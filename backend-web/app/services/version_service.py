"""
版本检测服务

功能：
1. 获取系统当前版本号（复用桌面启动器的版本号常量）
2. 向远程更新服务器请求 version.json，对比版本号判断是否有新版本
3. 返回统一的检测结果字典供路由层包装为 ApiResponse

说明：
- 更新服务器地址与格式跟桌面启动器（launcher/updater.py）保持一致，
  详见 data/update_config.json 与 https://xy-update.zhinianboke.com/version.json。
- 所有外部请求使用 httpx 异步客户端，超时 10 秒。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
from loguru import logger


# 默认更新服务器地址（与 launcher/updater.py 保持一致）
_DEFAULT_UPDATE_URL = "https://xy-update.zhinianboke.com"
# 远程 version.json 请求超时时间（秒）
_REMOTE_TIMEOUT_SECONDS = 10
# HTTP User-Agent，便于服务端识别来源
_USER_AGENT = "XianyuAutoReply-WebUpdater"


def get_current_version() -> str:
    """
    获取系统当前版本号

    优先复用桌面启动器的版本号常量（launcher.version.CURRENT_VERSION），
    以保证 Windows 桌面版与 Web 端版本号一致；若导入失败则尝试从
    data/version.txt 读取，最后返回空字符串由调用方决定如何向用户提示。

    Returns:
        当前版本号字符串（如 "1.0.3"），失败时返回空字符串
    """
    # 方式1：尝试从 launcher 模块读取（开发模式或完整打包时可用）
    try:
        from launcher.version import CURRENT_VERSION  # type: ignore
        version = str(CURRENT_VERSION or "").strip()
        if version:
            return version
    except Exception:
        pass

    # 方式2：从 data/version.txt 文件读取（打包后独立运行时可用）
    try:
        version_file = Path.cwd() / "data" / "version.txt"
        if version_file.exists():
            version = version_file.read_text(encoding="utf-8").strip()
            if version:
                return version
    except Exception as exc:
        logger.warning(f"从 data/version.txt 读取版本号失败: {exc}")

    # 方式3：从项目根目录的 version.txt 读取
    try:
        version_file = Path.cwd() / "version.txt"
        if version_file.exists():
            version = version_file.read_text(encoding="utf-8").strip()
            if version:
                return version
    except Exception as exc:
        logger.warning(f"从 version.txt 读取版本号失败: {exc}")

    return ""


def _get_update_url() -> str:
    """
    获取更新服务器基础 URL

    读取顺序：
    1. data/update_config.json 中的 update_url 字段
    2. 默认地址 _DEFAULT_UPDATE_URL

    Returns:
        基础 URL（不含尾部斜杠）
    """
    try:
        # 以项目根为基准（Docker 里 WORKDIR=/app，根目录下有 data/）
        config_path = Path.cwd() / "data" / "update_config.json"
        if config_path.exists():
            data = json.loads(config_path.read_text(encoding="utf-8"))
            url = str(data.get("update_url", "") or "").strip().rstrip("/")
            if url:
                return url
    except Exception as exc:
        logger.warning(f"读取更新服务器配置失败，使用默认地址: {exc}")
    return _DEFAULT_UPDATE_URL


def _compare_versions(local: str, remote: str) -> bool:
    """
    比较版本号，判断远程版本是否比本地新

    规则：按点分割后逐段比较整数值，忽略非数字前缀（如开头的 "v"）。

    Args:
        local: 本地版本号
        remote: 远程版本号

    Returns:
        True 表示远程更新需要升级；False 表示本地已是最新或无法比较
    """
    def _normalize(ver: str) -> list[int]:
        raw = (ver or "").strip().lstrip("vV")
        parts: list[int] = []
        for seg in raw.split("."):
            try:
                parts.append(int(seg))
            except ValueError:
                # 非数字段视为 0，避免抛异常
                parts.append(0)
        return parts

    try:
        local_parts = _normalize(local)
        remote_parts = _normalize(remote)
        # 补齐长度，短的补 0
        max_len = max(len(local_parts), len(remote_parts))
        local_parts += [0] * (max_len - len(local_parts))
        remote_parts += [0] * (max_len - len(remote_parts))
        return remote_parts > local_parts
    except Exception:
        return False


async def check_update() -> dict[str, Any]:
    """
    检查是否有新版本可用

    调用远程 ``{update_url}/version.json`` 获取最新版本信息，
    与本地版本号比较后返回统一结构。网络错误、解析错误等情况
    由调用方转换为 ApiResponse 的 success=False 返回给前端。

    Returns:
        字典：
          - has_update: bool 是否有新版本
          - current_version: str 当前版本号
          - remote_version: str 远程版本号（失败时为空）
          - description: str 更新说明
          - filename: str 下载文件名
          - download_url: str 完整下载地址
          - error: str 错误信息（正常时为空）
    """
    current_version = get_current_version()
    result: dict[str, Any] = {
        "has_update": False,
        "current_version": current_version,
        "remote_version": "",
        "description": "",
        "filename": "",
        "download_url": "",
        "error": "",
    }

    if not current_version:
        result["error"] = "无法读取当前版本号"
        return result

    update_url = _get_update_url()
    version_url = f"{update_url}/version.json"

    try:
        async with httpx.AsyncClient(timeout=_REMOTE_TIMEOUT_SECONDS) as client:
            response = await client.get(
                version_url,
                headers={"User-Agent": _USER_AGENT},
            )
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException:
        result["error"] = "连接更新服务器超时，请稍后重试"
        return result
    except httpx.HTTPStatusError as exc:
        result["error"] = f"更新服务器返回错误状态码: {exc.response.status_code}"
        return result
    except httpx.HTTPError as exc:
        result["error"] = f"无法连接更新服务器: {exc}"
        return result
    except json.JSONDecodeError:
        result["error"] = "更新服务器返回的数据格式无效"
        return result
    except Exception as exc:
        logger.exception("检查更新失败")
        result["error"] = f"检查更新失败: {exc}"
        return result

    remote_version = str(data.get("version", "") or "").strip()
    if not remote_version:
        result["error"] = "更新服务器未返回版本号"
        return result

    filename = str(data.get("filename", "") or "").strip()
    result["remote_version"] = remote_version
    result["description"] = str(data.get("description", "") or "").strip() or "无更新说明"
    result["filename"] = filename
    result["download_url"] = f"{update_url}/{filename}" if filename else ""
    result["has_update"] = _compare_versions(current_version, remote_version)

    return result
