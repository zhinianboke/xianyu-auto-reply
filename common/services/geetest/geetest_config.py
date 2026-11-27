"""极验服务端配置，由进程环境或当前服务的 .env 文件提供。"""
from functools import lru_cache

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class GeetestConfig(BaseSettings):
    """集中定义极验接入配置和与旧版一致的默认值。"""

    model_config = SettingsConfigDict(
        env_prefix="GEETEST_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    captcha_id: str = Field(default="a30cdbb466e9349385762477cb2c7df6", min_length=1)
    private_key: SecretStr = Field(default=SecretStr("6f70322308eb29ae0d85516a14a32d2c"), min_length=1)
    user_id: str = "xianyu_system"
    client_type: str = Field(default="web", min_length=1)
    api_url: AnyHttpUrl = AnyHttpUrl("http://api.geetest.com")
    register_url: str = "/register.php"
    validate_url: str = "/validate.php"
    version: str = Field(default="python-fastapi:3.1.1", min_length=1)
    timeout: float = Field(default=3.0, gt=0, allow_inf_nan=False)
    status_ttl_seconds: int = Field(default=300, gt=0)
    sdk_url: AnyHttpUrl = AnyHttpUrl("https://static.geetest.com/static/tools/gt.js")

    @field_validator("api_url", "sdk_url")
    @classmethod
    def validate_http_url(cls, url: AnyHttpUrl) -> AnyHttpUrl:
        """校验服务地址和浏览器 SDK 地址，拒绝包含凭据的 URL。"""
        if url.username is not None or url.password is not None:
            raise ValueError("极验地址不能包含用户名或密码")
        return url

    @field_validator("api_url")
    @classmethod
    def validate_api_url(cls, url: AnyHttpUrl) -> AnyHttpUrl:
        """校验能够直接拼接接口路径的 API 基址。"""
        if url.query is not None or url.fragment is not None:
            raise ValueError("极验 API 基址不能包含查询参数或片段")
        return url

    @field_validator("register_url", "validate_url")
    @classmethod
    def validate_api_path(cls, path: str) -> str:
        """校验注册和二次验证的接口路径，返回原路径。"""
        if not path.startswith("/") or path.startswith("//") or any(char in path for char in "\\?#"):
            raise ValueError("极验接口路径必须以单个斜杠开头，且不能包含反斜杠、查询参数或片段")
        return path


@lru_cache
def get_geetest_config() -> GeetestConfig:
    """返回当前服务的极验配置，进程环境变量优先于 .env。"""
    return GeetestConfig()
