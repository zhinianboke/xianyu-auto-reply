"""
采集商品发送私信定时任务

功能：
1. 查询采集商品表中"卖家真实ID已补全(seller_user_id 不为空) 且 未私信(is_dm_sent=0)"的数据
2. 取该商品所属监控任务配置的下单账号列表(order_account_ids，私信与下单共用)与私信内容(dm_content)
3. 在该任务的下单账号列表中轮换取账号发起私信：参照既有发起聊天逻辑，调用 WebSocket 服务的
   create-chat 创建/获取与卖家的会话，再调用 send-message 发送私信内容
4. 发送成功后将该采集商品标记为已私信(is_dm_sent=1)，并记录成功私信使用的账号(dm_account_id)，
   供后续自动下单优先使用该账号

账号规则：
- 账号不可用（离线/会话创建失败/Token过期等）：本次运行不再使用该账号，换下一个账号，不计私信尝试次数
- 内容发送被拦截(failed)：累计私信尝试次数(dm_attempts)，清空 dm_account_id，本次不再换号（下次任务再试）
- 发送成功/超时未确认：标记已私信(终态)，记录 dm_account_id

说明：
- 发起私信需要卖家真实用户ID作为收件人，因此处理的是 seller_user_id 已补全的数据
  （seller_user_id 为空无法私信，由"采集商品卖家ID补全"任务先补全）。
- 私信账号需已启动且 WebSocket 在线，否则换号或下次任务再试。
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
from common.models.xy_account import XYAccount
from common.utils.time_utils import get_beijing_now_naive

_INACTIVE_STATUSES = {"inactive", "disabled", "suspended", "deleted"}
# 单次任务最多扫描的待私信商品数（全局安全上限，避免一次性载入过多；
# 每个监控任务实际处理条数由任务自身的 dm_batch_size 控制）
_MAX_ITEMS_SCAN_PER_RUN = 500
# 私信发送失败最大重试次数（达到后不再重试）
_MAX_DM_ATTEMPTS = 3


class DmSendTaskService:
    """采集商品发送私信任务服务"""

    def __init__(self, task_name: str = "采集商品发送私信"):
        self.task_name = task_name
        self._lock = asyncio.Lock()

    async def execute(self):
        """执行发送私信任务。"""
        # 并发保护：发送私信对外可见，避免定时与手动触发并发导致重复私信
        if self._lock.locked():
            logger.info(f"【{self.task_name}】已有任务正在执行，跳过本次")
            return
        async with self._lock:
            await self._execute_inner()

    async def _execute_inner(self):
        logger.info(f"【{self.task_name}】开始执行")
        start_time = datetime.now()

        try:
            items = await self._get_items_to_send()
            if not items:
                logger.info(f"【{self.task_name}】没有待私信的采集商品，结束")
                return

            logger.info(f"【{self.task_name}】查询到 {len(items)} 条待私信商品")

            # 监控任务ID -> 私信内容（缓存）
            task_content_cache: Dict[int, Optional[str]] = {}
            # 监控任务ID -> 可用账号列表（缓存，保持配置顺序）
            task_accounts_cache: Dict[int, List[XYAccount]] = {}
            # 监控任务ID -> 每次最多处理条数（缓存）
            task_batch_cache: Dict[int, int] = {}
            # 监控任务ID -> 轮换指针（让同一任务的多条商品轮换使用不同账号）
            task_rr: Dict[int, int] = {}
            # 监控任务ID -> 本次已实际私信处理条数（达到 dm_batch_size 后该任务本次不再处理）
            task_done: Dict[int, int] = {}
            # 本次运行被判定不可用的账号（停用至本次结束）
            disabled_accounts: set[str] = set()

            sent = 0
            skipped_no_config = 0
            skipped_batch_full = 0
            no_account = 0
            failed = 0

            for pk, item_id, seller_user_id, task_id in items:
                # 私信内容、账号、批量上限（按任务缓存）
                if task_id not in task_content_cache:
                    (
                        task_content_cache[task_id],
                        task_accounts_cache[task_id],
                        task_batch_cache[task_id],
                    ) = await self._get_task_dm_config(task_id)
                dm_content = task_content_cache.get(task_id)
                accounts = task_accounts_cache.get(task_id) or []
                batch_size = task_batch_cache.get(task_id, 5)

                # 未配置下单账号或私信内容：跳过（不发，也不标记）
                if not dm_content or not accounts:
                    skipped_no_config += 1
                    continue

                # 该任务本次已达每次最多处理条数：跳过
                if task_done.get(task_id, 0) >= batch_size:
                    skipped_batch_full += 1
                    continue

                usable = [a for a in accounts if a.account_id not in disabled_accounts]
                if not usable:
                    no_account += 1
                    continue

                result = await self._send_for_item(
                    pk=pk,
                    item_id=item_id,
                    seller_user_id=seller_user_id,
                    content=dm_content,
                    accounts=usable,
                    rr_start=task_rr.get(task_id, 0),
                    disabled_accounts=disabled_accounts,
                )
                task_rr[task_id] = task_rr.get(task_id, 0) + 1

                if result == "sent":
                    sent += 1
                    task_done[task_id] = task_done.get(task_id, 0) + 1
                elif result == "no_account":
                    no_account += 1
                else:
                    # failed：内容被拦截已实际发出，计入该任务本次处理条数
                    failed += 1
                    task_done[task_id] = task_done.get(task_id, 0) + 1

                await asyncio.sleep(0.5)

            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(
                f"【{self.task_name}】执行完成：待私信{len(items)}，成功{sent}，"
                f"未配置跳过{skipped_no_config}，达批量上限跳过{skipped_batch_full}，"
                f"无可用账号{no_account}，失败{failed}，"
                f"停用账号{len(disabled_accounts)}，耗时{elapsed:.2f}秒"
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
                        ListingMonitorItem.is_ordered.is_(False),
                        ListingMonitorItem.dm_attempts < _MAX_DM_ATTEMPTS,
                        ListingMonitorItem.seller_user_id.isnot(None),
                        ListingMonitorItem.seller_user_id != "",
                    )
                )
                .order_by(ListingMonitorItem.id.asc())
                .limit(_MAX_ITEMS_SCAN_PER_RUN)
            )
            rows = (await session.execute(stmt)).all()
            return [(r[0], r[1], r[2], r[3]) for r in rows]

    async def _get_task_dm_config(self, task_id: int) -> Tuple[Optional[str], List[XYAccount], int]:
        """获取监控任务的私信内容、可用账号列表与每次最多处理条数（任务须未删除且启用）。

        私信与下单共用 order_account_ids，按配置顺序返回、过滤禁用/空Cookie账号。
        Returns: (dm_content, accounts, dm_batch_size)
        """
        async with async_session_maker() as session:
            task = (
                await session.execute(
                    select(
                        ListingMonitorTask.dm_content,
                        ListingMonitorTask.order_account_ids,
                        ListingMonitorTask.dm_batch_size,
                    ).where(
                        ListingMonitorTask.id == task_id,
                        ListingMonitorTask.is_deleted.is_(False),
                        ListingMonitorTask.is_enabled.is_(True),
                    )
                )
            ).first()
            if not task:
                return None, [], 5
            dm_content = task[0]
            account_ids = list(task[1] or [])
            batch_size = task[2] if task[2] and task[2] > 0 else 5
            if not dm_content or not account_ids:
                return dm_content, [], batch_size
            rows = list(
                (
                    await session.execute(
                        select(XYAccount).where(XYAccount.account_id.in_(account_ids))
                    )
                ).scalars().all()
            )

        by_id = {row.account_id: row for row in rows}
        ordered: List[XYAccount] = []
        for account_id in account_ids:
            acc = by_id.get(account_id)
            if not acc or not acc.cookie:
                continue
            if (acc.status or "active").strip().lower() in _INACTIVE_STATUSES:
                continue
            ordered.append(acc)
        return dm_content, ordered, batch_size

    async def _send_for_item(
        self,
        pk: int,
        item_id: str,
        seller_user_id: str,
        content: str,
        accounts: List[XYAccount],
        rr_start: int,
        disabled_accounts: set[str],
    ) -> str:
        """对单个商品轮换账号发起私信。

        Returns: "sent" / "failed" / "no_account"
        """
        n = len(accounts)
        tried = 0
        for offset in range(n):
            acc = accounts[(rr_start + offset) % n]
            if acc.account_id in disabled_accounts:
                continue
            tried += 1
            res = await self._send_dm(
                account_id=acc.account_id,
                seller_user_id=seller_user_id,
                item_id=item_id,
                content=content,
            )
            if res is None:
                # 账号级失败（离线/会话创建失败等）：本次停用，换下一个账号，不计尝试次数
                disabled_accounts.add(acc.account_id)
                logger.warning(
                    f"【{self.task_name}】账号 {acc.account_id} 私信不可用，本次停用，尝试下一个账号"
                )
                continue

            send_status, send_fail_reason, chat_id = res
            if send_status == "failed":
                # 内容被拦截：累计尝试次数、清空 dm_account_id，本次不再换号
                await self._record_result(pk, send_status, send_fail_reason, account_id=None, chat_id=chat_id)
                return "failed"

            # 成功 / 超时未确认：标记已私信终态，记录成功账号与会话ID
            await self._record_result(pk, send_status, send_fail_reason, account_id=acc.account_id, chat_id=chat_id)
            return "sent"

        # 所有账号都不可用
        return "no_account" if tried == 0 else "failed"

    async def _send_dm(self, account_id: str, seller_user_id: str, item_id: str, content: str):
        """参照既有发起聊天逻辑：创建会话 + 发送私信（并等待发送结果）。

        Returns:
            None：WebSocket 发送层失败（账号离线/会话创建失败等），应换号；
            (send_status, send_fail_reason, chat_id)：WebSocket 已发出（不论是否被服务端拦截）。
        """
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
            return None

        if not isinstance(create_res, dict) or not create_res.get("success"):
            msg = create_res.get("message") if isinstance(create_res, dict) else create_res
            logger.warning(f"【{self.task_name}】商品 {item_id} 创建会话失败（账号 {account_id}）：{msg}")
            return None

        chat_id = (create_res.get("data") or {}).get("chat_id")
        if not chat_id:
            logger.warning(f"【{self.task_name}】商品 {item_id} 创建会话响应缺少 chat_id（账号 {account_id}）")
            return None

        # 2) 发送私信内容（等待服务端结果，识别安全拦截）
        send_url = f"{base_url}/internal/accounts/{account_id}/send-message"
        try:
            send_res = await http_client.post(
                send_url, json={"chat_id": chat_id, "message": content, "wait_result": True}
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"【{self.task_name}】商品 {item_id} 发送私信异常（账号 {account_id}）：{exc}")
            return None

        if not isinstance(send_res, dict) or not send_res.get("success"):
            msg = send_res.get("message") if isinstance(send_res, dict) else send_res
            logger.warning(f"【{self.task_name}】商品 {item_id} 发送私信失败（账号 {account_id}）：{msg}")
            return None

        data = send_res.get("data") or {}
        send_status = data.get("send_status") or "unknown"
        send_fail_reason = data.get("send_fail_reason")
        logger.info(
            f"【{self.task_name}】商品 {item_id} 私信已发出："
            f"账号={account_id}，卖家={seller_user_id}，chat_id={chat_id}，结果={send_status}"
        )
        return (send_status, send_fail_reason, chat_id)

    async def _record_result(
        self,
        pk: int,
        send_status: str,
        send_fail_reason: Optional[str],
        account_id: Optional[str],
        chat_id: Optional[str] = None,
    ) -> None:
        """记录私信发送结果并累计尝试次数。

        - success / unknown(超时未确认)：置 is_dm_sent=true（终态，不再重试，避免重复发送），
          记录成功私信账号 dm_account_id（供后续下单优先使用）
        - failed：保持 is_dm_sent=false，累计 dm_attempts，并清空 dm_account_id；
          达到上限后由查询条件自动排除（停止重试）
        """
        async with async_session_maker() as session:
            item = (
                await session.execute(
                    select(ListingMonitorItem).where(ListingMonitorItem.id == pk)
                )
            ).scalar_one_or_none()
            if not item:
                return
            item.dm_attempts = (item.dm_attempts or 0) + 1
            item.dm_status = (send_status or "unknown")[:20]
            item.dm_fail_reason = str(send_fail_reason)[:500] if send_fail_reason else None
            # 记录私信会话ID（已创建会话即记录，便于后续追溯/继续沟通）
            if chat_id:
                item.dm_chat_id = str(chat_id)[:80]
            if send_status != "failed":
                # 成功或超时未确认：标记为已处理终态，记录成功私信账号与私信时间
                item.is_dm_sent = True
                item.dm_account_id = account_id[:80] if account_id else None
                item.dm_sent_at = get_beijing_now_naive()
            else:
                # 失败：清空成功私信账号
                item.dm_account_id = None
            await session.commit()


# 全局实例
dm_send_task_service = DmSendTaskService(task_name="采集商品发送私信")
