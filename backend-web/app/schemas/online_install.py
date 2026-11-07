"""在线安装请求校验：SSH 密码连接信息与服务器安装目录。"""
from __future__ import annotations

import re
from ipaddress import ip_address
from posixpath import normpath

from pydantic import BaseModel, Field, field_validator


class SSHConnectionRequest(BaseModel):
    """校验 SSH 地址、端口、账号和密码，不改变密码中的空格。"""

    host: str = Field(min_length=1, max_length=253)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        """接收 IPv4、IPv6 或域名；拒绝 URL、路径及控制字符。"""
        host = value.strip().removeprefix("[").removesuffix("]")
        try:
            return str(ip_address(host))
        except ValueError:
            if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", host):
                raise ValueError("服务器地址必须为有效的 IP 或域名，不能包含协议、端口或路径")
            if any(not label or len(label) > 63 or label.startswith("-") or label.endswith("-") for label in host.split(".")):
                raise ValueError("服务器域名格式不正确")
            return host.lower()

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        """清理账号两端空格并拒绝空账号和控制字符。"""
        username = value.strip()
        if not username or any(ord(char) < 32 or ord(char) == 127 for char in username):
            raise ValueError("SSH 用户名不能为空或包含控制字符")
        return username


class OnlineInstallRequest(SSHConnectionRequest):
    """在 SSH 连接信息上增加 Linux 绝对安装目录。"""

    install_path: str = Field(default="/opt/xianyu-auto-reply", min_length=1, max_length=512)

    @field_validator("install_path")
    @classmethod
    def validate_install_path(cls, value: str) -> str:
        """要求明确的绝对目录，禁止根目录和控制字符；执行时另行 shell 转义。"""
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("安装目录不能包含控制字符")
        path = normpath(value.strip())
        if path.startswith("//"):
            path = "/" + path.lstrip("/")
        if path == "/" or not path.startswith("/"):
            raise ValueError("安装目录必须为 Linux 绝对路径，且不能为根目录或包含控制字符")
        return path
