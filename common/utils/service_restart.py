"""
服务重启工具模块

功能：
1. 自动检测运行环境（docker / frozen 打包 / dev 开发）
2. 提供统一的 restart_service()，在本机重启指定服务（backend-web / websocket / scheduler）
3. dev/frozen：派生一个「脱离父进程」的独立协调子进程，先等待原响应返回，
   再按端口杀掉旧进程、重新拉起服务；即便父进程（如 backend 自身）被杀，重启动作也不中断。
4. docker：容器内进程即 PID1，配合 compose 的 restart: unless-stopped，
   直接让目标进程延迟自杀退出，交由容器 restart 策略自动拉起。
5. 内置跨平台的按端口杀进程 / 端口连通检测，避免依赖 launcher 包。

设计说明：
- 三个服务入口统一为 <项目根>/<dir>/main.py，run_server() 内 uvicorn.run(port=service_port)。
- 端口固定：backend-web=8089、websocket=8090、scheduler=8091。
- 协调子进程使用「内联 Python 脚本」执行，兼容 Windows / Linux，不依赖 .bat。
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from loguru import logger


# 三个可重启服务的元信息：端口、目录名、中文名称
SERVICE_META: dict[str, dict] = {
    "backend-web": {"port": 8089, "dir": "backend-web", "label": "后端服务"},
    "websocket": {"port": 8090, "dir": "websocket", "label": "消息服务"},
    "scheduler": {"port": 8091, "dir": "scheduler", "label": "定时任务服务"},
}

# 重启前等待的秒数：确保当前 HTTP 响应已返回给前端后再执行杀进程
_RESTART_DELAY_SECONDS = 2.0


def get_project_root() -> Path:
    """
    获取项目根目录

    - 打包(frozen)模式：exe 所在目录
    - 开发模式：本文件位于 common/utils/，上溯两级即项目根
    """
    if is_frozen():
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent.parent


def is_frozen() -> bool:
    """
    检测是否运行在编译/打包模式（Nuitka / PyInstaller 等）

    与 launcher.frozen_detect.is_frozen 判定逻辑保持一致，
    但在 common 内独立实现，避免运行期服务依赖 launcher 包。
    """
    try:
        import __main__
        if hasattr(__main__, "__compiled__"):
            return True
    except Exception:
        pass

    if getattr(sys, "frozen", False):
        return True

    if sys.platform == "win32":
        exe_name = Path(sys.executable).name.lower()
        if not exe_name.startswith("python"):
            return True

    return False


def is_docker() -> bool:
    """
    检测是否运行在 Docker 容器内

    判定依据（任一命中即为 True）：
    1. 根目录存在 /.dockerenv 文件（Docker 官方镜像标准标记）
    2. 环境变量 RUNNING_IN_DOCKER 显式声明
    """
    try:
        if Path("/.dockerenv").exists():
            return True
    except Exception:
        pass
    if os.environ.get("RUNNING_IN_DOCKER", "").strip().lower() in ("1", "true", "yes"):
        return True
    return False


def detect_runtime() -> str:
    """
    检测当前运行环境

    Returns:
        'docker' | 'frozen' | 'dev'
    """
    if is_docker():
        return "docker"
    if is_frozen():
        return "frozen"
    return "dev"


def check_port(port: int, host: str = "127.0.0.1", timeout: float = 0.5) -> bool:
    """
    检测指定端口是否可连接（服务是否在线）

    Args:
        port: 端口号
        host: 主机地址
        timeout: 连接超时时间（秒）

    Returns:
        True 表示端口可连接（服务运行中）
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect((host, port))
            return True
    except (ConnectionRefusedError, OSError, TimeoutError):
        return False


def kill_by_port(port: int) -> None:
    """
    按端口查找并强制杀掉监听该端口的进程（跨平台）

    - Windows：netstat -ano 找 LISTENING 的 PID，taskkill /F
    - Linux/macOS：优先 fuser，其次 lsof
    避免误杀当前进程自身（os.getpid）。

    Args:
        port: 端口号
    """
    current_pid = os.getpid()
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["netstat", "-ano", "-p", "TCP"],
                capture_output=True, text=True, timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            for line in result.stdout.splitlines():
                if f":{port} " in line and "LISTENING" in line:
                    parts = line.split()
                    pid_str = parts[-1].strip()
                    if pid_str.isdigit():
                        pid = int(pid_str)
                        if pid not in (0, current_pid):
                            subprocess.run(
                                ["taskkill", "/F", "/PID", str(pid)],
                                capture_output=True, timeout=5,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                            )
        except Exception as e:
            logger.warning(f"按端口 {port} 杀进程失败（Windows）：{e}")
    else:
        # Linux/macOS：收集端口占用 PID 并逐个 kill -9
        pids: set[int] = set()
        try:
            result = subprocess.run(
                ["lsof", "-t", f"-i:{port}", "-sTCP:LISTEN"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.split():
                if line.strip().isdigit():
                    pids.add(int(line.strip()))
        except Exception:
            # lsof 不存在时退回 fuser
            try:
                result = subprocess.run(
                    ["fuser", f"{port}/tcp"],
                    capture_output=True, text=True, timeout=5,
                )
                for line in result.stdout.split():
                    if line.strip().isdigit():
                        pids.add(int(line.strip()))
            except Exception as e:
                logger.warning(f"按端口 {port} 查找进程失败（POSIX）：{e}")
        for pid in pids:
            if pid == current_pid:
                continue
            try:
                os.kill(pid, 9)
            except Exception as e:
                logger.warning(f"杀进程 {pid} 失败：{e}")


def _build_start_command(service_dir: str) -> list[str]:
    """
    构建重新拉起服务的启动命令

    - frozen 打包模式：主 exe --run-service <dir>（与 launcher.ServiceManager 一致）
    - dev 开发模式：python <项目根>/<dir>/main.py

    Args:
        service_dir: 服务目录名，如 'websocket'

    Returns:
        subprocess 可执行的命令列表
    """
    root = get_project_root()
    if is_frozen():
        return [sys.executable, "--run-service", service_dir]
    main_py = root / service_dir / "main.py"
    return [sys.executable, str(main_py)]


def _spawn_reviver(service_key: str) -> None:
    """
    派生一个「脱离父进程」的独立协调子进程完成重启（dev / frozen 模式）

    协调进程逻辑（内联 Python 脚本）：
        sleep(delay)          # 等待原 HTTP 响应返回
        kill_by_port(port)    # 杀掉旧进程（等价 停止.bat）
        Popen(start_cmd)      # 重新拉起服务（等价 启动.bat 的 python main.py）

    子进程必须完全脱离父进程：
    - Windows：DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    - POSIX：start_new_session=True
    这样即便父进程（如 backend 自身）被杀，重启动作仍继续。

    Args:
        service_key: 服务标识（backend-web / websocket / scheduler）
    """
    meta = SERVICE_META[service_key]
    port = meta["port"]
    service_dir = meta["dir"]
    root = get_project_root()
    start_cmd = _build_start_command(service_dir)

    # 内联协调脚本：不依赖项目内任何模块，跨平台自包含
    reviver_code = _REVIVER_TEMPLATE

    env = os.environ.copy()
    env["XR_REVIVE_PORT"] = str(port)
    env["XR_REVIVE_DELAY"] = str(_RESTART_DELAY_SECONDS)
    env["XR_REVIVE_CWD"] = str(root / service_dir)
    # 用换行分隔启动命令各参数，供子进程解析
    env["XR_REVIVE_CMD"] = "\n".join(start_cmd)
    env["PYTHONPATH"] = str(root)
    env["PYTHONIOENCODING"] = "utf-8"
    # 是否为重启后的服务弹出可见 cmd 窗口：
    # - dev 开发模式：显示（与手动运行 启动.bat 体验一致，可看到实时日志）
    # - frozen 打包模式：隐藏（与 launcher 一致，避免弹出多余黑窗）
    env["XR_REVIVE_SHOW_CONSOLE"] = "0" if is_frozen() else "1"

    # 协调进程用「当前 Python 解释器」执行内联脚本；
    # frozen 模式下 sys.executable 是主 exe，无法 -c 执行任意脚本，
    # 因此 frozen 模式改用同目录/系统的 python。
    # 若找不到可用解释器则直接抛错，交由上层返回失败提示——
    # 绝不能回退到「当前进程自杀」，否则替他人重启时会误杀自己（如 backend 替 websocket 重启）。
    reviver_python = _resolve_reviver_python()
    if not reviver_python:
        raise RuntimeError("未找到可用于协调重启的 Python 解释器")

    creationflags = 0
    startupinfo = None
    start_new_session = False
    if sys.platform == "win32":
        creationflags = (
            getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        )
    else:
        start_new_session = True

    try:
        subprocess.Popen(
            [reviver_python, "-c", reviver_code],
            cwd=str(root),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
            startupinfo=startupinfo,
            start_new_session=start_new_session,
            close_fds=True,
        )
        logger.info(f"[{service_key}] 已派生协调进程执行重启（端口 {port}）")
    except Exception as e:
        logger.error(f"[{service_key}] 派生协调进程失败：{e}")
        raise


def _resolve_reviver_python() -> Optional[str]:
    """
    解析用于执行内联协调脚本的 Python 解释器

    - dev 模式：sys.executable 即普通 python，可直接 -c
    - frozen 模式：sys.executable 是主 exe，需在其同目录/系统里找 python.exe
    """
    if not is_frozen():
        return sys.executable
    # frozen：尝试 exe 同目录的嵌入式解释器
    exe_dir = Path(sys.executable).parent
    for name in ("python.exe", "pythonw.exe", "python3.exe", "python", "python3"):
        candidate = exe_dir / name
        if candidate.exists():
            return str(candidate)
    # 退回系统 PATH 中的 python
    import shutil
    for name in ("python", "python3"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _schedule_self_exit(service_key: str, exit_code: int = 0) -> None:
    """
    安排当前进程延迟自杀退出（docker 模式，交由容器 restart 策略拉起）

    在后台线程中等待 _RESTART_DELAY_SECONDS 后 os._exit，
    确保当前 HTTP 响应已返回给前端。

    Args:
        service_key: 服务标识（仅用于日志）
        exit_code: 退出码
    """
    def _worker():
        time.sleep(_RESTART_DELAY_SECONDS)
        logger.info(f"[{service_key}] 进程退出以触发容器重启")
        os._exit(exit_code)

    threading.Thread(target=_worker, daemon=True, name=f"self-exit-{service_key}").start()


def restart_service(service_key: str) -> dict:
    """
    在本机重启指定服务（供服务「重启自身」时调用）

    - docker：安排当前进程延迟自杀，容器自动拉起
    - dev/frozen：派生脱离父进程的协调子进程，杀端口 + 重新拉起

    Args:
        service_key: backend-web / websocket / scheduler

    Returns:
        {'success': bool, 'mode': str, 'message': str}
    """
    if service_key not in SERVICE_META:
        return {"success": False, "mode": "", "message": f"未知服务：{service_key}"}

    label = SERVICE_META[service_key]["label"]
    mode = detect_runtime()

    try:
        if mode == "docker":
            _schedule_self_exit(service_key)
        else:
            _spawn_reviver(service_key)
        logger.info(f"触发重启 {label}（{service_key}），运行模式：{mode}")
        return {"success": True, "mode": mode, "message": f"{label}正在重启"}
    except Exception as e:
        logger.error(f"重启 {label}（{service_key}）失败：{e}")
        return {"success": False, "mode": mode, "message": f"{label}重启失败：{e}"}


# ---------------------------------------------------------------------------
# 内联协调脚本模板（在独立子进程中运行，不依赖项目内任何模块）
# 通过环境变量接收：XR_REVIVE_PORT / XR_REVIVE_DELAY / XR_REVIVE_CWD / XR_REVIVE_CMD
# ---------------------------------------------------------------------------
_REVIVER_TEMPLATE = r"""
import os, sys, time, socket, subprocess

port = int(os.environ.get("XR_REVIVE_PORT", "0"))
delay = float(os.environ.get("XR_REVIVE_DELAY", "2"))
cwd = os.environ.get("XR_REVIVE_CWD", "")
cmd = [c for c in os.environ.get("XR_REVIVE_CMD", "").split("\n") if c]

def kill_by_port(p):
    if sys.platform == "win32":
        try:
            r = subprocess.run(["netstat", "-ano", "-p", "TCP"],
                               capture_output=True, text=True, timeout=5,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            for line in r.stdout.splitlines():
                if (":%d " % p) in line and "LISTENING" in line:
                    parts = line.split()
                    pid = parts[-1].strip()
                    if pid.isdigit() and int(pid) != 0:
                        subprocess.run(["taskkill", "/F", "/PID", pid],
                                       capture_output=True, timeout=5,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception:
            pass
    else:
        pids = set()
        try:
            r = subprocess.run(["lsof", "-t", "-i:%d" % p, "-sTCP:LISTEN"],
                               capture_output=True, text=True, timeout=5)
            for x in r.stdout.split():
                if x.strip().isdigit():
                    pids.add(int(x.strip()))
        except Exception:
            try:
                r = subprocess.run(["fuser", "%d/tcp" % p],
                                   capture_output=True, text=True, timeout=5)
                for x in r.stdout.split():
                    if x.strip().isdigit():
                        pids.add(int(x.strip()))
            except Exception:
                pass
        for pid in pids:
            try:
                os.kill(pid, 9)
            except Exception:
                pass

def port_alive(p):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            s.connect(("127.0.0.1", p))
            return True
    except Exception:
        return False

# 1) 等待原响应返回
time.sleep(delay)

# 2) 杀掉旧进程；轮询确认端口释放
kill_by_port(port)
for _ in range(20):
    if not port_alive(port):
        break
    time.sleep(0.3)
    kill_by_port(port)

# 3) 重新拉起服务
if cmd:
    show_console = os.environ.get("XR_REVIVE_SHOW_CONSOLE", "1") == "1"
    kwargs = dict(cwd=(cwd or None), close_fds=True)
    if sys.platform == "win32":
        if show_console:
            # dev：弹出独立 cmd 窗口，日志实时可见（与 启动.bat 体验一致）
            # CREATE_NEW_CONSOLE=0x00000010；不重定向标准流，输出直接进新窗口
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_CONSOLE", 0x00000010)
        else:
            # frozen：隐藏窗口并丢弃标准输出（与 launcher 一致）
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            kwargs["stdin"] = subprocess.DEVNULL
            kwargs["stdout"] = subprocess.DEVNULL
            kwargs["stderr"] = subprocess.DEVNULL
    else:
        # POSIX：脱离会话，输出交由各服务自身的日志文件
        kwargs["start_new_session"] = True
        kwargs["stdin"] = subprocess.DEVNULL
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL
    try:
        subprocess.Popen(cmd, **kwargs)
    except Exception:
        pass
"""
