"""
amap_inputtips_service 的网页后端兼容导出。

功能：
1. 保留原 app.services 导入路径；
2. 统一复用 common 中的实现，避免跨服务复制业务逻辑。
"""
from __future__ import annotations

from common.services.amap_inputtips_service import (
    REQUEST_TIMEOUT_SECONDS,
    AMAP_INPUTTIPS_URL,
    AMAP_WEB_KEY,
    AMAP_APP_NAME,
    AMAP_ORIGIN,
    AmapInputTipsError,
    _as_text,
    _parse_tip,
    AmapInputTipsService,
)

__all__ = [
    "REQUEST_TIMEOUT_SECONDS",
    "AMAP_INPUTTIPS_URL",
    "AMAP_WEB_KEY",
    "AMAP_APP_NAME",
    "AMAP_ORIGIN",
    "AmapInputTipsError",
    "AmapInputTipsService",
]
