"""
采集商品发送私信定时任务

功能：
1. 查询采集商品表中"最近2天下单成功(order_status=success 且 ordered_at>=今日00:00前推2天) 且
   卖家真实ID已补全(seller_user_id 不为空) 且 未私信(is_dm_sent=0)"的数据
2. 取私信内容(dm_content)；发私信使用"账号池"，按优先级失败就换下一个账号，
   直到池内所有账号都失败才算该条私信失败
3. 发起私信：参照既有发起聊天逻辑，调用 WebSocket 服务的
   create-chat 创建/获取与卖家的会话，再调用 send-message 发送私信内容
4. 发送成功后将该采集商品标记为已私信(is_dm_sent=1)，并记录成功私信使用的账号(dm_account_id)

账号池规则（优先级顺序，合并去重）：
- 下单账号(该商品 order_account_id)优先 → 当前用户的私信兜底账号 → 管理员的私信兜底账号
  （私信兜底取自专属的 DmFallbackAccountService 配置：本用户·本分类→本用户·无分类→管理员·本分类→管理员·无分类）
- 失败就换号：两类失败都换下一个账号继续——
  · 账号级不可用(离线/未就绪/会话创建失败/账号已删)：本次运行内停用该账号、换号
  · 内容被安全拦截(failed)：换号继续(账号对其它任务可能仍可用，不全局停用)
- 池内全部失败才算该条失败：
  · 至少一个账号把内容发到服务端被拦截 → 累计 dm_attempts、置 failed，达上限后停止重试
  · 全是账号级不可用(内容一次都没真正发出) → 置 waiting、不计 dm_attempts，下轮继续重试
- 发送成功/超时未确认：标记已私信(终态)，记录成功私信账号 dm_account_id

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
from common.services.order_account_loader import load_xy_accounts_by_ids
from common.services.dm_fallback_account_service import DmFallbackAccountService
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
            # 监控任务ID -> 兜底账号池（有序账号ID列表：当前用户兜底 → 管理员兜底，已滤掉不可用）
            task_accounts_cache: Dict[int, List[str]] = {}
            # 监控任务ID -> 每次最多处理条数（缓存）
            task_batch_cache: Dict[int, int] = {}
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
                base_pool = task_accounts_cache.get(task_id) or []
                batch_size = task_batch_cache.get(task_id, 5)

                # 未配置私信内容：跳过（不发，也不标记）
                if not dm_content:
                    skipped_no_config += 1
                    continue

                # 该任务本次已达每次最多处理条数：跳过
                if task_done.get(task_id, 0) >= batch_size:
                    skipped_batch_full += 1
                    continue

                # 组装本条商品的账号池（优先级保序去重）：
                # 下单账号(该商品 order_account_id) → 兜底池(当前用户 → 管理员)，再剔除本次运行已停用的死号
                account_ids: List[str] = []
                if order_account_id:
                    account_ids.append(order_account_id)
                for aid in base_pool:
                    if aid not in account_ids:
                        account_ids.append(aid)
                account_ids = [aid for aid in account_ids if aid not in disabled_accounts]

                # 池为空（无下单账号且无可用兜底账号）：置等待，留待下次任务再试
                if not account_ids:
                    no_account += 1
                    await self._mark_dm_waiting(pk, "", None)
                    continue

                result = await self._send_for_item(
                    pk=pk,
                    item_id=item_id,
                    seller_user_id=seller_user_id,
                    content=dm_content,
                    account_ids=account_ids,
                    disabled_accounts=disabled_accounts,
                )

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
    ) -> Tuple[Optional[str], List[str], int]:
        """获取监控任务的私信内容、兜底账号池与每次最多处理条数（任务须未删除且启用）。

        兜底账号池（有序去重、已滤掉未登录/已停用/不存在的账号）：
        - 兜底链：本用户·本分类→本用户·无分类→管理员·本分类→管理员·无分类（当前用户先于管理员）
        发私信时再由调用方把"该商品真实下单成功的账号(order_account_id)"置于此池最前。
        注意：不纳入任务的下单账号池(order_account_ids)——私信只认该商品真实下单的那一个账号。

        Returns: (dm_content, ordered_pool_account_ids, dm_batch_size)
        """
        async with async_session_maker() as session:
            task = (
                await session.execute(
                    select(
                        ListingMonitorTask.dm_content,
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
            batch_size = task[1] if task[1] and task[1] > 0 else 5
            category_id = task[2]
            if not dm_content:
                return dm_content, [], batch_size

            # 私信兜底链有序账号ID（本用户→管理员）；配置表未就绪/异常时降级为空，避免阻塞整轮私信
            try:
                fallback_ids = await DmFallbackAccountService(session).get_effective_fallback_account_ids(
                    owner_id, category_id
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"【{self.task_name}】加载用户{owner_id}私信兜底账号失败，本次按无兜底处理：{exc}")
                fallback_ids = []
            if not fallback_ids:
                return dm_content, [], batch_size

            # 过滤未登录/已停用/不存在的账号，并按兜底链的优先级顺序输出
            available_map, _ = await load_xy_accounts_by_ids(session, fallback_ids)
            ordered_pool = [aid for aid in fallback_ids if aid in available_map]
        return dm_content, ordered_pool, batch_size

    async def _send_for_item(
        self,
        pk: int,
        item_id: str,
        seller_user_id: str,
        content: str,
        account_ids: List[str],
        disabled_accounts: set[str],
    ) -> str:
        """对单个商品发起私信：按优先级顺序遍历账号池，失败就换号，全部失败才算失败。

        Args:
            account_ids: 候选账号ID列表（已按优先级保序：下单账号 → 当前用户兜底 → 管理员兜底）。
            disabled_accounts: 本次运行内已判定账号级不可用的账号集合（跨商品共享，避免重复尝试死号）。

        Returns: "sent" / "failed" / "no_account"
            - sent：某账号发送成功/超时未确认（置已私信终态）
            - failed：内容在某账号被服务端拦截且全池都未成功（累计 dm_attempts）
            - no_account：全是账号级不可用、内容一次都没真正发出（置 waiting，不计尝试，下轮再试）
        """
        sent_blocked = False  # 是否有账号把内容发到服务端却被拦截（区分"内容失败"与"账号不可用"）
        block_reason: Optional[str] = None  # 内容被拦截的原因（优先用于 failed 落库，避免被后续"账号不可用"覆盖）
        last_reason: Optional[str] = None
        last_account: str = ""
        for account_id in account_ids:
            if account_id in disabled_accounts:
                continue
            res, send_fail_msg = await self._send_dm(
                account_id=account_id,
                seller_user_id=seller_user_id,
                item_id=item_id,
                content=content,
            )
            if res is None:
                # 账号级不可用（离线/未就绪/会话创建失败/账号已删）：本次运行停用该账号，换下一个
                disabled_accounts.add(account_id)
                last_reason, last_account = send_fail_msg, account_id
                logger.warning(
                    f"【{self.task_name}】商品 {item_id} 账号 {account_id} 私信不可用，"
                    f"本次停用并尝试下一个账号：{send_fail_msg}"
                )
                continue

            send_status, send_fail_reason, chat_id = res
            if send_status == "failed":
                # 内容被安全拦截：换号继续（账号对其它任务可能仍可用，不全局停用）
                sent_blocked = True
                block_reason = send_fail_reason
                last_reason, last_account = send_fail_reason, account_id
                logger.warning(
                    f"【{self.task_name}】商品 {item_id} 账号 {account_id} 私信内容被拦截，"
                    f"尝试下一个账号：{send_fail_reason}"
                )
                continue

            # 成功 / 超时未确认：标记已私信终态，记录成功账号与会话ID
            await self._record_result(pk, send_status, send_fail_reason, account_id=account_id, chat_id=chat_id)
            return "sent"

        # 池内全部失败
        if sent_blocked:
            # 至少一个账号把内容发到服务端被拦截：累计 dm_attempts、置 failed，达上限后停止重试
            # （用拦截原因落库，而非可能更晚出现的"账号不可用"原因，保证状态与原因一致）
            await self._record_result(pk, "failed", block_reason, account_id=None)
            return "failed"
        # 全是账号级不可用（内容一次都没真正发出）：置 waiting、不计 dm_attempts，下轮继续重试
        await self._mark_dm_waiting(pk, last_account, last_reason)
        return "no_account"

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

    async def _mark_dm_waiting(self, pk: int, account_id: str, reason: Optional[str]) -> None:
        """账号池暂时不可用（账号未启用/未启动/未连接，或无可用账号）：记录等待原因供前端展示。

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
            base = f"私信账号 {account_id} 当前不可用" if account_id else "无可用私信账号"
            item.dm_fail_reason = (f"{base}，等待下次重试：{reason}" if reason else f"{base}，等待下次重试")[:500]
            await session.commit()


# 全局实例
dm_send_task_service = DmSendTaskService(task_name="采集商品发送私信")
