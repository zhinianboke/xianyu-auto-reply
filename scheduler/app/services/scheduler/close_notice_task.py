"""
关闭账号消息通知定时任务

功能：
1. 每10分钟执行一次（默认禁用，需手动开启）
2. 查询数据库中所有启用状态的账号
3. 逐个账号调用公共关闭账号通知方法
4. 记录执行日志（哪些账号关闭成功，哪些失败）
5. 单个账号失败不影响其他账号处理
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.session import async_session_maker
from common.models.scheduled_close_notice_log import ScheduledCloseNoticeLog
from common.models.xy_account import XYAccount
from common.utils.xianyu_utils import close_account_notice


class CloseNoticeTaskService:
    """关闭账号消息通知定时任务服务"""

    def __init__(self):
        self.task_name = "关闭账号消息通知"

    async def execute(self):
        """执行关闭消息通知任务"""
        logger.info(f"【{self.task_name}】开始执行")
        start_time = datetime.now()

        # 生成批次ID
        batch_id = str(uuid.uuid4())

        try:
            async with async_session_maker() as session:
                # 1. 查询所有启用状态的账号
                accounts = await self._get_active_accounts(session)

                if not accounts:
                    logger.info(f"【{self.task_name}】没有启用状态的账号，任务结束")
                    return

                logger.info(f"【{self.task_name}】查询到 {len(accounts)} 个启用状态的账号")

                # 2. 逐个账号关闭消息通知
                success_count = 0
                failed_count = 0

                for account in accounts:
                    try:
                        ok, error_msg = await self._close_notice_for_account(account)

                        # 记录日志
                        await self._log_result(
                            session=session,
                            batch_id=batch_id,
                            account_id=account.account_id,
                            status="success" if ok else "failed",
                            error_message=error_msg,
                        )

                        if ok:
                            success_count += 1
                            logger.info(f"【{self.task_name}】账号 {account.account_id} 关闭成功")
                        else:
                            failed_count += 1
                            logger.warning(f"【{self.task_name}】账号 {account.account_id} 关闭失败: {error_msg}")

                    except Exception as e:
                        failed_count += 1
                        error_str = str(e)[:500]
                        logger.error(f"【{self.task_name}】账号 {account.account_id} 处理异常: {error_str}")

                        # 记录异常日志
                        await self._log_result(
                            session=session,
                            batch_id=batch_id,
                            account_id=account.account_id,
                            status="failed",
                            error_message=error_str,
                        )

                    # 账号间间隔1秒，避免请求过于密集
                    if account != accounts[-1]:
                        await asyncio.sleep(1)

                # 3. 记录执行结果
                elapsed = (datetime.now() - start_time).total_seconds()
                logger.info(
                    f"【{self.task_name}】执行完成，批次ID: {batch_id}, "
                    f"成功: {success_count}, 失败: {failed_count}, "
                    f"共: {len(accounts)}, 耗时: {elapsed:.2f}秒"
                )

        except Exception as e:
            logger.error(f"【{self.task_name}】执行失败: {e}")
            raise

    async def _get_active_accounts(self, session: AsyncSession) -> list:
        """获取所有启用状态的账号"""
        inactive_statuses = {"inactive", "disabled", "suspended", "deleted"}
        stmt = select(XYAccount).where(
            XYAccount.status.notin_(inactive_statuses)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def _close_notice_for_account(
        self,
        account: XYAccount,
    ) -> tuple[bool, Optional[str]]:
        return await close_account_notice(account.account_id, account.cookie or "", self.task_name)

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
            log = ScheduledCloseNoticeLog(
                batch_id=batch_id,
                account_id=account_id,
                status=status,
                error_message=error_message[:500] if error_message else None,
            )
            session.add(log)
            await session.commit()
        except Exception as e:
            logger.error(f"【{self.task_name}】记录日志失败: {e}")
            await session.rollback()


# 全局实例
close_notice_task_service = CloseNoticeTaskService()
