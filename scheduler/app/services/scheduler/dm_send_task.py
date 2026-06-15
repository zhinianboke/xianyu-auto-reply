"""
采集商品发送私信定时任务

功能：
1. 查询采集商品表中"卖家真实ID已补全(seller_user_id 不为空) 且 未私信(is_dm_sent=0)"的数据
2. 取该商品所属监控任务配置的私信账号(dm_account_id)与私信内容(dm_content)
3. 参照既有发起聊天逻辑：调用 WebSocket 服务的 create-chat 创建/获取与卖家的会话，
   再调用 send-message 发送私信内容
4. 发送成功后将该采集商品标记为已私信(is_dm_sent=1)

说明：
- 发起私信需要卖家真实用户ID作为收件人，因此处理的是 seller_user_id 已补全的数据
  （seller_user_id 为空无法私信，由"采集商品卖家ID补全"任务先补全）。
- 私信账号需已启动且 WebSocket 在线，否则本次跳过、下次任务再试。
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy import and_, select

from app.core.config import get_settings
from app.core.http_client import get_http_client
from common.db.session import async_session_maker
from common.models.listing_monitor_item import ListingMonitorItem
from common.models.listing_monitor_task import ListingMonitorTask

# 单次任务最多处理的待私信商品数，避免单次运行过久
_MAX_ITEMS_PER_RUN = 100


class DmSendTaskService:
    """采集商品发送私信任务服务"""

    def __init__(self, task_name: str = "采集商品发送私信"):
        self.task_name = task_name

    async def execute(self):
        """执行发送私信任务。"""
        logger.info(f"【{self.task_name}】开始执行")
        start_time = datetime.now()

        try:
            items = await self._get_items_to_send()
            if not items:
                logger.info(f"【{self.task_name}】没有待私信的采集商品，结束")
                return

            logger.info(f"【{self.task_name}】查询到 {len(items)} 条待私信商品")

            # 监控任务ID -> (dm_account_id, dm_content) 缓存
            task_dm_cache: Dict[int, Tuple[Optional[str], Optional[str]]] = {}
            sent = 0
            skipped_no_config = 0
            failed = 0

            for pk, item_id, seller_user_id, task_id in items:
                dm_conf = task_dm_cache.get(task_id)
                if dm_conf is None:
                    dm_conf = await self._get_task_dm_config(task_id)
                    task_dm_cache[task_id] = dm_conf
                dm_account_id, dm_content = dm_conf

                # 未配置私信账号或私信内容：跳过（不发，也不标记）
                if not dm_account_id or not dm_content:
                    skipped_no_config += 1
                    continue

                ok = await self._send_dm(
                    account_id=dm_account_id,
                    seller_user_id=seller_user_id,
                    item_id=item_id,
                    content=dm_content,
                )
                if ok:
                    await self._mark_dm_sent(pk)
                    sent += 1
                else:
                    failed += 1

                await asyncio.sleep(0.5)

            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(
                f"【{self.task_name}】执行完成：待私信{len(items)}，成功{sent}，"
                f"未配置私信跳过{skipped_no_config}，失败{failed}，耗时{elapsed:.2f}秒"
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(f"【{self.task_name}】执行异常: {exc}")

    async def _get_items_to_send(self) -> List[Tuple[int, str, str, int]]:
        """查询卖家真实ID已补全且未私信的采集商品。

        Returns: (主键id, item_id, seller_user_id, monitor_task_id) 列表
        """
        async with async_session_maker() as session:
            stmt = (
                select(
                    ListingMonitorItem.id,
                    ListingMonitorItem.item_id,
                    ListingMonitorItem.seller_user_id,
                    ListingMonitorItem.monitor_task_id,
                )
                .where(
                    and_(
                        ListingMonitorItem.is_dm_sent.is_(False),
                        ListingMonitorItem.seller_user_id.isnot(None),
                        ListingMonitorItem.seller_user_id != "",
                    )
                )
                .order_by(ListingMonitorItem.id.asc())
                .limit(_MAX_ITEMS_PER_RUN)
            )
            rows = (await session.execute(stmt)).all()
            return [(r[0], r[1], r[2], r[3]) for r in rows]

    async def _get_task_dm_config(self, task_id: int) -> Tuple[Optional[str], Optional[str]]:
        """获取监控任务配置的私信账号与私信内容。"""
        async with async_session_maker() as session:
            task = (
                await session.execute(
                    select(ListingMonitorTask.dm_account_id, ListingMonitorTask.dm_content).where(
                        ListingMonitorTask.id == task_id
                    )
                )
            ).first()
            if not task:
                return None, None
            return task[0], task[1]

    async def _send_dm(self, account_id: str, seller_user_id: str, item_id: str, content: str) -> bool:
        """参照既有发起聊天逻辑：创建会话 + 发送私信。"""
        settings = get_settings()
        http_client = get_http_client()
        base_url = settings.websocket_service_url.rstrip("/")

        # 1) 创建/获取与卖家的会话
        create_url = f"{base_url}/internal/accounts/{account_id}/create-chat"
        try:
            create_res = await http_client.post(
                create_url, json={"buyer_id": str(seller_user_id), "item_id": str(item_id)}
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"【{self.task_name}】商品 {item_id} 创建会话异常（账号 {account_id}）：{exc}")
            return False

        if not isinstance(create_res, dict) or not create_res.get("success"):
            msg = create_res.get("message") if isinstance(create_res, dict) else create_res
            logger.warning(f"【{self.task_name}】商品 {item_id} 创建会话失败（账号 {account_id}）：{msg}")
            return False

        chat_id = (create_res.get("data") or {}).get("chat_id")
        if not chat_id:
            logger.warning(f"【{self.task_name}】商品 {item_id} 创建会话响应缺少 chat_id（账号 {account_id}）")
            return False

        # 2) 发送私信内容
        send_url = f"{base_url}/internal/accounts/{account_id}/send-message"
        try:
            send_res = await http_client.post(send_url, json={"chat_id": chat_id, "message": content})
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"【{self.task_name}】商品 {item_id} 发送私信异常（账号 {account_id}）：{exc}")
            return False

        if not isinstance(send_res, dict) or not send_res.get("success"):
            msg = send_res.get("message") if isinstance(send_res, dict) else send_res
            logger.warning(f"【{self.task_name}】商品 {item_id} 发送私信失败（账号 {account_id}）：{msg}")
            return False

        logger.info(
            f"【{self.task_name}】商品 {item_id} 私信发送成功："
            f"账号={account_id}，卖家={seller_user_id}，chat_id={chat_id}"
        )
        return True

    async def _mark_dm_sent(self, pk: int) -> None:
        """将采集商品标记为已私信。"""
        async with async_session_maker() as session:
            item = (
                await session.execute(
                    select(ListingMonitorItem).where(ListingMonitorItem.id == pk)
                )
            ).scalar_one_or_none()
            if item:
                item.is_dm_sent = True
                await session.commit()


# 全局实例
dm_send_task_service = DmSendTaskService(task_name="采集商品发送私信")
