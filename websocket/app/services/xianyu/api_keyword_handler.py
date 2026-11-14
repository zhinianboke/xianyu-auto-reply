"""执行API关键词：下单校验、API回复，以及成功发送后的免拼和确认发货。"""
from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

from loguru import logger

from app.services.xianyu.api_keyword_lock import api_keyword_order_lock
from app.services.xianyu.api_keyword_trigger_guard import ApiKeywordTriggerGuard
from app.services.xianyu.resource_manager import pause_manager
from common.services.api_keyword_client import request_api_keyword
from common.services.api_keyword_runtime import (
    API_DELIVERY_METADATA_KEY,
    FULFILLED_ORDER_STATUSES,
    get_api_confirmation_order,
    get_pending_api_order,
    get_trigger_api_order,
    save_api_order_checkpoint,
    save_api_order_delivery,
)
from common.services.delivery_utils import is_shipping_result_ok


class ApiKeywordDeliveryConflict(ValueError):
    """订单已有发货结果的业务冲突，只记录原因与上下文，无需异常堆栈。"""


class ApiKeywordHandler:
    """使用当前自动回复实例发送API结果，不重新取卡券或触发完整自动发货流程。"""

    def __init__(self, reply_service, websocket, chat_id: str, buyer_id: str, item_id: str):
        """保存发送上下文，订单及配置均使用数据快照，外部请求不占用数据库事务。"""
        self.service = reply_service
        self.instance = reply_service.xianyu_instance
        self.websocket = websocket
        self.chat_id = chat_id
        self.buyer_id = buyer_id
        self.item_id = item_id
        self.trace = reply_service._reply_trace_var.get()
        self.results: list[dict[str, Any]] = []
        self.order: dict[str, Any] | None = None
        self.content = ""
        self.confirm_attempted = False
        self.checkpoint_saved = False
        self.send_checked = False
        self.sent_segments: set[int] = set()
        self.signature = ""
        self.trigger_guard = ApiKeywordTriggerGuard(reply_service, {}, buyer_id, item_id)

    async def close(self) -> None:
        """最终消息日志落库后释放触发保护，无参数和返回值。"""
        await self.trigger_guard.close()

    async def finalize_log(self, log_id: int | None) -> None:
        """核对最终日志是否落库；成功回复写库失败时保留可恢复日志，防止再次调用API。"""
        try:
            await self.trigger_guard.finalize_log(log_id)
        except Exception:
            logger.exception("API关键词成功消息日志及恢复记录保存失败: account={}, buyer={}, item={}",
                             self.service.cookie_id, self.buyer_id, self.item_id)
            raise

    def _context(self, **values) -> None:
        """记录运行结果到现有自动回复日志上下文，供后台查看。"""
        if self.trace is not None:
            self.trace.setdefault("context_snapshot", {}).update(values)

    async def _lookup_order(self, config, order_id=None, *, for_trigger: bool = False):
        """按所属用户、账号、买家及商品核对订单，触发资格允许已发货及已完成。

        Args:
            config: 当前API配置，包含所属用户ID。
            order_id: 可选的指定订单主键。
            for_trigger: 是否只检查下单资格；默认仍只读取待发货订单供发货使用。
        Returns:
            符合对应状态要求的订单快照，没有符合条件的订单时返回None。
        """
        lookup = get_trigger_api_order if for_trigger else get_pending_api_order
        return await lookup(
            config["owner_id"], self.service.cookie_id, self.buyer_id, self.item_id, order_id,
        )

    async def _send(self, content: str, *, enforce_trigger: bool = False) -> None:
        """通过公共发送方法发送纯文本，不解释API返回的内部图片指令。"""
        send_options = {"before_send": self.trigger_guard.ensure_owned} if enforce_trigger and self.trigger_guard.enabled else {}
        self.results.extend(await self.service._send_text_with_separator(
            self.websocket, self.chat_id, self.buyer_id, content, **send_options,
        ))

    def _restore_checkpoint(self, current) -> None:
        """校验订单既有API结果，避免与其他发货流程混用，重试复用完整结果。"""
        checkpoint = (current.get("metadata_json") or {}).get(API_DELIVERY_METADATA_KEY)
        if checkpoint:
            if not isinstance(checkpoint, dict) or type(checkpoint.get("send_checked", False)) is not bool:
                raise ValueError("订单API发送检测进度格式异常，请核对发货记录")
            if (checkpoint.get("signature") != self.signature
                    or not isinstance(checkpoint.get("content"), str) or not checkpoint["content"].strip()):
                raise ApiKeywordDeliveryConflict("该订单已有其他API发货结果，请先核对原发货记录")
            self.content = checkpoint["content"]
            self.send_checked = bool(checkpoint.get("send_checked"))
            segments = checkpoint.get("sent_segments", [])
            if not isinstance(segments, list) or any(type(index) is not int or index < 1 for index in segments):
                raise ValueError("订单API发送进度格式异常，请核对发货记录")
            self.sent_segments = set(segments)
            self.checkpoint_saved = True
            self._context(api_keyword_reused_result=True)
        elif current.get("card_only_delivered"):
            raise ApiKeywordDeliveryConflict("该订单已由其他发货流程处理，请先核对发货记录")
        elif str(current.get("delivery_content") or "").strip():
            raise ApiKeywordDeliveryConflict("该订单已有发货内容，请先核对原发货记录")

    async def _pre_check(self, current) -> None:
        """复用自动发货拦截入口；下单限制分支在取API结果之前执行。"""
        shipping = getattr(self.instance, "auto_delivery_handler", None)
        if shipping is None:
            raise ValueError("自动发货服务未初始化，无法同步确认发货")
        pre_check = await shipping.pre_delivery_check_and_close(
            websocket=self.websocket, order_no=current["order_no"], buyer_id=self.buyer_id,
            chat_id=self.chat_id, item_id=self.item_id,
            log_prefix=f"【{self.service.cookie_id}】API关键词",
            strict=True,
        )
        self._context(api_keyword_delivery_pre_check=pre_check)
        if not isinstance(pre_check, dict) or pre_check.get("action") not in {"allow", "block", "card_only"}:
            raise ValueError("禁止发货检查未返回有效结果，已停止同步确认发货")
        if pre_check["action"] != "allow":
            raise ValueError(pre_check.get("reason_text") or "命中账号禁止发货规则，已停止同步确认发货")

    async def _request_and_send(self, config, message: str, ensure_owned=None) -> bool:
        """请求API、保存响应日志并发送；人工暂停或消息发送失败时停止后续确认。"""
        await self.trigger_guard.ensure_owned()
        if ensure_owned is not None:
            await ensure_owned()
        if not self.content:
            self.content = await request_api_keyword(config, self.item_id, message)
        await self.trigger_guard.ensure_owned()
        segments = self.service._build_text_reply_segments(self.content)
        if not segments:
            raise ValueError("API结果没有可发送的文本内容")
        if any(index > len(segments) for index in self.sent_segments):
            raise ValueError("订单API发送进度与结果不一致，请核对发货记录")
        if self.trace is not None:
            self.trace.update(reply_mode="text", reply_text=self.content,
                              reply_segments=segments)
        if self.order is not None and config["sync_confirm_delivery"] and config["trigger_after_order"]:
            await ensure_owned()
            await save_api_order_checkpoint(self.order, config["id"], self.signature, self.content)
            self.checkpoint_saved = True
        if pause_manager.is_chat_paused(self.chat_id, self.service.cookie_id):
            self._context(api_keyword_skipped="API请求结束后会话被人工暂停")
            if self.trace is not None:
                self.trace.update(process_status="skipped", decision_reason="chat_paused_after_delay")
            return False
        if ensure_owned is not None:
            await ensure_owned()
        if self.send_checked:
            # 先前已发送且未被拦截，本次只重试确认，避免重复发送卡密。
            if self.trace is not None:
                self.trace.update(process_status="success", decision_reason="reply_sent", send_status="success")
            return True
        if not config["sync_confirm_delivery"]:
            # 普通API回复沿用公共发送的分段间隔；进度持久化仅用于同步发货分支。
            await self.trigger_guard.ensure_owned()
            await self._send(self.content, enforce_trigger=True)
            if not self.service._is_send_results_success(self.results):
                raise ValueError(self.service._get_send_error_message(self.results) or "API结果发送失败")
            if self.trigger_guard.enabled:
                # 开启成功日志限制时，先等发送检测再落库，避免被拦截消息短暂占用次数。
                await self._check_send_rejection()
            return True
        for segment in segments:
            if segment["index"] in self.sent_segments:
                continue
            if self._confirmation_paused():
                return False
            await self.trigger_guard.ensure_owned()
            if ensure_owned is not None:
                await ensure_owned()
                if await self._lookup_order(config, self.order["id"]) is None:
                    raise ValueError("订单状态已变化，已停止发送API结果，请核对订单")
            start = len(self.results)
            await self._send(segment["content"], enforce_trigger=True)
            current_results = self.results[start:]
            if not self.service._is_send_results_success(current_results):
                raise ValueError(self.service._get_send_error_message(current_results) or "API结果发送失败")
            if config["sync_confirm_delivery"]:
                await self._check_send_rejection(current_results, mark_complete=False)
                if self.trace is not None:
                    self.trace["_api_send_checked"] = True
                self.sent_segments.add(segment["index"])
                if self.checkpoint_saved:
                    await ensure_owned()
                    await save_api_order_checkpoint(
                        self.order, config["id"], self.signature, self.content,
                        sent_segments=sorted(self.sent_segments),
                    )
        if config["sync_confirm_delivery"]:
            if self.checkpoint_saved:
                await ensure_owned()
                await save_api_order_checkpoint(self.order, config["id"], self.signature, self.content, True)
            self.send_checked = True
            if self.trace is not None:
                self.trace["_api_send_checked"] = True
                if not self.results:
                    # 最后一段进度已落库但确认进度未写入时，恢复无需重发，也不能记为未匹配。
                    self.trace.update(process_status="success", decision_reason="reply_sent", send_status="success")
        return True

    async def _check_send_rejection(self, send_results=None, *, mark_complete: bool = True) -> None:
        """沿用自动发货的发送拦截检测；任一分段被拦截时禁止确认发货。"""
        results = self.results if send_results is None else send_results
        wait_fn = getattr(self.instance, "wait_send_reject_reason", None)
        if not callable(wait_fn):
            raise ValueError("消息发送结果检测不可用，已停止同步确认发货")  # noqa: TRY004 -- 中文业务错误
        pending = [result for result in results if result.get("send_future") is not None]
        if len(pending) != len(results):
            raise ValueError("API结果缺少发送回执检测引用，已停止同步确认发货")
        reasons = await asyncio.gather(*[
            self._wait_send_result(wait_fn, result) for result in pending
        ], return_exceptions=True)
        for result, reason in zip(pending, reasons):
            result.pop("send_future", None)
            if isinstance(reason, BaseException):
                reason = f"消息发送结果检测失败：{reason}"
            if reason:
                result.update(success=False, error_message=reason)
        if not self.service._is_send_results_success(results):
            raise ValueError(self.service._get_send_error_message(results) or "API结果发送被拦截")
        if mark_complete and self.trace is not None:
            self.trace["_api_send_checked"] = True
        if mark_complete:
            self.send_checked = True

    async def _wait_send_result(self, wait_fn, result):
        """保留原回执引用，识别公共检测方法内部捕获的异常；超时仍沿用未拦截语义。"""
        future = result["send_future"]
        # 公共检测的wait_for超时会取消传入Future，用shield区分超时与原回执失败。
        guarded = asyncio.shield(future)
        try:
            reason = await wait_fn(guarded, result.get("mid"))
            if future.cancelled():
                raise ValueError("消息发送回执已取消，已停止同步确认发货")
            if future.done():
                error = future.exception()
                if error is not None:
                    raise ValueError(f"消息发送回执异常：{error}") from error
            return reason
        finally:
            # 检测方法异常或任务取消时也回收原引用，避免shield留下无人等待的Future。
            if not future.done():
                future.cancel()
            elif not future.cancelled():
                future.exception()
            if not guarded.done():
                guarded.cancel()
            elif not guarded.cancelled():
                guarded.exception()

    async def _confirm(self, config, ensure_owned) -> None:
        """重新核对订单并调用既有免拼/确认发货；只有平台成功才保存为已发货。"""
        if self._confirmation_paused():
            return
        await self.trigger_guard.ensure_owned()
        await ensure_owned()
        current = await get_api_confirmation_order(self.order)
        if current is None:
            raise ValueError("订单已不处于待发货状态，已停止同步确认发货，请核对订单")
        handler = getattr(self.instance, "auto_delivery_handler", None)
        if handler is None:
            raise ValueError("自动发货服务未初始化，无法同步确认发货")
        await self._pre_check(current)
        await self.trigger_guard.ensure_owned()
        await ensure_owned()
        current = await get_api_confirmation_order(self.order)
        if current is None:
            raise ValueError("订单状态已变化，已停止同步确认发货，请核对订单")
        if self._confirmation_paused():
            return
        self.confirm_attempted = True
        # API关键词的同步开关是此规则的显式发货配置，覆盖账号只发卡券/同意后发货模式。
        if current["is_bargain"] and current["status"] not in FULFILLED_ORDER_STATUSES:
            await self.trigger_guard.ensure_owned()
            free_result = await handler.auto_freeshipping(
                current["order_no"], self.item_id, self.buyer_id, force=True,
            )
            self._context(api_keyword_freeshipping_result=free_result)
            if not is_shipping_result_ok(free_result):
                raise ValueError(f"免拼失败：{(free_result or {}).get('error') or (free_result or {}).get('message') or '接口返回失败'}")
        await ensure_owned()
        # 免拼可能已完成平台发货，由确认接口核实成功；退款/关闭仍停止，不换订单。
        current = await get_api_confirmation_order(self.order)
        if current is None:
            raise ValueError("订单状态已变化，已停止确认发货，请核对订单")
        if self._confirmation_paused():
            return
        await self.trigger_guard.ensure_owned()
        confirm_result = await handler.auto_confirm(current["order_no"], self.item_id, force=True)
        self._context(api_keyword_confirm_result=confirm_result)
        if not is_shipping_result_ok(confirm_result):
            raise ValueError(f"确认发货失败：{(confirm_result or {}).get('error') or (confirm_result or {}).get('message') or '接口返回失败'}")
        handler.mark_delivery_sent(current["order_no"])
        await save_api_order_delivery(current, self.content)
        self._context(api_keyword_delivery_status="已发货")

    def _confirmation_paused(self) -> bool:
        """等待消息回执或平台预检查期间人工介入时，停止后续免拼/确认并保留可重试结果。"""
        if not pause_manager.is_chat_paused(self.chat_id, self.service.cookie_id):
            return False
        self._context(api_keyword_delivery_skipped="会话已被人工暂停，已停止同步确认发货")
        if self.trace is not None:
            self.trace["_api_confirmation_paused"] = True
            self.trace.update(process_status="skipped", decision_reason="chat_paused_after_delay")
        return True

    async def _process_order(self, config, message, ensure_owned) -> None:
        """持锁处理符合下单资格的订单，待发货恢复并确认，已发货/已完成仅回复。

        Args:
            config: 当前API及同步确认发货配置。
            message: 买家的完整触发消息。
            ensure_owned: 检查订单锁仍有效的异步方法。
        Returns:
            无返回值；回复结果及处理上下文保存在当前处理实例中。
        """
        current = await self._lookup_order(config, self.order["id"])
        if current is None:
            current = await get_api_confirmation_order(self.order)
            if current is None:
                raise ValueError("订单已不处于待发货状态，请核对订单后重试")
        self.order = current
        if current["status"] in FULFILLED_ORDER_STATUSES:
            checkpoint = (current.get("metadata_json") or {}).get(API_DELIVERY_METADATA_KEY)
            needs_recovery = bool(
                checkpoint and current.get("card_only_delivered")
                and not str(current.get("delivery_content") or "").strip()
            )
            if not needs_recovery:
                # 已完成发货的订单仍具备下单资格，仅返回本次API结果，不覆盖原发货记录。
                await self._request_and_send({**config, "sync_confirm_delivery": False}, message, ensure_owned)
                self._context(api_keyword_delivery_skipped="订单已发货或已完成，仅回复API结果，跳过重复确认发货")
                return
            self._restore_checkpoint(current)
            if not self.checkpoint_saved or not self.send_checked:
                raise ValueError("订单状态已变化，无法核实API结果完整发送，请核对发货记录")
            # 平台已发货但本地保存曾失败，只核实平台并补结果，禁止重新请求或发送。
            if self.trace is not None:
                self.trace.update(reply_mode="text", reply_text=self.content, process_status="success",
                                  decision_reason="reply_sent", send_status="success")
            await self._confirm(config, ensure_owned)
            return
        self._restore_checkpoint(current)
        if config["trigger_after_order"]:
            await self._pre_check(current)
            await ensure_owned()
            if await self._lookup_order(config, current["id"]) is None:
                raise ValueError("订单状态已变化，已停止调用API，请核对订单")
        if await self._request_and_send(config, message, ensure_owned):
            await self._confirm(config, ensure_owned)

    async def run(self, config: dict[str, Any], message: str) -> list[dict[str, Any]]:
        """先核对触发限制再执行API及发货，返回真实结果；失败给买家提示并写日志。"""
        self.trigger_guard = ApiKeywordTriggerGuard(self.service, config, self.buyer_id, self.item_id)
        self._context(api_keyword_rule_id=config["id"],
                      api_keyword_trigger_after_order=config["trigger_after_order"],
                      api_keyword_sync_confirm_delivery=config["sync_confirm_delivery"],
                      api_keyword_follow_order_quantity=config.get("follow_order_quantity", False),
                      api_keyword_skip_same_message=config.get("skip_same_message", False))
        try:
            if not await self.trigger_guard.check(message):
                return self.results
            # 触发限制不改变API请求或发货配置，排除新开关可兼容升级前的订单恢复记录。
            delivery_config = {key: value for key, value in config.items() if key not in {"follow_order_quantity", "skip_same_message"}}
            self.signature = hashlib.sha256(json.dumps(delivery_config, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
            if config["trigger_after_order"]:
                self.order = await self._lookup_order(config, for_trigger=True)
                if self.order is None:
                    raise ValueError("未找到您在该商品下的有效订单（待发货、已发货或已完成），请先下单并完成付款")
                self._context(api_keyword_order_no=self.order["order_no"])
                if self.trace is not None:
                    self.trace["order_no"] = self.order["order_no"]
                if not config["sync_confirm_delivery"]:
                    # 只需检查下单的回复不申请发货锁，也不依赖Redis发货锁服务。
                    await self._request_and_send(config, message)
                    return self.results
                async with api_keyword_order_lock(self.instance, self.order["order_no"]) as ensure_owned:
                    await self._process_order(config, message, ensure_owned)
            elif config["sync_confirm_delivery"]:
                # 下单限制关闭时先返回本次API结果，订单查询只服务于同步发货。
                if not await self._request_and_send(config, message):
                    return self.results
                if not self.send_checked:
                    await self._check_send_rejection()
                if not self.buyer_id or not self.item_id or self.item_id == "未知商品":
                    self._context(api_keyword_delivery_skipped="缺少买家或商品信息，跳过同步确认发货")
                    return self.results
                self.order = await self._lookup_order(config)
                if self.order is None:
                    self._context(api_keyword_delivery_skipped="没有该商品的待发货订单，跳过同步确认发货")
                    logger.info("API关键词已回复，未找到待发货订单: account={}, buyer={}, item={}",
                                self.service.cookie_id, self.buyer_id, self.item_id)
                    return self.results
                if self.trace is not None:
                    self.trace["order_no"] = self.order["order_no"]
                async with api_keyword_order_lock(self.instance, self.order["order_no"]) as ensure_owned:
                    await self._confirm(config, ensure_owned)
            else:
                await self._request_and_send(config, message)
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
            logger.opt(exception=not isinstance(exc, ApiKeywordDeliveryConflict)).error(
                "API关键词执行失败: account={}, buyer={}, item={}, rule_id={}, order_no={}, error_type={}, error={}",
                self.service.cookie_id, self.buyer_id, self.item_id, config["id"],
                (self.order or {}).get("order_no"), type(exc).__name__, error,
            )
            self._context(api_keyword_error=error)
            if self.trace is not None:
                self.trace["_api_keyword_error"] = error
            if self.order is not None and self.checkpoint_saved:
                self._context(api_keyword_recovery="重新发送同一API关键词可复用已保存结果并重试确认")
            if self.order is not None and (self.confirm_attempted or self.checkpoint_saved):
                try:
                    await save_api_order_delivery(self.order, self.content, error)
                except Exception:  # noqa: BLE001
                    logger.exception("API关键词失败原因保存失败: order_no={}", self.order["order_no"])
            try:
                if self.trace is not None and not self.content:
                    prompt = f"API关键词处理失败：{error}"
                    self.trace.update(reply_mode="text", reply_text=prompt,
                                      reply_segments=self.service._build_text_reply_segments(prompt))
                await self._send(f"API关键词处理失败：{error}")
            except Exception:  # noqa: BLE001
                logger.exception("API关键词错误提示发送失败: rule_id={}", config["id"])
                self.results.append({"success": False, "mode": "text", "error_message": error})
        return self.results
