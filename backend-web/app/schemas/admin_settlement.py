"""管理员逐条修改结算结果的参数校验；不允许修改金额或收款信息。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from common.models.settlement_record import SETTLEMENT_STATUSES


class AdminSettlementUpdate(BaseModel):
    """目标结果、并发校验版本、拒绝原因与追加的操作说明。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: str = Field(max_length=32, description="结算结果")
    expected_revision: str = Field(pattern=r"^[a-f0-9]{64}$", description="原记录版本")
    reject_reason: str = Field(default="", max_length=512, description="拒绝原因")
    remark: str = Field(default="", max_length=500, description="修改说明（追加保留历史备注）")

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        """只允许现有四种结算结果，非法参数给出中文错误。"""
        if value not in SETTLEMENT_STATUSES:
            raise ValueError("结算结果无效，请重新选择")
        return value

    @model_validator(mode="after")
    def validate_rejection(self) -> AdminSettlementUpdate:
        """拒绝时必须填写原因；其他结果不得附带拒绝原因。"""
        if self.status == "rejected" and not self.reject_reason:
            raise ValueError("结算结果为已拒绝时必须填写拒绝原因")
        if self.status != "rejected" and self.reject_reason:
            raise ValueError("只有已拒绝的结算结果可以填写拒绝原因")
        return self
