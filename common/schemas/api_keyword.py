"""API关键词新建和修改的共用校验，不调用外部API。"""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)

from common.models.xy_api_keyword_rule import HTTP_METHODS
from common.utils.response_field import parse_response_field_path


class ApiKeywordConfig(BaseModel):
    """新建与编辑共用的可修改字段，账号和所属用户由服务端校验。"""

    model_config = ConfigDict(extra="forbid")

    keyword: str
    url: str
    method: str = "GET"
    timeout: int = 60
    headers: dict[str, str] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    response_field: str = ""
    sync_confirm_delivery: StrictBool = False
    trigger_after_order: StrictBool = False

    @field_validator("keyword")
    @classmethod
    def validate_keyword(cls, value: str) -> str:
        """拆分中英文逗号和换行，拒绝空值、重复及超长关键字，返回规范文本。"""
        if len(value) > 12000:
            raise ValueError("触发关键字总长度不能超过12000个字符")
        keywords = [part.strip() for part in re.split(r"[,，\r\n]+", value) if part.strip()]
        if not keywords:
            raise ValueError("请输入触发关键字")
        if len(keywords) > 100:
            raise ValueError("一次最多填写100个触发关键字")
        if any(len(part) > 120 for part in keywords):
            raise ValueError("每个触发关键字不能超过120个字符")
        if len({part.casefold() for part in keywords}) != len(keywords):
            raise ValueError("触发关键字存在重复，请检查后保存")
        return ",".join(keywords)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        """校验HTTP/HTTPS地址及端口，不请求或探测用户填写的地址。"""
        value = value.strip()
        if len(value) > 2048 or any(char.isspace() or ord(char) < 32 for char in value):
            raise ValueError("API地址过长或包含空白字符")
        try:
            parsed = urlsplit(value)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                raise ValueError("请输入有效的HTTP或HTTPS API地址")
            if parsed.port is not None and parsed.port == 0:
                raise ValueError("API地址端口无效")
        except ValueError as exc:
            raise ValueError("请输入有效的HTTP或HTTPS API地址及端口") from exc
        return value

    @field_validator("method")
    @classmethod
    def validate_method(cls, value: str) -> str:
        """规范请求方法，只接受GET与POST。"""
        value = value.strip().upper()
        if value not in HTTP_METHODS:
            raise ValueError("请求方法只支持GET和POST")
        return value

    @field_validator("timeout", mode="before")
    @classmethod
    def validate_timeout(cls, value: Any) -> int:
        """超时时间必须为1到300秒的整数，避免静默截断小数。"""
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 300:
            raise ValueError("超时时间必须为1到300秒的整数")
        return value

    @field_validator("headers", mode="before")
    @classmethod
    def validate_headers(cls, value: Any) -> dict[str, str]:
        """请求头必须为字符串键值对象，拒绝换行、空键及非法头名称。"""
        if not isinstance(value, dict) or any(
            not isinstance(key, str) or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", key)
            or not isinstance(item, str) or "\r" in item or "\n" in item
            for key, item in value.items()
        ):
            raise ValueError("请求头必须是JSON对象，名称和值必须为合法字符串且不能包含换行")
        if len(json.dumps(value, ensure_ascii=False)) > 65536:
            raise ValueError("请求头内容不能超过65536个字符")
        return value

    @field_validator("params", mode="before")
    @classmethod
    def validate_params(cls, value: Any) -> dict[str, Any]:
        """请求参数必须为标准JSON对象，支持常量、商品ID、消息及消息链接占位符。"""
        if not isinstance(value, dict):
            raise ValueError("请求参数必须是JSON对象")  # noqa: TRY004 -- Pydantic字段校验必须使用ValueError
        try:
            serialized = json.dumps(value, ensure_ascii=False, allow_nan=False)
        except (ValueError, TypeError, RecursionError) as exc:
            raise ValueError("请求参数必须是有效的JSON对象") from exc
        if len(serialized) > 65536:
            raise ValueError("请求参数内容不能超过65536个字符")
        return value

    @field_validator("response_field")
    @classmethod
    def validate_response_field(cls, value: str) -> str:
        """保留可选响应路径，复用公共路径解析器验证基本格式。"""
        value = value.strip()
        if len(value) > 255 or (value and not parse_response_field_path(value)):
            raise ValueError("响应取值字段格式无效或超过255个字符")
        return value


class ApiKeywordCreate(ApiKeywordConfig):
    """新建配置；request_id为客户端生成的内部幂等标识，无需用户填写。"""

    request_id: UUID


class ApiKeywordUpdate(ApiKeywordConfig):
    """完整保存编辑字段，携带读取时的版本，防止并发覆盖；重试相同内容可幂等保存。"""

    expected_revision: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="before")
    @classmethod
    def require_complete_config(cls, value: Any) -> Any:
        """修改时要求提交全部配置字段，防止漏传字段被默认值清空或关闭。"""
        if isinstance(value, dict) and set(ApiKeywordConfig.model_fields) - value.keys():
            raise ValueError("修改配置必须提交全部字段，请重新打开编辑窗口后保存")
        return value
