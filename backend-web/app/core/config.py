"""
Backend-Web服务配置模块

功能：
1. 继承common配置基类
2. 添加Backend-Web服务特定配置
3. 从.env文件读取配置
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import List

from pydantic import Field, computed_field

from common.core.config import BaseConfig


class BackendWebConfig(BaseConfig):
    """
    Backend-Web服务配置类
    
    包含Backend-Web服务特定配置：
    - 服务端口
    - JWT配置
    - CORS配置
    - 服务间通信URL
    """

    # 服务配置
    project_name: str = Field(default="Xianyu Backend-Web Service")
    version: str = Field(default="0.1.0")
    api_v1_prefix: str = Field(default="/api/v1")
    service_port: int = Field(default=8089, alias="BACKEND_WEB_PORT")
    
    # JWT配置
    # 注意：jwt_secret_key 由数据库统一托管（启动时 ensure_jwt_secret_key 自动生成/加载并写回此实例），
    # 此处 default 仅作占位，运行期会被数据库中的值覆盖。
    jwt_secret_key: str = Field(default="change-me", repr=False)
    jwt_algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=30)
    refresh_token_expire_minutes: int = Field(default=60 * 24 * 7)
    
    # CORS配置
    cors_origins_raw: str = Field(default="*", alias="CORS_ORIGINS")
    
    # 服务间通信URL
    websocket_service_url: str = Field(
        default="http://localhost:8090",
        alias="WEBSOCKET_SERVICE_URL"
    )
    scheduler_service_url: str = Field(
        default="http://localhost:8091",
        alias="SCHEDULER_SERVICE_URL"
    )
    
    # 静态文件目录（共享）
    static_dir: str = Field(default="static", alias="STATIC_DIR")
    
    frontend_public_url: str = Field(
        default="",
        alias="FRONTEND_PUBLIC_URL"
    )

    # Backend-Web服务的公网访问地址（用于生成文件URL）
    backend_web_public_url: str = Field(
        default="http://localhost:8089",
        alias="BACKEND_WEB_PUBLIC_URL"
    )
    
    # 启动时是否自动启动Goofish定时采集任务
    auto_start_crawl_jobs: bool = Field(default=True, alias="AUTO_START_CRAWL_JOBS")

    # 卡券对接（分销卡券）上游服务基址：用于「分销卡券」页面通过上游卡券系统提货
    # 默认指向生产环境上游服务，可通过环境变量 CARD_DOCK_BASE_URL 覆盖（禁止写死 localhost）
    card_dock_base_url: str = Field(
        default="http://backend.zhinianboke.com",
        alias="CARD_DOCK_BASE_URL",
    )

    @computed_field(return_type=list[str])
    @property
    def cors_origins(self) -> List[str]:
        """解析CORS配置"""
        raw_value = self.cors_origins_raw.strip()
        if not raw_value:
            return ["*"]
        if raw_value == "*":
            return ["*"]
        try:
            parsed = json.loads(raw_value)
            if isinstance(parsed, list):
                return [str(origin).strip() for origin in parsed if str(origin).strip()]
        except json.JSONDecodeError:
            pass
        return [origin.strip() for origin in raw_value.split(",") if origin.strip()]


@lru_cache
def get_settings() -> BackendWebConfig:
    """返回缓存的配置实例"""
    return BackendWebConfig()
