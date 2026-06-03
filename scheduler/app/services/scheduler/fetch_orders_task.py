"""
定时获取闲鱼订单任务

功能：
1. 查询数据库中所有启用状态的账号
2. 逐个账号调用闲鱼订单列表API获取订单并同步到数据库
3. 单个账号失败不影响其他账号

本模块同时承载两个定时任务（通过参数复用同一套遍历账号 + 同步逻辑）：
- 获取闲鱼订单任务（fetch_orders）：query_code=ALL，翻页拉取全部订单
- 获取待发货订单任务（fetch_pending_orders）：query_code=NOT_SHIP，只拉首页，
  侧重同步收货人姓名/手机号/地址等待发货信息
"""
from __future__ import annotations

import asyncio
from datetime import datetime

from loguru import logger
from sqlalchemy import select

from common.db.session import async_session_maker
from common.models.xy_account import XYAccount
from common.services.order_service import OrderService


class FetchOrdersTaskService:
    """定时获取闲鱼订单任务服务（可复用于全部订单 / 待发货订单两种场景）"""

    def __init__(
        self,
        task_name: str = "定时获取闲鱼订单",
        query_code: str = "ALL",
        max_pages: int | None = None,
    ):
        """
        Args:
            task_name: 任务名称（日志前缀）
            query_code: 闲鱼订单查询类型，"ALL"=全部，"NOT_SHIP"=待发货
            max_pages: 最大拉取页数，None=按 totalCount 翻页，正整数=最多拉该页数
        """
        self.task_name = task_name
        self.query_code = query_code
        self.max_pages = max_pages

    async def execute(self):
        """执行获取订单任务"""
        logger.info(f"【{self.task_name}】开始执行")
        start_time = datetime.now()

        try:
            # 1. 查询所有启用状态的账号
            accounts = await self._get_active_accounts()

            if not accounts:
                logger.info(f"【{self.task_name}】没有启用状态的账号，任务结束")
                return

            logger.info(f"【{self.task_name}】查询到 {len(accounts)} 个启用状态的账号")

            # 2. 逐个账号获取订单
            success_count = 0
            failed_count = 0
            total_fetched = 0
            total_new = 0
            total_updated = 0

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
                    result = await self._fetch_orders_for_account(account)
                    fetched = result.get("total_fetched", 0)
                    new_inserted = result.get("new_inserted", 0)
                    updated = result.get("updated", 0)
                    errors = result.get("errors", [])

                    total_fetched += fetched
                    total_new += new_inserted
                    total_updated += updated

                    if errors:
                        logger.warning(
                            f"【{self.task_name}】账号 {account.account_id} "
                            f"获取订单有警告: {errors}"
                        )

                    success_count += 1
                    logger.info(
                        f"【{self.task_name}】账号 {account.account_id} "
                        f"获取完成: 共{fetched}条, 新增{new_inserted}, 更新{updated}"
                    )
                except Exception as e:
                    failed_count += 1
                    logger.error(
                        f"【{self.task_name}】账号 {account.account_id} "
                        f"获取订单失败: {e}"
                    )

                # 账号间间隔2秒，避免请求过于密集
                if account != accounts[-1]:
                    await asyncio.sleep(2)

            # 3. 记录执行结果
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(
                f"【{self.task_name}】执行完成，"
                f"账号: 成功{success_count}/失败{failed_count}/共{len(accounts)}, "
                f"订单: 获取{total_fetched}/新增{total_new}/更新{total_updated}, "
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

    async def _fetch_orders_for_account(self, account) -> dict:
        """获取单个账号的订单"""
        async with async_session_maker() as session:
            order_service = OrderService(session)
            return await order_service.fetch_xianyu_orders(
                account,
                query_code=self.query_code,
                max_pages=self.max_pages,
            )


# 全局实例：获取全部订单（翻页）
fetch_orders_task_service = FetchOrdersTaskService(
    task_name="定时获取闲鱼订单",
    query_code="ALL",
    max_pages=None,
)

# 全局实例：获取待发货订单（只拉首页，侧重同步收货信息）
fetch_pending_orders_task_service = FetchOrdersTaskService(
    task_name="定时获取待发货订单",
    query_code="NOT_SHIP",
    max_pages=1,
)
