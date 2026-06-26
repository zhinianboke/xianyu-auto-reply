"""
采集商品发送私信定时任务

功能：
1. 查询采集商品表中"最近2天下单成功(order_status=success 且 ordered_at>=今日00:00前推2天) 且
   卖家真实ID已补全(seller_user_id 不为空) 且 未私信(is_dm_sent=0)"的数据
2. 取私信内容(dm_content)；发私信账号严格使用"该商品下单成功时使用的账号"(order_account_id)，
   即"下单用哪个账号，就用哪个账号发起私信"
3. 用下单账号发起私信：参照既有发起聊天逻辑，调用 WebSocket 服务的
   create-chat 创建/获取与卖家的会话，再调用 send-message 发送私信内容
4. 发送成功后将该采集商品标记为已私信(is_dm_sent=1)，并记录成功私信使用的账号(dm_account_id)

账号规则：
- 严格使用下单账号(order_account_id)：下单用哪个账号就用哪个账号发私信，不换号
- 下单账号已删除（账号表查无此账号）：私信无法进行，直接判失败、置终态(dm_attempts 置上限)不再重试
- 下单账号仍存在但当前不可用（未启用/未启动/WebSocket未连接等）：本次跳过，不计尝试次数，留待下次任务再试
- 内容发送被拦截(failed)：累计私信尝试次数(dm_attempts)，清空 dm_account_id（下次任务再试）
- 发送成功/超时未确认：标记已私信(终态)，记录 dm_account_id
- 历史数据未记录下单账号(order_account_id 为空)时：回退到下单账号池(order_account_ids)+兜底账号轮换发送

说明：
- 仅在"下单成功之后"才发送私信：私信对象是已成功拍下该商品的卖家，故只处理 order_status=success 的数据
  （失败/重复/无账号等非成功状态不发私信）。
- "最近2天"按下单成功时间(ordered_at)计：处理最近2天下单成功的商品，提供48小时容错窗口，
  避免定时任务短期故障导致私信永久遗漏。
- 发起私信需要卖家真实用户ID作为收件人，因此处理的是 seller_user_id 已补全的数据
  （seller_user_id 为空无法私信，由"采集商品卖家ID补全"任务先补全）。
- 私信账号需已启动且 WebSocket 在线，否则换号或下次任务再试。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy import and_, select

from app.core.config import get_settings
from app.core.http_client import get_http_client
from common.db.session import async_session_maker
from common.models.listing_monitor_item import ListingMonitorItem
from common.models.listing_monitor_task import ListingMonitorTask
from common.models.xy_account import XYAccount
from common.services.order_account_loader import (
    load_fallback_accounts,
    load_xy_accounts_by_ids,
)
from common.utils.time_utils import get_beijing_now_naive

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

            for pk, item_id, seller_user_id, task_id, item_owner_id, order_account_id in items:
                # 私信内容、账号、批量上限（按任务缓存）
                if task_id not in task_content_cache:
                    (
                        task_content_cache[task_id],
                        task_accounts_cache[task_id],
                        task_batch_cache[task_id],
                    ) = await self._get_task_dm_config(task_id, item_owner_id)
                dm_content = task_content_cache.get(task_id)
                accounts = task_accounts_cache.get(task_id) or []
                batch_size = task_batch_cache.get(task_id, 5)

                # 未配置私信内容：跳过（不发，也不标记）
                if not dm_content:
                    skipped_no_config += 1
                    continue

                # 该任务本次已达每次最多处理条数：跳过
                if task_done.get(task_id, 0) >= batch_size:
                    skipped_batch_full += 1
                    continue

                # 账号选择：严格使用"下单成功的账号"发起私信；
                # 仅当历史数据未记录下单账号（order_account_id 为空）时，才回退到下单账号池轮换。
                if order_account_id:
                    account_ids = [order_account_id]
                    strict = True
                else:
                    account_ids = [
                        a.account_id for a in accounts if a.account_id not in disabled_accounts
                    ]
                    strict = False
                    if not account_ids:
                        no_account += 1
                        continue

                result = await self._send_for_item(
                    pk=pk,
                    item_id=item_id,
                    seller_user_id=seller_user_id,
                    content=dm_content,
                    account_ids=account_ids,
                    rr_start=task_rr.get(task_id, 0),
                    disabled_accounts=disabled_accounts,
                    strict=strict,
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

    async def _get_items_to_send(self) -> List[Tuple[int, str, str, int, Optional[int], Optional[str]]]:
        """查询"今天和昨天下单成功 且 卖家真实ID已补全 且 未私信"的采集商品。

        Returns: (主键id, item_id, seller_user_id, monitor_task_id, owner_id, order_account_id) 列表
        """
        # 只处理"下单成功时间"为今天和昨天（北京时间今天 00:00 前推 1 天 = 昨天 00:00 起）的采集商品，
        # 提供 24 小时容错窗口，避免定时任务短期故障导致私信永久遗漏
        cutoff_time = get_beijing_now_naive().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
        async with async_session_maker() as session:
            stmt = (
                select(
                    ListingMonitorItem.id,
                    ListingMonitorItem.item_id,
                    ListingMonitorItem.seller_user_id,
                    ListingMonitorItem.monitor_task_id,
                    ListingMonitorItem.owner_id,
                    ListingMonitorItem.order_account_id,
                )
                .where(
                    and_(
                        ListingMonitorItem.is_dm_sent.is_(False),
                        # 下单成功之后才发送私信（仅 success，排除失败/重复/无账号等非成功状态）
                        ListingMonitorItem.order_status == "success",
                        # 处理"下单成功时间"为今天和昨天的数据（ordered_at 仅在下单成功时写入北京时间）
                        ListingMonitorItem.ordered_at >= cutoff_time,
                        ListingMonitorItem.dm_attempts < _MAX_DM_ATTEMPTS,
                        ListingMonitorItem.seller_user_id.isnot(None),
                        ListingMonitorItem.seller_user_id != "",
                    )
                )
                .order_by(ListingMonitorItem.id.asc())
                .limit(_MAX_ITEMS_SCAN_PER_RUN)
            )
            rows = (await session.execute(stmt)).all()
            return [(r[0], r[1], r[2], r[3], r[4], r[5]) for r in rows]

    async def _get_task_dm_config(
        self, task_id: int, owner_id: Optional[int]
    ) -> Tuple[Optional[str], List[XYAccount], int]:
        """获取监控任务的私信内容、可用账号列表与每次最多处理条数（任务须未删除且启用）。

        候选账号来源（与自动下单定时任务对齐）：
        - 任务下单账号(order_account_ids)
        - + 兜底下单账号（本用户·本分类→本用户·无分类→管理员·本分类→管理员·无分类）
        按配置顺序合并去重、过滤未登录/已停用/不存在的账号。

        Returns: (dm_content, accounts, dm_batch_size)
        """
        async with async_session_maker() as session:
            task = (
                await session.execute(
                    select(
                        ListingMonitorTask.dm_content,
                        ListingMonitorTask.order_account_ids,
                        ListingMonitorTask.dm_batch_size,
                        ListingMonitorTask.category_id,
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
            task_account_ids = list(task[1] or [])
            batch_size = task[2] if task[2] and task[2] > 0 else 5
            category_id = task[3]
            if not dm_content:
                return dm_content, [], batch_size

            # 加载任务账号（按配置顺序、过滤失效）
            task_accounts_map: Dict[str, XYAccount] = {}
            if task_account_ids:
                task_accounts_map, _ = await load_xy_accounts_by_ids(session, task_account_ids)

        # 加载兜底账号（按分类 5 层链）；独立 session 内完成
        fallback_accounts_map, _ = await load_fallback_accounts(
            owner_id, category_id, log_prefix=self.task_name
        )

        # 合并：任务账号在前、兜底在后；按 account_id 去重
        ordered: List[XYAccount] = []
        seen: set[str] = set()
        for aid in task_account_ids:
            acc = task_accounts_map.get(aid)
            if acc and acc.account_id not in seen:
                seen.add(acc.account_id)
                ordered.append(acc)
        for aid, acc in fallback_accounts_map.items():
            if aid not in seen:
                seen.add(aid)
                ordered.append(acc)
        return dm_content, ordered, batch_size

    async def _send_for_item(
        self,
        pk: int,
        item_id: str,
        seller_user_id: str,
        content: str,
        account_ids: List[str],
        rr_start: int,
        disabled_accounts: set[str],
        strict: bool = False,
    ) -> str:
        """对单个商品发起私信。

        Args:
            account_ids: 候选账号ID列表。strict=True 时仅含下单账号一个，必须用它发，不换号。
            strict: 严格模式——只用下单成功的账号发私信；该账号不可用则本次跳过，
                    不换号、不全局停用、不累计尝试次数，留待下次任务再试。

        Returns: "sent" / "failed" / "no_account"
        """
        n = len(account_ids)
        tried = 0
        for offset in range(n):
            account_id = account_ids[(rr_start + offset) % n]
            if account_id in disabled_accounts:
                continue
            tried += 1
            res, send_fail_msg = await self._send_dm(
                account_id=account_id,
                seller_user_id=seller_user_id,
                item_id=item_id,
                content=content,
            )
            if res is None:
                if strict:
                    # 区分两种情况（以账号表是否存在为准）：
                    # 1) 账号已删除（账号表查无此账号）：私信永远无法进行 → 直接判失败、置终态不再重试
                    # 2) 账号仍存在（仅未启用/未启动/WebSocket未连接等暂时不可用）：记录原因后跳过，留待下次任务再试
                    if not await self._account_exists(account_id):
                        logger.warning(
                            f"【{self.task_name}】商品 {item_id} 下单账号 {account_id} 不存在(已被删除)，"
                            f"判为私信失败，置终态不再重试"
                        )
                        await self._mark_dm_account_missing(pk, account_id)
                        return "failed"
                    logger.warning(
                        f"【{self.task_name}】商品 {item_id} 下单账号 {account_id} 当前不可用(存在但未就绪)，"
                        f"严格模式不换号，本次跳过留待下次任务再试：{send_fail_msg}"
                    )
                    # 记录"等待重试"状态与原因，供前端展示（不计尝试次数、不置已私信，下轮继续重试）
                    await self._mark_dm_waiting(pk, account_id, send_fail_msg)
                    return "no_account"
                # 非严格（历史数据回退池）：本次停用该账号，换下一个，不计尝试次数
                disabled_accounts.add(account_id)
                logger.warning(
                    f"【{self.task_name}】账号 {account_id} 私信不可用，本次停用，尝试下一个账号：{send_fail_msg}"
                )
                continue

            send_status, send_fail_reason, chat_id = res
            if send_status == "failed":
                # 内容被拦截：累计尝试次数、清空 dm_account_id，本次不再换号
                await self._record_result(pk, send_status, send_fail_reason, account_id=None, chat_id=chat_id)
                return "failed"

            # 成功 / 超时未确认：标记已私信终态，记录成功账号与会话ID
            await self._record_result(pk, send_status, send_fail_reason, account_id=account_id, chat_id=chat_id)
            return "sent"

        # 所有候选账号都不可用
        return "no_account" if tried == 0 else "failed"

    async def _send_dm(
        self, account_id: str, seller_user_id: str, item_id: str, content: str
    ) -> Tuple[Optional[Tuple[str, Optional[str], Optional[str]]], Optional[str]]:
        """参照既有发起聊天逻辑：创建会话 + 发送私信（并等待发送结果）。

        Returns: (result, fail_reason)
            - 发送层失败（账号离线/未启动/会话创建失败等）：(None, 失败原因)，原因供前端展示与重试判断；
            - WebSocket 已发出（不论是否被服务端拦截）：((send_status, send_fail_reason, chat_id), None)。
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
            reason = f"创建会话异常：{exc}"
            logger.warning(f"【{self.task_name}】商品 {item_id} {reason}（账号 {account_id}）")
            return None, reason

        if not isinstance(create_res, dict) or not create_res.get("success"):
            msg = create_res.get("message") if isinstance(create_res, dict) else create_res
            reason = f"创建会话失败：{msg}"
            logger.warning(f"【{self.task_name}】商品 {item_id} {reason}（账号 {account_id}）")
            return None, reason

        chat_id = (create_res.get("data") or {}).get("chat_id")
        if not chat_id:
            reason = "创建会话响应缺少 chat_id"
            logger.warning(f"【{self.task_name}】商品 {item_id} {reason}（账号 {account_id}）")
            return None, reason

        # 2) 发送私信内容（等待服务端结果，识别安全拦截）
        send_url = f"{base_url}/internal/accounts/{account_id}/send-message"
        try:
            send_res = await http_client.post(
                send_url, json={"chat_id": chat_id, "message": content, "wait_result": True}
            )
        except Exception as exc:  # noqa: BLE001
            reason = f"发送私信异常：{exc}"
            logger.warning(f"【{self.task_name}】商品 {item_id} {reason}（账号 {account_id}）")
            return None, reason

        if not isinstance(send_res, dict) or not send_res.get("success"):
            msg = send_res.get("message") if isinstance(send_res, dict) else send_res
            reason = f"发送私信失败：{msg}"
            logger.warning(f"【{self.task_name}】商品 {item_id} {reason}（账号 {account_id}）")
            return None, reason

        data = send_res.get("data") or {}
        send_status = data.get("send_status") or "unknown"
        send_fail_reason = data.get("send_fail_reason")
        logger.info(
            f"【{self.task_name}】商品 {item_id} 私信已发出："
            f"账号={account_id}，卖家={seller_user_id}，chat_id={chat_id}，结果={send_status}"
        )
        return (send_status, send_fail_reason, chat_id), None

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

    async def _account_exists(self, account_id: str) -> bool:
        """判断下单账号是否仍存在于账号表（不论启用/登录状态）。

        用于严格模式区分「账号已删除」与「账号仍存在但暂不可用」：
        - 账号表（xy_accounts）查无此 account_id → 已被删除，私信无法进行；
        - 查到则视为存在（即便已停用/未登录/未启动，也只是暂时不可用，等待下次循环）。
        """
        if not account_id:
            return False
        async with async_session_maker() as session:
            found = (
                await session.execute(
                    select(XYAccount.id).where(XYAccount.account_id == account_id)
                )
            ).first()
            return found is not None

    async def _mark_dm_account_missing(self, pk: int, account_id: str) -> None:
        """下单账号已不存在（被删除）：私信永远无法进行，置为终态不再重试。

        - dm_attempts 置为上限，使查询条件 dm_attempts < _MAX_DM_ATTEMPTS 直接排除该商品；
        - is_dm_sent 保持 False（确实未私信），不写 dm_account_id；
        - 记录明确的失败原因供前端查看。
        """
        async with async_session_maker() as session:
            item = (
                await session.execute(
                    select(ListingMonitorItem).where(ListingMonitorItem.id == pk)
                )
            ).scalar_one_or_none()
            if not item:
                return
            item.dm_status = "failed"
            item.dm_fail_reason = f"下单账号 {account_id} 不存在(已被删除)，无法发送私信"[:500]
            item.dm_attempts = _MAX_DM_ATTEMPTS  # 置上限：直接终态，不再重试
            item.dm_account_id = None
            await session.commit()

    async def _mark_dm_waiting(self, pk: int, account_id: str, reason: Optional[str]) -> None:
        """下单账号暂时不可用（仍存在，仅未启用/未启动/未连接）：记录等待原因供前端展示。

        - dm_status 置为 "waiting"（非终态，前端展示"等待重试"）；
        - 记录失败/等待原因，便于排查；
        - 不累计 dm_attempts、不置 is_dm_sent，下轮任务继续重试；
        - 待账号就绪发送成功后，由 _record_result 覆盖为 success/已私信终态。
        """
        async with async_session_maker() as session:
            item = (
                await session.execute(
                    select(ListingMonitorItem).where(ListingMonitorItem.id == pk)
                )
            ).scalar_one_or_none()
            if not item:
                return
            item.dm_status = "waiting"
            item.dm_fail_reason = (
                f"下单账号 {account_id} 当前不可用，等待下次重试：{reason}" if reason
                else f"下单账号 {account_id} 当前不可用(未启用/未启动)，等待下次重试"
            )[:500]
            await session.commit()


# 全局实例
dm_send_task_service = DmSendTaskService(task_name="采集商品发送私信")
