"""用户管理中的结算记录：复用个人分页查询，字典展示、行锁校验和结果修改审计。"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.schemas.admin_settlement import AdminSettlementUpdate
from app.services.settlement_service import SettlementService, serialize_settlement_record
from common.db.retry import with_db_retry
from common.models.data_dictionary import XYDataDictionary
from common.models.settlement_record import (
    SETTLEMENT_PAYMENT_TYPE_DICT, SETTLEMENT_STATUS_DICT, SETTLEMENT_STATUSES, SettlementRecord,
)
from common.models.user import User
from common.utils.time_utils import get_beijing_now_naive


def settlement_revision(item: dict[str, Any]) -> str:
    """对真实记录快照计算版本，避免同一秒或同一状态下的并发编辑覆盖。"""
    raw = json.dumps(item, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class AdminSettlementService:
    """仅通过管理员路由调用；查询/更新始终同时绑定用户与记录编号。"""

    def __init__(self, session: AsyncSession, log=logger):
        """复用项目请求会话与日志对象，不创建额外数据库连接池。"""
        self.session = session
        self.log = log

    async def _require_user(self, user_id: int) -> None:
        """检查目标用户真实存在，保留停用用户的历史结算查询能力。"""
        if (await self.session.execute(select(User.id).where(User.id == user_id))).scalar_one_or_none() is None:
            raise ValueError("用户不存在")

    async def _options(self) -> dict[str, list[dict[str, Any]]]:
        """查询结果/收款方式中文字典；缺失配置报错，不返回硬编码备用名称。"""
        rows = (await self.session.execute(
            select(XYDataDictionary).where(XYDataDictionary.dict_type.in_(
                [SETTLEMENT_STATUS_DICT, SETTLEMENT_PAYMENT_TYPE_DICT]
            )).order_by(XYDataDictionary.sort_order, XYDataDictionary.id)
        )).scalars().all()
        options: dict[str, list[dict[str, Any]]] = {"statuses": [], "payment_types": []}
        for row in rows:
            key = "statuses" if row.dict_type == SETTLEMENT_STATUS_DICT else "payment_types"
            # 历史字典值仍展示中文，但只允许选择参数模型支持的结算结果。
            enabled = bool(row.enabled) and (key != "statuses" or row.dict_value in SETTLEMENT_STATUSES)
            options[key].append({"value": row.dict_value, "label": row.dict_label, "enabled": enabled})
        if not set(SETTLEMENT_STATUSES).issubset({item["value"] for item in options["statuses"]}):
            raise ValueError("结算结果字典未初始化，请更新并重启后端服务")
        if not {"alipay", "wechat"}.issubset({item["value"] for item in options["payment_types"]}):
            raise ValueError("结算收款方式字典未初始化，请更新并重启后端服务")
        return options

    def _display(self, item: dict[str, Any], options: dict) -> dict[str, Any]:
        """补充中文名称及并发版本；历史未知值按原值展示，不伪造状态。"""
        statuses = {option["value"]: option["label"] for option in options["statuses"]}
        payments = {option["value"]: option["label"] for option in options["payment_types"]}
        payment_type = item["payment_type"] or ("alipay" if item["alipay_id"] else "")
        return {**item, "revision": settlement_revision(item),
                "status_label": statuses.get(item["status"], item["status"]),
                "payment_type_label": payments.get(payment_type, payment_type or "未设置")}

    @with_db_retry()
    async def list_records(self, user_id: int, page: int, page_size: int) -> dict:
        """复用现有用户隔离分页，返回真实记录与中文字典；异常回滚后重试。"""
        try:
            await self._require_user(user_id)
            options = await self._options()
            response = await SettlementService(self.session).get_settlement_records(user_id, page, page_size)
            data = response["data"]
            data["list"] = [self._display(item, options) for item in data["list"]]
            self.log.info("结算记录查询成功：user_id={} page={} page_size={} total={}", user_id, page, page_size, data["total"])
            return {**data, "options": options}
        except BaseException:
            await self.session.rollback()
            raise

    @with_db_retry()
    async def update_result(self, user_id: int, record_id: int, admin_id: int, payload: AdminSettlementUpdate) -> dict:
        """锁定指定用户的记录，校验版本后修改结果和原因，追加审计，金额/流水不变。"""
        try:
            await self._require_user(user_id)
            options = await self._options()
            chosen = next((item for item in options["statuses"] if item["value"] == payload.status), None)
            if chosen is None or not chosen["enabled"]:
                raise ValueError("所选结算结果已停用，请刷新记录后重新选择")
            record = (await self.session.execute(
                select(SettlementRecord).where(SettlementRecord.id == record_id, SettlementRecord.user_id == user_id)
                .with_for_update().execution_options(populate_existing=True)
            )).scalar_one_or_none()
            if record is None:
                raise ValueError("该用户的结算记录不存在")
            before = serialize_settlement_record(record)
            if settlement_revision(before) != payload.expected_revision:
                raise ValueError("结算记录已被其他操作修改，请刷新记录后重新编辑")
            if record.status == payload.status and (record.reject_reason or "") == payload.reject_reason and not payload.remark:
                raise ValueError("结算结果未发生变化")
            old_label = self._display(before, options)["status_label"]
            record.status = payload.status
            record.reject_reason = payload.reject_reason or None
            record.updated_at = get_beijing_now_naive().replace(microsecond=0)
            # 即使与上次时间落在同一秒，也显式写入北京时间，不触发数据库本地时区的 now()。
            flag_modified(record, "updated_at")
            audit = f"[{record.updated_at:%Y-%m-%d %H:%M:%S}] 管理员ID={admin_id} 修改结算结果：{old_label} → {chosen['label']}"
            if payload.reject_reason:
                audit += f"；拒绝原因：{payload.reject_reason}"
            if payload.remark:
                audit += f"；修改说明：{payload.remark}"
            record.remark = f"{record.remark}\n{audit}" if record.remark else audit
            await self.session.flush()
            # 显式读取写入后的快照，避免异步属性隐式读取，并保持返回版本与刷新查询一致。
            await self.session.refresh(record)
            item = self._display(serialize_settlement_record(record), options)
            await self.session.commit()
            self.log.info("结算结果修改成功：admin_id={} user_id={} record_id={} before={} after={}", admin_id, user_id, record_id, before, item)
            return item
        except BaseException:
            await self.session.rollback()
            raise
