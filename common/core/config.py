"""
共享配置基类

功能：
1. 从环境变量加载配置
2. 提供数据库连接URL
3. 提供Redis连接配置
4. 提供通用配置项
"""
from __future__ import annotations

from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseConfig(BaseSettings):
    """
    所有服务的基础配置类
    
    包含数据库连接、Redis连接、日志级别等通用配置
    各服务可以继承此类并添加自己的特定配置
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 环境配置
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")

    # SQL 日志开关：开启后会在每条 SQL 执行前打印拼接好参数的完整 SQL。
    # 默认开启，便于开发与 Docker 环境排查；高并发生产环境如需降低开销可设为 false。
    sql_echo: bool = Field(default=True)

    # 数据库配置
    mysql_host: str = Field(default="localhost")
    mysql_port: int = Field(default=3306)
    mysql_user: str = Field(default="root")
    mysql_password: str = Field(default="root")
    mysql_database: str = Field(default="xianyu_data")
    sync_driver: str = Field(default="mysql+pymysql")
    async_driver: str = Field(default="mysql+asyncmy")

    # 数据库连接池配置（账号数量较大时可通过环境变量调优）
    # 重要：db_pool_size + db_max_overflow 不应超过 MySQL 的 max_connections，
    # 否则连接池打满后还会触发 MySQL 的 "Too many connections"。
    # 上千账号场景的建议：保持适中的连接池 + 短连接超时，让卡住的连接快速失败并归还，
    # 而不是无限放大连接数把远程 MySQL 压垮。
    db_pool_size: int = Field(default=30)            # 常驻连接数
    db_max_overflow: int = Field(default=70)         # 允许的溢出连接数（峰值 = pool_size + max_overflow）
    db_pool_timeout: int = Field(default=30)         # 从连接池获取连接的最长等待秒数
    db_pool_recycle: int = Field(default=1800)       # 连接回收时间（秒），防止 MySQL 主动断开陈旧连接
    db_pool_pre_ping: bool = Field(default=True)     # 取连接前 ping 一次，自动剔除失效连接
    db_pool_use_lifo: bool = Field(default=True)     # LIFO 复用最近使用的连接，便于空闲连接被回收，降低对远程库的常驻连接数
    db_connect_timeout: int = Field(default=10)      # 建立 TCP 连接的超时秒数，避免远程库不可达时无限阻塞
    
    # Redis配置（敏感信息请通过环境变量或.env文件配置）
    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)
    redis_password: str = Field(default="", repr=False)
    redis_db: int = Field(default=0)
    
    # JWT配置（用于安全模块）
    # 注意：jwt_secret_key 由数据库统一托管（backend-web 启动时自动生成并持久化），
    # 此处 default 仅作占位，运行期会被数据库中的值覆盖；请勿依赖环境变量配置该值。
    jwt_secret_key: str = Field(default="change-me", repr=False)
    jwt_algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=30)
    refresh_token_expire_minutes: int = Field(default=60 * 24 * 7)

    # 服务监听地址：`::` 同时监听 IPv4 和 IPv6（dual-stack），
    # 适用于 Linux/macOS；如需仅监听 IPv4 可设为 0.0.0.0
    host: str = Field(default="::")

    # 服务地址配置
    websocket_service_url: str = Field(default="http://127.0.0.1:8001")

    # 数据库备份文件目录（Docker 环境通过共享卷挂载，本地回退到 backups）
    # 通过环境变量 BACKUP_DIR 配置，禁止写死 localhost / 绝对路径
    backup_dir: str = Field(default="backups", alias="BACKUP_DIR")

    # IM Token 缓存（xy_token_cache 表）的随机过期时间区间（小时）。
    # 实际 TTL 在区间内随机取值，避免大量账号 Token 同时过期造成并发刷新。
    # 未配置时默认 5~10 小时；配置非法（<=0 或 min>max）时回退默认。
    token_cache_ttl_min_hours: float = Field(default=5.0, alias="TOKEN_CACHE_TTL_MIN_HOURS")
    token_cache_ttl_max_hours: float = Field(default=10.0, alias="TOKEN_CACHE_TTL_MAX_HOURS")

    # 滑块验证 - 真实鼠标模式开关
    # 开启后：用 pyautogui 驱动“物理光标”回放真人轨迹完成滑块（成功率高，但会占用桌面鼠标，
    #         仅适用于有图形桌面的 Windows 环境；运行期间该桌面鼠标被接管约 2~3 秒）。
    # 关闭（默认）：走原有 Playwright(CDP) 轨迹 + DrissionPage 兜底逻辑。
    # Docker / 无头 Linux 环境必须保持关闭（无桌面无法驱动物理鼠标），故默认 False。
    captcha_real_mouse_enabled: bool = Field(default=False, alias="CAPTCHA_REAL_MOUSE")

    @property
    def database_url(self) -> str:
        """同步数据库连接URL"""
        password = quote_plus(self.mysql_password)
        host = f"[{self.mysql_host}]" if ":" in self.mysql_host else self.mysql_host
        return f"{self.sync_driver}://{self.mysql_user}:{password}@{host}:{self.mysql_port}/{self.mysql_database}"

    @property
    def async_database_url(self) -> str:
        """异步数据库连接URL"""
        password = quote_plus(self.mysql_password)
        host = f"[{self.mysql_host}]" if ":" in self.mysql_host else self.mysql_host
        return f"{self.async_driver}://{self.mysql_user}:{password}@{host}:{self.mysql_port}/{self.mysql_database}"

    @property
    def redis_url(self) -> str:
        """Redis连接URL"""
        password = quote_plus(self.redis_password)
        host = f"[{self.redis_host}]" if ":" in self.redis_host else self.redis_host
        return f"redis://:{password}@{host}:{self.redis_port}/{self.redis_db}"


@lru_cache
def get_settings() -> BaseConfig:
    """返回缓存的配置实例"""
    return BaseConfig()
