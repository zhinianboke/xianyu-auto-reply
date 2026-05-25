"""
进程管理工具模块

功能：
1. 杀掉进程树（父进程+所有子进程）
2. 通过端口号查找并杀掉占用端口的进程
3. 检测指定端口是否可连接
"""
import os
import signal
import socket
import subprocess
import sys


def kill_process_tree(pid: int):
    """
    杀掉指定PID及其所有子进程（进程树）

    Args:
        pid: 父进程PID
    """
    if sys.platform == "win32":
        try:
            # taskkill /T 会杀掉整个进程树
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception:
            pass
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass


def kill_by_port(port: int):
    """
    通过端口号查找并杀掉占用该端口的进程（Windows）

    Args:
        port: 端口号
    """
    if sys.platform != "win32":
        return
    try:
        # 用netstat查找占用端口的PID
        result = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        for line in result.stdout.splitlines():
            # 匹配 0.0.0.0:port 或 127.0.0.1:port 的LISTENING行
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                pid_str = parts[-1].strip()
                if pid_str.isdigit():
                    pid = int(pid_str)
                    # 避免杀掉自己
                    if pid != os.getpid():
                        subprocess.run(
                            ["taskkill", "/F", "/PID", str(pid)],
                            capture_output=True, timeout=5,
                            creationflags=subprocess.CREATE_NO_WINDOW,
                        )
    except Exception:
        pass


def check_port(port: int, host: str = "127.0.0.1", timeout: float = 0.3) -> bool:
    """
    检测指定端口是否可连接

    Args:
        port: 端口号
        host: 主机地址
        timeout: 连接超时时间（秒）
    Returns:
        True表示端口可连接（服务运行中）
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect((host, port))
            return True
    except (ConnectionRefusedError, OSError, TimeoutError):
        return False
