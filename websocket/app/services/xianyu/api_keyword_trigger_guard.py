"""API关键词触发检查与并发保护，锁持有到最终消息日志写入完成。"""
from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any
from uuid import uuid4

from loguru import logger

from common.db.redis_client import DistributedLock, get_redis_client
from common.services.api_keyword_trigger import check_api_keyword_trigger
from common.utils.time_utils import get_beijing_now_naive


class ApiKeywordTriggerGuard:
    """同用户、账号、买家和商品串行核对，避免并发消息同时消耗最后一个额度。"""

    def __init__(self, service, config: dict[str, Any], buyer_id: str, item_id: str):
        """保存真实触发上下文；参数为服务、规则、买家和商品，无返回值。"""
        self.service = service
        self.config = config
        self.buyer_id = buyer_id
        self.item_id = item_id
        self.trace = service._reply_trace_var.get()
        self.lock: DistributedLock | None = None
        self.renewal: asyncio.Task | None = None
        self.lost = False
        self.pending_log_key = ""
        self.enabled = bool(config.get("follow_order_quantity") or config.get("skip_same_message"))

    def _skip(self, reason: str, message: str, context: dict | None = None) -> None:
        """写入跳过原因及统计；参数为原因和中文说明，不发送API请求。"""
        self.trace.update(process_status="skipped", decision_reason=reason)
        self.trace.setdefault("context_snapshot", {}).update(context or {}, api_keyword_skipped=message)
        logger.info("API关键词跳过: account={}, buyer={}, item={}, rule_id={}, reason={}",
                    self.service.cookie_id, self.buyer_id, self.item_id, self.config["id"], message)

    async def check(self, message: str) -> bool:
        """加锁后查询成功日志与订单额度；参数为完整消息，返回是否允许执行。"""
        if not self.enabled:
            return True
        if self.trace is None or not self.buyer_id:
            raise ValueError("缺少消息日志或买家信息，无法安全核对API关键词触发限制")
        scope = [self.config["owner_id"], self.service.cookie_id, self.buyer_id, self.item_id]
        key = hashlib.sha256(json.dumps(scope, ensure_ascii=False).encode("utf-8")).hexdigest()
        self.lock = DistributedLock(f"api_keyword_trigger:{key}", expire=120)
        self.pending_log_key = f"api_keyword_pending_log:{key}"
        try:
            acquired = await self.lock.acquire(blocking=True, timeout=5)
        except Exception as exc:
            raise ValueError("API关键词触发锁服务不可用，请稍后重试") from exc
        if not acquired:
            self._skip("api_keyword_trigger_busy", "该买家商品的API消息正在处理中，请稍后重试")
            return False
        self.renewal = asyncio.create_task(self._renew())
        await self.ensure_owned()
        try:
            await self._recover_pending_log()
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("API关键词成功消息日志恢复服务不可用，已停止新请求，请稍后重试") from exc
        self.trace.setdefault("context_snapshot", {})["api_keyword_trigger_id"] = str(uuid4())
        result = await check_api_keyword_trigger(
            self.config, self.service.cookie_id, self.buyer_id, self.item_id,
            message, self.trace.get("matched_keyword") or "",
        )
        self.trace.setdefault("context_snapshot", {}).update(result["context"])
        if not result["allowed"]:
            self._skip(result["reason"], result["message"])
            return False
        return True

    async def _recover_pending_log(self) -> None:
        """持锁补记之前未落库的成功日志；失败拒绝新请求，返回后才核对触发次数。"""
        client = await get_redis_client()
        pending = await client.get(self.pending_log_key)
        if pending is None:
            return
        try:
            payload = json.loads(pending)
        except (ValueError, TypeError) as exc:
            raise ValueError("API关键词待恢复日志格式异常，请核对消息记录后重试") from exc
        context = payload.get("context_snapshot") if isinstance(payload, dict) else None
        if not isinstance(context, dict) or not context.get("api_keyword_trigger_id"):
            raise ValueError("API关键词待恢复日志格式异常，请核对消息记录后重试")
        log_id = await self.service.auto_reply_log_service.record_message(payload)
        if not log_id:
            raise ValueError("上一条API成功消息日志尚未写入，已停止新请求，请稍后重试")
        await self.ensure_owned()
        await client.delete(self.pending_log_key)
        logger.info("API关键词成功日志恢复完成: account={}, buyer={}, item={}, log_id={}",
                    self.service.cookie_id, self.buyer_id, self.item_id, log_id)

    async def finalize_log(self, log_id: int | None) -> None:
        """成功消息日志落库失败时暂存真实日志；参数为最终日志ID，后续触发先恢复再查询。"""
        if not self.enabled or self.trace is None or self.trace.get("process_status") != "success" or log_id:
            return
        if not self.pending_log_key:
            raise ValueError("API关键词成功消息缺少触发日志标识，请核对消息记录")
        self.trace.setdefault("context_snapshot", {}).setdefault("api_keyword_log_created_at", get_beijing_now_naive().isoformat())
        payload = self.service.auto_reply_log_service._normalize_json_value(self.trace)
        client = await get_redis_client()
        # 不设过期时间，成功日志补记完成后才移除，避免数据库故障期间重复消耗额度。
        saved = await client.set(self.pending_log_key, json.dumps(payload, ensure_ascii=False), nx=True)
        if not saved:
            raise ValueError("API关键词已有待恢复日志，已保留原记录，请核对消息日志")
        logger.error("API关键词成功消息日志未落库，已保留待恢复日志: account={}, buyer={}, item={}",
                     self.service.cookie_id, self.buyer_id, self.item_id)

    async def _renew(self) -> None:
        """长请求期间每30秒续期，无参数；丢锁时标记并停止后续业务操作。"""
        try:
            while True:
                await asyncio.sleep(30)
                await self.ensure_owned()
        except Exception:  # noqa: BLE001 -- 后台续期失败必须传递到主业务检查
            self.lost = True
            logger.exception("API关键词触发锁续期失败: account={}, buyer={}, item={}",
                             self.service.cookie_id, self.buyer_id, self.item_id)

    async def ensure_owned(self) -> None:
        """关键操作前确认触发锁有效，无参数；失效抛出中文业务错误。"""
        if self.enabled and (self.lost or self.lock is None or not await self.lock.extend()):
            raise ValueError("API关键词触发锁已失效，已停止处理，请核对消息日志")

    async def close(self) -> None:
        """消息日志提交后回收续期任务并释放触发锁，无参数和返回值。"""
        if self.renewal is not None:
            self.renewal.cancel()
            await asyncio.gather(self.renewal, return_exceptions=True)
        if self.lock is not None:
            try:
                if not await self.lock.release():
                    logger.error("API关键词触发锁释放失败: account={}, buyer={}, item={}",
                                 self.service.cookie_id, self.buyer_id, self.item_id)
            except Exception:  # noqa: BLE001 -- 释放异常需要记录且不得阻止上下文回收
                logger.exception("API关键词触发锁释放异常: account={}, buyer={}, item={}",
                                 self.service.cookie_id, self.buyer_id, self.item_id)
