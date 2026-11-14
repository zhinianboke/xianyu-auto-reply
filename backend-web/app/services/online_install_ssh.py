"""
在线安装 SSH 执行器。

功能：密码或私钥认证、固定部署命令执行、实时合并输出与超时释放。
所有远程执行均由接口明确触发，不在模块导入或服务启动时连接服务器。
"""
from __future__ import annotations

import codecs
import shlex
import time
from collections.abc import Iterator
from contextlib import contextmanager
from io import StringIO
from threading import Event, Timer

import paramiko
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa

from app.core.config import get_settings
from app.schemas.online_install import OnlineInstallRequest, SSHConnectionRequest

INSTALL_COMMAND = r"curl -fsSL https://xy-update.zhinianboke.com/deploy.sh | sed 's/\r$//' | bash"


class OnlineInstallError(Exception):
    """携带可直接展示给用户的 SSH 或安装错误。"""


def parse_private_key(private_key: str, passphrase: str = "") -> paramiko.PKey:
    """从内存解析 PEM / OpenSSH 私钥及可选口令，不写入临时文件。

    Args:
        private_key: 包含 BEGIN / END 行的完整 SSH 私钥。
        passphrase: 加密私钥的口令，空字符串表示未提供。
    Returns:
        用于 SSH 认证的 RSA、Ed25519 或 ECDSA 私钥；失败抛出中文业务错误。
    """
    data = private_key.strip().encode("utf-8")
    if not data.startswith(b"-----BEGIN ") or b"PRIVATE KEY-----" not in data.split(b"\n", 1)[0]:
        raise OnlineInstallError("请填写完整的 SSH 私钥（包含 BEGIN / END 行），不能使用 .pub 公钥")
    loader = serialization.load_ssh_private_key if data.startswith(b"-----BEGIN OPENSSH PRIVATE KEY-----") else serialization.load_pem_private_key
    try:
        key = loader(data, password=passphrase.encode("utf-8") if passphrase else None)
    except TypeError as exc:
        message = "私钥已加密，请填写私钥口令" if not passphrase else "此私钥未加密，请清空私钥口令后重试"
        raise OnlineInstallError(message) from exc
    except ValueError as exc:
        if not passphrase and "password" in str(exc).lower():
            raise OnlineInstallError("私钥已加密，请填写私钥口令") from exc
        message = "私钥口令不正确或私钥内容无效，请检查后重试" if passphrase else "SSH 私钥格式无效或内容不完整，请填写完整的 OpenSSH / PEM 私钥"
        raise OnlineInstallError(message) from exc
    except UnsupportedAlgorithm as exc:
        raise OnlineInstallError("SSH 私钥的算法或加密方式不受支持，请使用 RSA、Ed25519 或 ECDSA 私钥") from exc

    if isinstance(key, rsa.RSAPrivateKey):
        key_type = paramiko.RSAKey
    elif isinstance(key, ed25519.Ed25519PrivateKey):
        key_type = paramiko.Ed25519Key
    elif isinstance(key, ec.EllipticCurvePrivateKey) and isinstance(key.curve, (ec.SECP256R1, ec.SECP384R1, ec.SECP521R1)):
        key_type = paramiko.ECDSAKey
    else:
        raise OnlineInstallError("SSH 私钥算法不受支持，请使用 RSA、Ed25519 或 ECDSA（NIST P-256 / P-384 / P-521）私钥")
    # 统一转换为未加密的 OpenSSH 格式后交给 Paramiko，兼容 PEM / PKCS#8；全过程仅在内存中进行。
    normalized = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH, serialization.NoEncryption())
    return key_type.from_private_key(StringIO(normalized.decode("ascii")))


@contextmanager
def connect_ssh(connection: SSHConnectionRequest):
    """按请求选择密码或私钥认证并最终关闭连接；禁用本机密钥和 SSH agent。

    Args:
        connection: 已校验的 SSH 连接参数。
    Yields:
        本次操作独占的 SSHClient。
    """
    settings = get_settings()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        authentication = (
            {"pkey": parse_private_key(connection.private_key, connection.private_key_passphrase)}
            if connection.auth_method == "private_key" else {"password": connection.password}
        )
        client.connect(
            hostname=connection.host, port=connection.port,
            username=connection.username, **authentication,
            timeout=settings.online_install_connect_timeout,
            auth_timeout=settings.online_install_connect_timeout,
            banner_timeout=settings.online_install_connect_timeout,
            look_for_keys=False, allow_agent=False,
        )
        transport = client.get_transport()
        if transport is None or not transport.is_active():
            raise OnlineInstallError("SSH 连接已经失效，请重新连接")
        transport.set_keepalive(20)
        yield client
    except paramiko.AuthenticationException as exc:
        message = "SSH 私钥认证失败，请检查用户名及服务器是否已配置对应公钥" if connection.auth_method == "private_key" else "SSH 认证失败，请检查用户名和密码"
        raise OnlineInstallError(message) from exc
    except TimeoutError as exc:
        raise OnlineInstallError("SSH 连接或执行超时，请检查服务器网络或查看安装日志") from exc
    except (paramiko.SSHException, OSError) as exc:
        raise OnlineInstallError(f"SSH 连接失败：{exc}") from exc
    finally:
        client.close()


def stream_command(client: paramiko.SSHClient, command: str, timeout: float) -> Iterator[dict]:
    """合并标准输出和错误输出，按块读取并正确解码跨块 UTF-8 字符。

    Args:
        client: 已建立的独占 SSH 连接。
        command: 经 shlex.quote 转义并由 Bash 执行的固定部署命令。
        timeout: 本条命令最大执行秒数。
    Yields:
        output、heartbeat 或 exit_code 事件；异常时关闭远程 channel。
    """
    transport = client.get_transport()
    if transport is None or not transport.is_active():
        raise OnlineInstallError("SSH 连接已经失效")
    channel = None
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    deadline = time.monotonic() + timeout
    heartbeat_at = time.monotonic() + 5
    expired = Event()
    confirmation_expired = Event()
    confirmation_watchdog = None

    def close_expired_transport() -> None:
        """到期主动断开传输，唤醒等待远端 exec 确认的 Paramiko 阻塞调用。"""
        expired.set()
        transport.close()

    watchdog = Timer(timeout, close_expired_transport)
    watchdog.daemon = True
    watchdog.start()
    try:
        channel = transport.open_session(timeout=min(timeout, get_settings().online_install_connect_timeout))
        channel.set_combine_stderr(True)

        def close_unconfirmed_transport() -> None:
            """服务器未及时确认命令时断开连接，避免等待期间任务缺失心跳。"""
            confirmation_expired.set()
            transport.close()

        confirmation_watchdog = Timer(get_settings().online_install_connect_timeout, close_unconfirmed_transport)
        confirmation_watchdog.daemon = True
        confirmation_watchdog.start()
        channel.exec_command(command)
        confirmation_watchdog.cancel()
        channel.shutdown_write()  # 固定脚本无需交互，避免远程命令等待输入。
        while True:
            if time.monotonic() >= deadline:
                raise OnlineInstallError("安装执行超时，SSH 会话已关闭，请查看日志并检查目标服务器的实际状态")
            if channel.recv_ready():
                output = decoder.decode(channel.recv(32768))
                if output:
                    yield {"output": output}
            elif channel.exit_status_ready() and (channel.closed or channel.eof_received):
                # 远端可先发送退出码、再发送末尾输出；收到 EOF 后再发布结果。
                output = decoder.decode(b"", final=True)
                if output:
                    yield {"output": output}
                exit_code = channel.recv_exit_status()
                if exit_code < 0:
                    raise OnlineInstallError("SSH 连接中断，未收到安装退出码，请检查目标服务器的实际状态")
                yield {"exit_code": exit_code}
                return
            elif channel.closed or not transport.is_active():
                raise OnlineInstallError("SSH 连接中断，无法确认安装结果，请检查目标服务器的实际状态")
            else:
                time.sleep(0.1)
            if time.monotonic() >= heartbeat_at:
                yield {"heartbeat": True}
                heartbeat_at = time.monotonic() + 5
    except (paramiko.SSHException, OSError) as exc:
        if expired.is_set() or time.monotonic() >= deadline:
            raise OnlineInstallError("安装执行超时，SSH 会话已关闭，请查看日志并检查目标服务器的实际状态") from exc
        if confirmation_expired.is_set():
            raise OnlineInstallError("SSH 服务器未及时确认执行命令，会话已关闭，请检查目标服务器的实际状态") from exc
        raise
    finally:
        watchdog.cancel()
        if confirmation_watchdog is not None:
            confirmation_watchdog.cancel()
        if channel is not None:
            channel.close()


def test_ssh_connection(connection: SSHConnectionRequest) -> dict:
    """仅测试所选 SSH 认证，返回真实 SSH 服务版本及响应耗时，不检查 Docker 环境。"""
    started = time.monotonic()
    with connect_ssh(connection) as client:
        server_info = client.get_transport().remote_version
    return {"server_info": server_info, "response_time": round((time.monotonic() - started) * 1000)}


def run_install_script(request: OnlineInstallRequest, log) -> Iterator[dict]:
    """SSH 连接后在登录默认目录执行管道；pipefail 确保下载失败不被误报成功。"""
    with connect_ssh(request) as client:
        yield {"output": "SSH 连接成功，正在执行安装脚本…\n"}
        command = "bash -o pipefail -c " + shlex.quote(INSTALL_COMMAND)
        log.info(f"[在线安装] 执行远程命令：{command}")
        yield {"output": f"将在 SSH 登录后的默认目录执行安装脚本\n执行命令：{INSTALL_COMMAND}\n"}
        yield from stream_command(client, command, get_settings().online_install_timeout)
