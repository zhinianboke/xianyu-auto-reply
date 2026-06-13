"""
网络相关公共工具

功能：
1. resolve_listen_host：在「双栈监听(::)」与「仅 IPv4(0.0.0.0)」之间做兼容性回退，
   解决 Windows 下 :: 仅监听 IPv6、以及部分关闭 IPv6 的 Docker 容器绑定 :: 失败的问题。

说明：
- Windows 默认 IPV6_V6ONLY=1，绑定 :: 只会监听 IPv6，无法接受 127.0.0.1 等 IPv4 连接，
  因此在 Windows 上直接回退到 0.0.0.0，保证 IPv4 客户端可访问。
- Linux/macOS 上先做一次实际绑定探测，若 IPv6 不可用（例如 Docker 关闭了 IPv6），
  则回退到 0.0.0.0，避免服务因绑定失败而无法启动。
"""
from __future__ import annotations

import socket
import sys

from loguru import logger

# 双栈监听地址与 IPv4 回退地址常量，避免在各处写死字符串
DUAL_STACK_HOST = "::"
IPV4_FALLBACK_HOST = "0.0.0.0"


def resolve_listen_host(host: str, port: int) -> str:
    """
    解析最终用于 uvicorn 绑定的监听地址，必要时回退到 0.0.0.0。

    Args:
        host: 期望监听的地址（通常来自配置 settings.host）。
        port: 服务监听端口，仅用于探测时构造测试套接字。

    Returns:
        实际可用的监听地址：若 host 为 :: 且当前环境不支持，则返回 0.0.0.0；
        其它情况原样返回 host。
    """
    # 仅当显式要求双栈监听时才需要做兼容性处理，其它地址原样返回
    if host != DUAL_STACK_HOST:
        return host

    # Windows 下 :: 只监听 IPv6，无法接受 IPv4 连接，直接回退保证 IPv4 可访问
    if sys.platform == "win32":
        logger.warning(
            "当前为 Windows 环境，监听 {} 仅支持 IPv6，已自动回退到 {} 以保证 IPv4 访问",
            DUAL_STACK_HOST,
            IPV4_FALLBACK_HOST,
        )
        return IPV4_FALLBACK_HOST

    # Linux/macOS：实际尝试绑定一次，确认 IPv6 双栈可用（部分 Docker 关闭了 IPv6）
    test_socket = None
    try:
        test_socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        test_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # 绑定到端口 0（由系统分配临时端口），仅探测地址族是否可用，避免与真实端口冲突
        test_socket.bind((DUAL_STACK_HOST, 0))
        logger.info("IPv6 双栈监听可用，使用 {} 监听端口 {}", DUAL_STACK_HOST, port)
        return DUAL_STACK_HOST
    except OSError as exc:
        logger.warning(
            "绑定 IPv6 双栈地址 {} 失败（{}），已自动回退到 {}",
            DUAL_STACK_HOST,
            exc,
            IPV4_FALLBACK_HOST,
        )
        return IPV4_FALLBACK_HOST
    finally:
        if test_socket is not None:
            test_socket.close()
