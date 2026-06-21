"""
登录状态续期定时任务

功能：
1. 每10分钟执行一次
2. 查询数据库中所有启用状态的账号
3. 调用 mtop.taobao.idlemessage.pc.loginuser.get 接口检查登录状态
4. 令牌过期时获取set-cookies更新到数据库
5. Session过期时触发后台异步密码登录
6. 记录执行日志
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional

import aiohttp
from loguru import logger
from sqlalchemy import delete as sql_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.session import async_session_maker
from common.models.scheduled_login_renew_log import ScheduledLoginRenewLog
from common.models.xy_account import XYAccount
from common.utils.cookie_refresh import clear_cookie_refresh_snapshot
from common.utils.xianyu_utils import trans_cookies, generate_sign
from common.utils.time_utils import get_beijing_now_naive


class LoginRenewTaskService:
    """登录状态续期定时任务服务"""

    # 登录续期日志保留天数，超过该天数的日志在每次任务执行时主动清理
    LOG_RETENTION_DAYS = 10

    def __init__(self):
        self.task_name = "登录状态续期"

    async def execute(self):
        """执行登录续期任务"""
        logger.info(f"【{self.task_name}】开始执行")
        start_time = datetime.now()
        
        # 生成批次ID
        batch_id = str(uuid.uuid4())

        try:
            async with async_session_maker() as session:
                # 主动清理过期的登录续期日志（10天前）
                await self._cleanup_expired_logs(session)

                # 1. 查询所有启用状态的账号
                accounts = await self._get_active_accounts(session)
                
                if not accounts:
                    logger.info(f"【{self.task_name}】没有启用状态的账号")
                    return

                logger.info(f"【{self.task_name}】找到 {len(accounts)} 个启用状态的账号")

                # 2. 遍历账号，执行续期检查
                success_count = 0
                token_refreshed_count = 0
                session_expired_count = 0
                failed_count = 0
                
                for account in accounts:
                    # 检查账号是否处于Session过期冷却期内
                    from common.utils.cookie_refresh import is_account_session_cooled
                    if is_account_session_cooled(account.account_id):
                        logger.info(
                            f"【{self.task_name}】账号 {account.account_id} "
                            f"处于Session过期冷却期内，跳过"
                        )
                        continue
                    
                    try:
                        status, message = await self._renew_account(session, account)
                        
                        # 记录日志
                        await self._log_result(
                            session=session,
                            batch_id=batch_id,
                            account_id=account.account_id,
                            status=status,
                            error_message=message
                        )
                        
                        if status == "success":
                            success_count += 1
                        elif status == "token_refreshed":
                            token_refreshed_count += 1
                        elif status == "session_expired":
                            session_expired_count += 1
                        else:
                            failed_count += 1
                            
                    except Exception as e:
                        failed_count += 1
                        logger.error(f"【{self.task_name}】账号 {account.account_id} 处理异常: {e}")
                        
                        # 记录异常日志
                        await self._log_result(
                            session=session,
                            batch_id=batch_id,
                            account_id=account.account_id,
                            status="failed",
                            error_message=str(e)[:500]
                        )
                    
                    # 账号间间隔1秒，避免请求过于密集
                    await asyncio.sleep(1)

                # 3. 记录执行结果
                elapsed = (datetime.now() - start_time).total_seconds()
                logger.info(
                    f"【{self.task_name}】执行完成，批次ID: {batch_id}, "
                    f"成功: {success_count}, 令牌刷新: {token_refreshed_count}, "
                    f"Session过期: {session_expired_count}, 失败: {failed_count}, "
                    f"耗时: {elapsed:.2f}秒"
                )

        except Exception as e:
            logger.error(f"【{self.task_name}】执行失败: {e}")
            raise

    async def _cleanup_expired_logs(self, session: AsyncSession) -> None:
        """
        主动清理过期的登录续期日志

        删除 created_at 早于 (当前北京时间 - LOG_RETENTION_DAYS 天) 的日志记录，
        避免日志表无限增长。使用参数化的 ORM delete 语句，避免 SQL 注入。
        """
        try:
            cutoff_time = get_beijing_now_naive() - timedelta(days=self.LOG_RETENTION_DAYS)
            stmt = sql_delete(ScheduledLoginRenewLog).where(
                ScheduledLoginRenewLog.created_at < cutoff_time
            )
            result = await session.execute(stmt)
            await session.commit()

            deleted_count = result.rowcount or 0
            if deleted_count > 0:
                logger.info(
                    f"【{self.task_name}】已清理 {deleted_count} 条 {self.LOG_RETENTION_DAYS} 天前的登录续期日志"
                    f"（清理时间界限: {cutoff_time}）"
                )
        except Exception as e:
            logger.error(f"【{self.task_name}】清理过期日志失败: {e}")
            await session.rollback()

    async def _get_active_accounts(self, session: AsyncSession) -> list:
        """获取所有启用状态的账号"""
        inactive_statuses = {"inactive", "disabled", "suspended", "deleted"}
        stmt = select(XYAccount).where(
            XYAccount.status.notin_(inactive_statuses)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def _renew_account(
        self,
        session: AsyncSession,
        account: XYAccount
    ) -> tuple[str, Optional[str]]:
        """
        对单个账号执行续期检查
        
        Returns:
            (状态, 消息)
            状态: success/token_refreshed/session_expired/failed
        """
        account_id = account.account_id
        cookies_str = account.cookie
        
        logger.info(f"【{self.task_name}】开始检查账号: {account_id}")
        
        try:
            # 调用登录用户接口检查登录状态
            result = await self._fetch_login_user_for_renew(cookies_str, account_id)
            
            status = result.get("status", "failed")
            message = result.get("message")
            new_cookies = result.get("new_cookies")
            
            # 如果获取到新Cookie，更新数据库
            if new_cookies and new_cookies != cookies_str:
                account.cookie = new_cookies
                account.metadata_json = clear_cookie_refresh_snapshot(account.metadata_json)
                account.last_refresh_at = get_beijing_now_naive()
                session.add(account)
                await session.commit()
                logger.info(f"【{self.task_name}】账号 {account_id} Cookie已更新")
            
            # Session过期或令牌为空时触发后台密码登录
            if status in ("session_expired", "token_empty"):
                from common.utils.cookie_refresh import (
                    mark_account_session_expired, trigger_password_login_async
                )
                mark_account_session_expired(account_id)
                trigger_password_login_async(account_id)
                status_desc = "Session过期" if status == "session_expired" else "令牌为空"
                logger.warning(
                    f"【{self.task_name}】账号 {account_id} {status_desc}，"
                    f"已标记冷却并触发后台密码登录"
                )
            
            return status, message
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"【{self.task_name}】账号 {account_id} 续期检查失败: {error_msg}")
            return "failed", error_msg

    async def _fetch_login_user_for_renew(
        self,
        cookies_str: str,
        account_id: str
    ) -> dict:
        """
        调用 mtop.taobao.idlemessage.pc.loginuser.get 接口用于登录状态续期
        
        Returns:
            {
                "status": "success/token_refreshed/session_expired/failed",
                "message": "说明信息",
                "new_cookies": "新的Cookie字符串（如果有更新）"
            }
        """
        cookies = trans_cookies(cookies_str)
        timestamp = str(int(time.time() * 1000))
        data_val = '{}'
        
        token = cookies.get('_m_h5_tk', '').split('_')[0] if cookies.get('_m_h5_tk') else ''
        sign = generate_sign(timestamp, token, data_val)
        
        params = {
            'jsv': '2.7.2',
            'appKey': '34839810',
            't': timestamp,
            'sign': sign,
            'v': '1.0',
            'type': 'originaljson',
            'accountSite': 'xianyu',
            'dataType': 'json',
            'timeout': '20000',
            'api': 'mtop.taobao.idlemessage.pc.loginuser.get',
            'sessionOption': 'AutoLoginOnly',
            'spm_cnt': 'a21ybx.im.0.0',
            'spm_pre': 'a21ybx.item.want.1.12523da6waCtUp',
            'log_id': '12523da6waCtUp',
        }
        
        headers = {
            'accept': 'application/json',
            'accept-language': 'en,zh-CN;q=0.9,zh;q=0.8,zh-TW;q=0.7,ja;q=0.6',
            'cache-control': 'no-cache',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://www.goofish.com',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': 'https://www.goofish.com/',
            'sec-ch-ua': '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
            'cookie': cookies_str.replace('\n', '').replace('\r', '') if cookies_str else '',
        }
        
        try:
            async with aiohttp.ClientSession() as http_session:
                async with http_session.post(
                    'https://h5api.m.goofish.com/h5/mtop.taobao.idlemessage.pc.loginuser.get/1.0/',
                    params=params,
                    data={'data': data_val},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=20)
                ) as response:
                    res_json = await response.json()
                    
                    ret = res_json.get('ret', [])
                    ret_str = ret[0] if ret else ''
                    
                    logger.info(f"【{self.task_name}】账号 {account_id} 接口返回: ret={ret}")
                    
                    # 提取set-cookie，合并更新Cookie
                    new_cookies_str = self._handle_set_cookie_response(
                        response, cookies_str
                    )
                    
                    # 成功
                    if 'SUCCESS' in ret_str:
                        return {
                            "status": "success",
                            "message": "登录状态正常",
                            "new_cookies": new_cookies_str
                        }
                    
                    # 令牌过期 - set-cookie已在上面合并
                    if 'TOKEN_EXOIRED' in ret_str or 'TOKEN_EXPIRED' in ret_str:
                        if new_cookies_str and new_cookies_str != cookies_str:
                            return {
                                "status": "token_refreshed",
                                "message": "令牌已刷新",
                                "new_cookies": new_cookies_str
                            }
                        else:
                            return {
                                "status": "failed",
                                "message": "令牌过期但未获取到新Cookie",
                                "new_cookies": None
                            }
                    
                    # Session过期
                    if 'SESSION_EXPIRED' in ret_str:
                        return {
                            "status": "session_expired",
                            "message": "Session过期，需要重新登录",
                            "new_cookies": None
                        }
                    
                    # 令牌为空（Cookie中缺少_m_h5_tk等关键字段）
                    if 'TOKEN_EMPTY' in ret_str or '令牌为空' in ret_str:
                        return {
                            "status": "token_empty",
                            "message": "令牌为空，需要重新登录",
                            "new_cookies": None
                        }
                    
                    # 其他错误
                    return {
                        "status": "failed",
                        "message": ret_str or "未知错误",
                        "new_cookies": None
                    }
                    
        except aiohttp.ClientError as e:
            return {
                "status": "failed",
                "message": f"网络请求失败: {e}",
                "new_cookies": None
            }
        except Exception as e:
            return {
                "status": "failed",
                "message": f"请求异常: {e}",
                "new_cookies": None
            }

    def _handle_set_cookie_response(
        self,
        response,
        original_cookies_str: str
    ) -> Optional[str]:
        """
        从响应的set-cookie头中提取新Cookie并合并更新
        
        Returns:
            更新后的Cookie字符串，如果没有更新则返回None
        """
        try:
            # 获取响应头中的set-cookie
            set_cookies = response.headers.getall('Set-Cookie', [])
            if not set_cookies:
                return None
            
            # 解析原始Cookie
            original_cookies = trans_cookies(original_cookies_str)
            
            # 解析新的Cookie
            for cookie_str in set_cookies:
                # 提取cookie名和值
                if '=' in cookie_str:
                    cookie_part = cookie_str.split(';')[0]
                    if '=' in cookie_part:
                        key, value = cookie_part.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        if key and value:
                            original_cookies[key] = value
            
            # 重新组装Cookie字符串
            new_cookies_str = '; '.join([f"{k}={v}" for k, v in original_cookies.items()])
            return new_cookies_str
            
        except Exception as e:
            logger.error(f"【{self.task_name}】解析set-cookie失败: {e}")
            return None

    async def _log_result(
        self,
        session: AsyncSession,
        batch_id: str,
        account_id: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        """记录执行日志"""
        try:
            log = ScheduledLoginRenewLog(
                batch_id=batch_id,
                account_id=account_id,
                status=status,
                error_message=error_message[:500] if error_message else None,
            )
            session.add(log)
            await session.commit()
            
            if status == "success":
                logger.info(f"【{self.task_name}】账号 {account_id} 状态正常")
            elif status == "token_refreshed":
                logger.info(f"【{self.task_name}】账号 {account_id} 令牌已刷新")
            elif status == "session_expired":
                logger.warning(f"【{self.task_name}】账号 {account_id} Session过期")
            else:
                logger.warning(f"【{self.task_name}】账号 {account_id} 处理失败: {error_message}")
            
        except Exception as e:
            logger.error(f"【{self.task_name}】记录日志失败: {e}")
            await session.rollback()


# 全局实例
login_renew_task_service = LoginRenewTaskService()
