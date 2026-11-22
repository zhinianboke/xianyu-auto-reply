"""HTTP/WebSocket 请求来源公共模块：校验可信代理、规范化客户端 IP，并保留连接来源。"""
from __future__ import annotations

import json
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Any

from starlette.requests import HTTPConnection

from common.core.config import get_settings, parse_trusted_proxy_cidrs


def _parse_ip(value: str | None) -> IPv4Address | IPv6Address | None:
    """校验单个 IP 地址；参数为原始值，返回规范化地址对象，非法或缺失时返回 None。"""
    if not isinstance(value, str) or not value.strip() or "%" in value:
        return None
    try:
        return ip_address(value.strip())
    except ValueError:
        return None


def client_ip(request: HTTPConnection) -> str | None:
    """获取经可信代理校验的客户端 IP；兼容 HTTP/WebSocket，无法识别连接对端时返回 None。"""
    peer = _parse_ip(request.client.host if request.client else None)
    if peer is None:
        return None
    networks = parse_trusted_proxy_cidrs(get_settings().trusted_proxy_cidrs)
    # 双栈 socket 的 IPv4-mapped 对端与对应 IPv4 是同一连接来源；仅信任判断映射，日志保留原型。
    mapped_peer = peer.ipv4_mapped if isinstance(peer, IPv6Address) else None
    if any(peer in network or (mapped_peer is not None and mapped_peer in network) for network in networks):
        forwarded = request.headers.get("X-Forwarded-For", "").split(",", 1)[0]
        declared = _parse_ip(forwarded) or _parse_ip(request.headers.get("X-Real-IP"))
        if declared is not None:
            return str(declared)
    return str(peer)


def request_origin(scope: dict[str, Any]) -> dict[str, str | None]:
    """汇总请求来源；参数为 HTTP/WebSocket ASGI scope，返回客户端、真实对端和原始代理声明。"""
    connection = HTTPConnection(scope)
    peer = connection.client
    peer_ip = _parse_ip(peer.host if peer else None)
    connection_peer = "unknown"
    if peer_ip is not None and peer is not None:
        host = f"[{peer_ip}]" if peer_ip.version == 6 else str(peer_ip)
        connection_peer = f"{host}:{peer.port}"
    return {
        "client_ip": client_ip(connection),
        "connection_peer": connection_peer,
        "x_forwarded_for": connection.headers.get("X-Forwarded-For", ""),
        "x_real_ip": connection.headers.get("X-Real-IP", ""),
    }


def format_request_origin(scope: dict[str, Any]) -> str:
    """将连接来源转换为单行 JSON；参数为 ASGI scope，返回完整且避免换行注入的日志字段。"""
    return json.dumps(request_origin(scope), ensure_ascii=False, separators=(",", ":"))
