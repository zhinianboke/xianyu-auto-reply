"""
WebSocket服务配置模块

功能：
1. 继承common配置基类
2. 添加WebSocket服务特定配置
3. 从.env文件读取配置
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field

from common.core.config import BaseConfig


class WebSocketConfig(BaseConfig):
    """
    WebSocket服务配置类
    
    包含WebSocket服务特定配置：
    - 服务端口
    - 浏览器配置
    - 服务间通信URL
    """

    # 服务配置
    project_name: str = Field(default="Xianyu WebSocket Service")
    service_port: int = Field(default=8090, alias="WEBSOCKET_PORT")
    
    # 启动时是否自动连接WebSocket
    auto_start_websocket: bool = Field(default=True, alias="AUTO_START_WEBSOCKET")
    
    # 浏览器配置
    max_captcha_concurrent: int = Field(default=3, alias="MAX_CAPTCHA_CONCURRENT")
    browser_headless: bool = Field(default=True, alias="BROWSER_HEADLESS")

    # DrissionPage 滑块兜底引擎配置
    # 当 Playwright 主引擎滑块验证失败后，再用 DrissionPage 引擎重试一次
    captcha_drissionpage_fallback_enabled: bool = Field(
        default=True, alias="CAPTCHA_DRISSIONPAGE_FALLBACK_ENABLED"
    )
    # DrissionPage 单次验证超时（秒）
    captcha_drissionpage_timeout: int = Field(
        default=25, alias="CAPTCHA_DRISSIONPAGE_TIMEOUT"
    )
    # DrissionPage 是否无头（Docker 必须 true）
    captcha_drissionpage_headless: bool = Field(
        default=True, alias="CAPTCHA_DRISSIONPAGE_HEADLESS"
    )
    
    # 服务间通信URL
    backend_web_service_url: str = Field(
        default="http://localhost:8089",
        alias="BACKEND_WEB_SERVICE_URL"
    )
    
    # 静态文件目录（共享）
    static_dir: str = Field(default="static", alias="STATIC_DIR")


@lru_cache
def get_settings() -> WebSocketConfig:
    """返回缓存的配置实例"""
    return WebSocketConfig()
