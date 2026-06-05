"""
定时获取闲鱼商品任务

功能：
1. 查询数据库中所有启用状态的账号
2. 逐个账号调用闲鱼商品列表API获取商品并 upsert 到数据库
3. 单个账号失败不影响其他账号

并发说明：
- 商品入库统一复用公共 ItemService.fetch_all_items_from_account，
  该入口已内置账号级 Redis 互斥锁（item_sync:{account_id}），可避免「定时获取
  闲鱼商品任务」与「商品管理页手动触发同步」并发 upsert 同一商品；
- 即便 Redis 不可用导致降级无锁执行，也由 xy_catalog_items 的
  (account_id, item_id) 唯一约束 + 保存时的冲突重试做最终兜底，确保不会重复入库。
"""
from __future__ import annotations

import asyncio
from datetime import datetime

from loguru import logger
from sqlalchemy import select

from common.db.session import async_session_maker
from common.models.xy_account import XYAccount
from common.services.item_service import ItemService
from common.utils.cookie_refresh import is_account_session_cooled


class FetchItemsTaskService:
    """定时获取闲鱼商品任务服务"""

    def __init__(
        self,
        task_name: str = "定时获取闲鱼商品",
        page_size: int = 20,
        max_pages: int | None = None,
    ):
        """
        Args:
            task_name: 任务名称（日志前缀）
            page_size: 每页拉取数量
            max_pages: 最大拉取页数，None=按返回结果翻页直到结束
        """
        self.task_name = task_name
        self.page_size = page_size
        self.max_pages = max_pages

    async def execute(self):
        """执行获取商品任务"""
        logger.info(f"【{self.task_name}】开始执行")
        start_time = datetime.now()

        try:
            # 1. 查询所有启用状态的账号
            accounts = await self._get_active_accounts()

            if not accounts:
                logger.info(f"【{self.task_name}】没有启用状态的账号，任务结束")
                return

            logger.info(f"【{self.task_name}】查询到 {len(accounts)} 个启用状态的账号")

            # 2. 逐个账号获取商品
            success_count = 0
            failed_count = 0
            skipped_count = 0
            total_fetched = 0
            total_saved = 0

            for account in accounts:
                # 检查账号是否处于Session过期冷却期内
                if is_account_session_cooled(account.account_id):
                    logger.info(
                        f"【{self.task_name}】账号 {account.account_id} "
                        f"处于Session过期冷却期内，跳过"
                    )
                    continue

                try:
                    result = await self._fetch_items_for_account(account)
                    if not result.get("success"):
                        failed_count += 1
                        logger.warning(
                            f"【{self.task_name}】账号 {account.account_id} "
                            f"获取商品失败: {result.get('message')}"
                        )
                    elif result.get("skipped"):
                        skipped_count += 1
                        logger.info(
                            f"【{self.task_name}】账号 {account.account_id} "
                            f"已有同步进行中，本次跳过"
                        )
                    else:
                        fetched = int(result.get("total_count") or 0)
                        saved = int(result.get("saved_count") or 0)
                        total_fetched += fetched
                        total_saved += saved
                        success_count += 1
                        logger.info(
                            f"【{self.task_name}】账号 {account.account_id} "
                            f"获取完成: 共{fetched}件, 保存{saved}件"
                        )
                except Exception as e:
                    failed_count += 1
                    logger.error(
                        f"【{self.task_name}】账号 {account.account_id} "
                        f"获取商品异常: {e}"
                    )

                # 账号间间隔2秒，避免请求过于密集
                if account is not accounts[-1]:
                    await asyncio.sleep(2)

            # 3. 记录执行结果
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(
                f"【{self.task_name}】执行完成，"
                f"账号: 成功{success_count}/失败{failed_count}/跳过{skipped_count}/共{len(accounts)}, "
                f"商品: 获取{total_fetched}/保存{total_saved}, "
                f"耗时: {elapsed:.2f}秒"
            )

        except Exception as e:
            logger.error(f"【{self.task_name}】执行异常: {e}")

    async def _get_active_accounts(self) -> list:
        """获取所有启用状态的账号"""
        async with async_session_maker() as session:
            inactive_statuses = {"inactive", "disabled", "suspended", "deleted"}
            stmt = select(XYAccount).where(
                XYAccount.status.notin_(inactive_statuses)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def _fetch_items_for_account(self, account) -> dict:
        """获取单个账号的全部商品并入库（复用 ItemService 的加锁入口）

        增量同步策略：开启 stop_when_page_all_existing，当某一页商品在本地库中
        全部已存在（且无跳过项）时停止继续翻页。由于闲鱼「在售」列表默认按上架
        时间倒序（新品在前），首页全部已存在即说明无新上架商品，停止翻页是安全
        的，不会漏抓新品；首次同步或有新品时仍会按需翻页直至拉全，从而在保证数据
        完整的前提下大幅降低对闲鱼接口的请求量，规避风控风险。
        """
        async with async_session_maker() as session:
            item_svc = ItemService(session)
            return await item_svc.fetch_all_items_from_account(
                account=account,
                page_size=self.page_size,
                max_pages=self.max_pages,
                stop_when_page_all_existing=True,
            )


# 全局实例
fetch_items_task_service = FetchItemsTaskService(
    task_name="定时获取闲鱼商品",
    page_size=20,
    max_pages=None,
)
