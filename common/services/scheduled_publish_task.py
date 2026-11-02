"""
商品定时发布任务服务。

功能：
1. 每轮扫描启用的定时发布规则；
2. 每天首次进入规则时间范围时，为每个账号生成随机下次触发时间；
3. 到期后随机选择该规则、账号从未成功发布过的素材执行发布；
4. 记录每次发布结果，并提前推进下次触发时间避免重复执行。
"""
from __future__ import annotations

import asyncio
import hashlib
from contextlib import suppress
from datetime import date, datetime, time, timedelta
from pathlib import Path
from secrets import choice, randbelow
from typing import Any

from loguru import logger
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.redis_client import distributed_lock
from common.db.session import async_session_maker
from common.models.product_material import ProductMaterial
from common.models.scheduled_publish_record import ScheduledPublishRecord
from common.models.scheduled_publish_rule import ScheduledPublishRule
from common.models.scheduled_publish_trigger import ScheduledPublishTrigger
from common.models.xy_account import XYAccount
from common.services.auto_relist_utils import material_to_publish_data
from common.services.product_material_price import resolve_material_publish_price
from common.services.publish_execution_service import execute_single_publish
from common.utils.time_utils import get_beijing_now_naive


IN_QUERY_CHUNK_SIZE = 1000
INACTIVE_ACCOUNT_STATUSES = {"inactive", "disabled", "suspended", "deleted"}
PUBLISH_RESULT_SUCCESS = "success"
PUBLISH_RESULT_FAILURE = "failure"


class ScheduledPublishTask:
    """按规则执行商品定时发布。"""

    def __init__(self, static_dir: str | Path | None = None) -> None:
        """初始化任务。

        Args:
            static_dir: 商品发布服务使用的静态文件根目录。
        """
        self.static_dir = static_dir
        self._execution_lock = asyncio.Lock()

    async def execute(self) -> None:
        """执行一轮定时发布扫描，同一进程和多进程均禁止重叠执行。"""
        if self._execution_lock.locked():
            logger.warning("[商品定时发布] 上一轮仍在执行，本轮跳过")
            return

        async with self._execution_lock:
            try:
                async with distributed_lock(
                    "scheduled_publish:runner",
                    expire=600,
                    blocking=False,
                ) as lock:
                    if not lock.is_locked:
                        logger.info("[商品定时发布] 其他实例正在执行，本轮跳过")
                        return

                    lock_stop = asyncio.Event()
                    lock_lost = asyncio.Event()
                    heartbeat = asyncio.create_task(
                        self._keep_lock_alive(lock, lock_stop, lock_lost)
                    )
                    try:
                        await self._execute_enabled_rules(lock_lost)
                    finally:
                        lock_stop.set()
                        heartbeat.cancel()
                        with suppress(asyncio.CancelledError):
                            await heartbeat
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.opt(exception=exc).error("[商品定时发布] 执行失败: {}", exc)

    async def _keep_lock_alive(self, lock, stop: asyncio.Event, lost: asyncio.Event) -> None:
        """定期续租分布式锁，锁丢失后通知主循环停止领取新任务。"""
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=120)
            except asyncio.TimeoutError:
                try:
                    if not await lock.extend(600):
                        lost.set()
                        logger.error("[商品定时发布] 分布式锁续租失败，停止处理后续账号")
                        return
                except Exception as exc:
                    lost.set()
                    logger.opt(exception=exc).error(
                        "[商品定时发布] 分布式锁续租异常，停止处理后续账号: {}",
                        exc,
                    )
                    return

    async def _execute_enabled_rules(self, lock_lost: asyncio.Event) -> None:
        """读取启用规则并逐个处理。"""
        async with async_session_maker() as session:
            result = await session.execute(
                select(ScheduledPublishRule)
                .where(
                    ScheduledPublishRule.is_enabled.is_(True),
                    ScheduledPublishRule.is_deleted.is_(False),
                )
                .order_by(ScheduledPublishRule.id.asc())
            )
            rules = list(result.scalars().all())

        logger.info("[商品定时发布] 本轮读取启用规则 {} 条", len(rules))
        for rule in rules:
            if lock_lost.is_set():
                return
            now = get_beijing_now_naive().replace(microsecond=0)
            if not self._in_trigger_window(rule, now.time()):
                continue
            for account_id in self._stored_account_ids(rule.account_ids):
                if lock_lost.is_set():
                    return
                try:
                    await self._process_rule_account(rule, account_id)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.opt(exception=exc).error(
                        "[商品定时发布] 处理规则账号异常，继续处理后续账号: rule_id={}, account_id={}, error={}",
                        rule.id,
                        account_id,
                        exc,
                    )

    async def _process_rule_account(
        self,
        rule: ScheduledPublishRule,
        account_id: str,
    ) -> None:
        """初始化或执行单个规则账号的到期发布。"""
        now = get_beijing_now_naive().replace(microsecond=0)
        if not self._in_trigger_window(rule, now.time()):
            return

        async with async_session_maker() as session:
            trigger = await self._get_trigger_for_update(
                session,
                rule.owner_id,
                rule.id,
                account_id,
            )
            has_today_record = await self._has_today_record(
                session,
                rule.owner_id,
                rule.id,
                account_id,
                now.date(),
            )
            if trigger is None or trigger.is_deleted or trigger.next_trigger_at is None or (
                not has_today_record and trigger.schedule_date != now.date()
            ):
                await self._initialize_daily_trigger(session, trigger, rule, account_id, now)
                logger.info(
                    "[商品定时发布] 当天首次扫描仅初始化触发时间: rule_id={}, account_id={}, had_record={}",
                    rule.id,
                    account_id,
                    has_today_record,
                )
                return
            if trigger.next_trigger_at > now:
                return

            material = await self._choose_unpublished_material(session, rule, account_id)
            next_trigger_at = self._random_next_trigger(rule, now)
            trigger.next_trigger_at = next_trigger_at
            trigger.schedule_date = now.date()
            trigger.owner_id = rule.owner_id

            if material is None:
                record = ScheduledPublishRecord(
                    owner_id=rule.owner_id,
                    rule_id=rule.id,
                    account_id=account_id,
                    material_id=None,
                    publish_result=PUBLISH_RESULT_FAILURE,
                    failure_reason="无可用素材库",
                    publish_date=now.date(),
                    created_at=now,
                    updated_at=now,
                )
                session.add(record)
                await session.commit()
                await session.refresh(record)
                logger.warning(
                    "[商品定时发布] 无可发布素材，已记录失败并推进下次触发时间: rule_id={}, account_id={}, record_id={}, next_trigger_at={}",
                    rule.id,
                    account_id,
                    record.id,
                    next_trigger_at,
                )
                return

            record = ScheduledPublishRecord(
                owner_id=rule.owner_id,
                rule_id=rule.id,
                account_id=account_id,
                material_id=material.id,
                publish_result=PUBLISH_RESULT_FAILURE,
                failure_reason="发布处理中",
                publish_date=now.date(),
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)

        await self._publish_and_finish_record(rule, account_id, material, record.id)

    async def _publish_and_finish_record(
        self,
        rule: ScheduledPublishRule,
        account_id: str,
        material: ProductMaterial,
        record_id: int,
    ) -> None:
        """执行外部发布，并将最终结果写回定时发布记录。"""
        success = False
        failure_reason: str | None = None
        try:
            async with async_session_maker() as session:
                account_result = await session.execute(
                    select(XYAccount.status).where(
                        XYAccount.owner_id == rule.owner_id,
                        XYAccount.account_id == account_id,
                    )
                )
                account_status = account_result.scalar_one_or_none()
                if account_status is None:
                    failure_reason = "定时发布账号不存在或不属于规则用户"
                elif str(account_status).strip().lower() in INACTIVE_ACCOUNT_STATUSES:
                    failure_reason = "定时发布账号已停用"
                else:
                    item_data = resolve_material_publish_price(
                        material_to_publish_data(material)
                    )
                    result = await execute_single_publish(
                        session=session,
                        user_id=rule.owner_id,
                        account_id=account_id,
                        item_data=item_data,
                        static_root=self.static_dir,
                        publish_request_id=self._build_publish_request_id(
                            rule.id,
                            account_id,
                            material.id,
                        ),
                        enable_idempotency=True,
                    )
                    success = bool(result.get("success"))
                    failure_reason = None if success else str(
                        result.get("message") or "商品发布失败"
                    )
        except asyncio.CancelledError:
            failure_reason = "定时发布任务被取消，发布结果未知，请核查发布日志"
            await self._finish_record(record_id, False, failure_reason)
            raise
        except Exception as exc:
            failure_reason = f"定时发布异常：{exc}"
            logger.opt(exception=exc).error(
                "[商品定时发布] 发布异常: rule_id={}, account_id={}, material_id={}, error={}",
                rule.id,
                account_id,
                material.id,
                exc,
            )

        await self._finish_record(record_id, success, failure_reason)
        if success:
            logger.info(
                "[商品定时发布] 发布成功: rule_id={}, account_id={}, material_id={}, record_id={}",
                rule.id,
                account_id,
                material.id,
                record_id,
            )
        else:
            logger.warning(
                "[商品定时发布] 发布失败: rule_id={}, account_id={}, material_id={}, record_id={}, reason={}",
                rule.id,
                account_id,
                material.id,
                record_id,
                failure_reason,
            )

    @staticmethod
    async def _finish_record(
        record_id: int,
        success: bool,
        failure_reason: str | None,
    ) -> None:
        """使用独立会话保存发布记录最终状态。"""
        async with async_session_maker() as session:
            result = await session.execute(
                select(ScheduledPublishRecord).where(ScheduledPublishRecord.id == record_id)
            )
            record = result.scalar_one_or_none()
            if record is None:
                logger.error("[商品定时发布] 发布记录不存在，无法回写: record_id={}", record_id)
                raise RuntimeError(f"定时发布记录不存在，无法保存发布结果：record_id={record_id}")
            record.publish_result = (
                PUBLISH_RESULT_SUCCESS if success else PUBLISH_RESULT_FAILURE
            )
            record.failure_reason = None if success else (failure_reason or "商品发布失败")
            record.updated_at = get_beijing_now_naive().replace(microsecond=0)
            await session.commit()

    @staticmethod
    async def _get_trigger_for_update(
        session: AsyncSession,
        owner_id: int,
        rule_id: int,
        account_id: str,
    ) -> ScheduledPublishTrigger | None:
        """加锁读取规则账号唯一触发记录。"""
        result = await session.execute(
            select(ScheduledPublishTrigger)
            .where(
                ScheduledPublishTrigger.owner_id == owner_id,
                ScheduledPublishTrigger.rule_id == rule_id,
                ScheduledPublishTrigger.account_id == account_id,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def _has_today_record(
        session: AsyncSession,
        owner_id: int,
        rule_id: int,
        account_id: str,
        publish_date: date,
    ) -> bool:
        """判断规则账号当天是否已有实际发布尝试记录。"""
        result = await session.execute(
            select(
                exists().where(
                    ScheduledPublishRecord.owner_id == owner_id,
                    ScheduledPublishRecord.rule_id == rule_id,
                    ScheduledPublishRecord.account_id == account_id,
                    ScheduledPublishRecord.publish_date == publish_date,
                )
            )
        )
        return bool(result.scalar())

    async def _initialize_daily_trigger(
        self,
        session: AsyncSession,
        trigger: ScheduledPublishTrigger | None,
        rule: ScheduledPublishRule,
        account_id: str,
        now: datetime,
    ) -> None:
        """每天第一次扫描仅初始化随机下次触发时间。"""
        next_trigger_at = self._random_next_trigger(rule, now)
        if trigger is None:
            trigger = ScheduledPublishTrigger(
                owner_id=rule.owner_id,
                rule_id=rule.id,
                account_id=account_id,
                schedule_date=now.date(),
                next_trigger_at=next_trigger_at,
                created_at=now,
                updated_at=now,
            )
            session.add(trigger)
        else:
            trigger.owner_id = rule.owner_id
            trigger.schedule_date = now.date()
            trigger.next_trigger_at = next_trigger_at
            trigger.is_deleted = False
            trigger.updated_at = now
        await session.commit()

    async def _choose_unpublished_material(
        self,
        session: AsyncSession,
        rule: ScheduledPublishRule,
        account_id: str,
    ) -> ProductMaterial | None:
        """随机选择本规则、本账号从未成功发布过的有效素材。"""
        success_result = await session.execute(
            select(ScheduledPublishRecord.material_id).where(
                ScheduledPublishRecord.owner_id == rule.owner_id,
                ScheduledPublishRecord.rule_id == rule.id,
                ScheduledPublishRecord.account_id == account_id,
                ScheduledPublishRecord.publish_result == PUBLISH_RESULT_SUCCESS,
            )
        )
        published_ids = {
            int(item) for item in success_result.scalars().all() if item is not None
        }
        candidate_ids = [
            item
            for item in self._stored_material_ids(rule.material_ids)
            if item not in published_ids
        ]
        if not candidate_ids:
            return None

        materials: list[ProductMaterial] = []
        for chunk in self._chunked(candidate_ids):
            result = await session.execute(
                select(ProductMaterial).where(
                    ProductMaterial.user_id == rule.owner_id,
                    ProductMaterial.id.in_(chunk),
                    ProductMaterial.is_deleted.is_(False),
                )
            )
            materials.extend(result.scalars().all())
        return choice(materials) if materials else None

    @staticmethod
    def _random_next_trigger(rule: ScheduledPublishRule, now: datetime) -> datetime:
        """按规则随机分钟范围计算下次触发时间。"""
        minimum = max(1, int(rule.interval_min_minutes or 1))
        maximum = max(minimum, int(rule.interval_max_minutes or minimum))
        minutes = minimum + randbelow(maximum - minimum + 1)
        return (now + timedelta(minutes=minutes)).replace(microsecond=0)

    @staticmethod
    def _build_publish_request_id(
        rule_id: int,
        account_id: str,
        material_id: int,
    ) -> str:
        """生成规则账号素材维度的稳定发布幂等请求号。"""
        digest = hashlib.sha256(
            f"{rule_id}\0{account_id}\0{material_id}".encode("utf-8")
        ).hexdigest()[:40]
        return f"scheduled-publish:{digest}"

    @staticmethod
    def _in_trigger_window(rule: ScheduledPublishRule, current_time: time) -> bool:
        """判断当前北京时间是否位于规则每日触发范围内。"""
        if not rule.trigger_start_time or not rule.trigger_end_time:
            return False
        current_minutes = current_time.hour * 60 + current_time.minute
        start_minutes = rule.trigger_start_time.hour * 60 + rule.trigger_start_time.minute
        end_minutes = rule.trigger_end_time.hour * 60 + rule.trigger_end_time.minute
        return start_minutes <= current_minutes <= end_minutes

    @staticmethod
    def _stored_account_ids(value: Any) -> list[str]:
        """安全读取规则账号ID并去重。"""
        if not isinstance(value, list):
            return []
        items = (str(item).strip() for item in value if item is not None)
        return list(dict.fromkeys(item for item in items if item))

    @staticmethod
    def _stored_material_ids(value: Any) -> list[int]:
        """安全读取规则素材ID，忽略非法历史值。"""
        if not isinstance(value, list):
            return []
        result: list[int] = []
        seen: set[int] = set()
        for item in value:
            try:
                material_id = int(item)
            except (TypeError, ValueError):
                continue
            if material_id > 0 and material_id not in seen:
                seen.add(material_id)
                result.append(material_id)
        return result

    @staticmethod
    def _chunked(values: list[int]) -> list[list[int]]:
        """拆分大批量素材ID，避免单条IN参数过多。"""
        return [
            values[offset:offset + IN_QUERY_CHUNK_SIZE]
            for offset in range(0, len(values), IN_QUERY_CHUNK_SIZE)
        ]
