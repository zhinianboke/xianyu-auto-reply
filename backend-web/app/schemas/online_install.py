"""在线安装请求校验：SSH 密码或私钥认证信息。"""
from __future__ import annotations

import re
from ipaddress import ip_address
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class SSHConnectionRequest(BaseModel):
    """校验 SSH 连接及所选认证方式；保留密码和私钥口令中的空格。"""

    host: str = Field(min_length=1, max_length=253)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=128)
    auth_method: Literal["password", "private_key"] = "password"
    password: str = Field(default="", max_length=1024)
    private_key: str = Field(default="", max_length=65536)
    private_key_passphrase: str = Field(default="", max_length=1024)

    @model_validator(mode="after")
    def validate_authentication(self) -> SSHConnectionRequest:
        """要求所选方式的凭据并清空另一方式的字段，使幂等签名只包含实际认证信息。"""
        if self.auth_method == "password":
            if not self.password:
                raise ValueError("密码认证方式下，SSH 密码不能为空")
            self.private_key = ""
            self.private_key_passphrase = ""
        else:
            self.private_key = self.private_key.replace("\r\n", "\n").replace("\r", "\n").strip().lstrip("\ufeff").strip()
            if not self.private_key:
                raise ValueError("私钥认证方式下，请填写完整的 SSH 私钥")
            self.password = ""
        return self

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
    """安装仅接收 SSH 连接信息，在服务器登录后的默认目录执行脚本。"""
