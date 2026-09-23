"""
Scheduler服务配置模块

功能：
1. 继承common配置基类
2. 添加Scheduler服务特定配置
3. 从.env文件读取配置
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field

from common.core.config import BaseConfig


class SchedulerConfig(BaseConfig):
    """
    Scheduler服务配置类
    
    包含Scheduler服务特定配置：
    - 服务端口
    - 服务间通信URL
    """

    # 服务配置
    project_name: str = Field(default="Xianyu Scheduler Service")
    service_port: int = Field(default=8091, alias="SCHEDULER_PORT")
    
    # 服务间通信URL
    websocket_service_url: str = Field(
        default="http://127.0.0.1:8090",
        alias="WEBSOCKET_SERVICE_URL"
    )
    backend_web_service_url: str = Field(
        default="http://127.0.0.1:8089",
        alias="BACKEND_WEB_SERVICE_URL",
    )

    # 自动续售执行参数：周期由定时任务配置表控制，批量和租约通过环境变量调节。
    auto_relist_batch_size: int = Field(
        default=10, alias="AUTO_RELIST_BATCH_SIZE", ge=1, le=100
    )
    auto_relist_lease_seconds: int = Field(
        default=900, alias="AUTO_RELIST_LEASE_SECONDS", ge=120, le=86400
    )
    auto_relist_max_retries: int = Field(
        default=3, alias="AUTO_RELIST_MAX_RETRIES", ge=1, le=20
    )


@lru_cache
def get_settings() -> SchedulerConfig:
    """返回缓存的配置实例"""
    return SchedulerConfig()
