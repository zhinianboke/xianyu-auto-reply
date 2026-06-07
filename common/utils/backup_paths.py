"""
数据库备份文件路径工具

功能：
1. 统一解析数据库备份文件的存储根目录（优先环境变量 BACKUP_DIR，本地回退到 backups）
2. 提供根据备份文件名解析真实文件路径的方法（供 scheduler 写入、backend-web 下载共用）
3. 确保备份目录存在

说明：
- Docker 环境通过共享卷把同一目录挂载到 scheduler（读写）与 backend-web（读）
- 路径统一由配置项 backup_dir（环境变量 BACKUP_DIR 或 .env 文件）管理，禁止写死
"""
from __future__ import annotations

import os
from pathlib import Path

from common.core.config import get_settings

# 项目根目录：common/utils/backup_paths.py -> common/utils -> common -> 项目根
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_backup_root() -> Path:
    """获取数据库备份文件根目录。

    优先级：
    1. 配置项 backup_dir（由 pydantic 从环境变量或 .env 文件加载，二者都能覆盖）
    2. 环境变量 BACKUP_DIR（兜底，防止个别进程未走配置系统）
    3. 未配置时回退到 backups

    相对路径统一基于「项目根目录」解析，而非当前工作目录（cwd）。
    原因：源码运行时 scheduler 与 backend-web 的 cwd 不同，若基于 cwd 解析相对路径，
    两个服务会指向不同目录，导致 scheduler 写入的备份文件 backend-web 无法读取下载。
    基于项目根解析可保证两服务始终指向同一目录。
    """
    backup_value = ""
    try:
        backup_value = (get_settings().backup_dir or "").strip()
    except Exception:
        backup_value = ""
    if not backup_value:
        backup_value = os.environ.get("BACKUP_DIR", "").strip()
    if not backup_value:
        backup_value = "backups"

    root = Path(backup_value)
    if not root.is_absolute():
        root = _PROJECT_ROOT / root
    return root


def ensure_backup_root() -> Path:
    """确保备份目录存在并返回该目录路径。"""
    root = get_backup_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_backup_file(file_name: str) -> Path | None:
    """根据备份文件名解析真实文件路径，做安全校验防止路径穿越。

    Args:
        file_name: 备份文件名（仅文件名，不含目录）。

    Returns:
        合法且存在时返回文件路径，否则返回 None。
    """
    if not file_name:
        return None
    # 仅允许纯文件名，拒绝包含路径分隔符或上跳的非法输入，防止目录穿越
    if "/" in file_name or "\\" in file_name or ".." in file_name:
        return None
    root = get_backup_root()
    target = (root / file_name).resolve()
    try:
        # 确保目标文件仍在备份根目录内
        target.relative_to(root.resolve())
    except ValueError:
        return None
    if not target.is_file():
        return None
    return target


def locate_backup_file(file_name: str | None, file_path: str | None) -> Path | None:
    """定位可下载的备份文件，兼容多种路径来源。

    解析顺序：
    1. 按文件名在「当前备份目录」中查找（最稳，且带路径穿越防护）
    2. 回退到日志记录中保存的绝对路径 file_path（兼容备份目录配置变化、
       或 scheduler 与 backend-web 目录解析存在差异的情况）

    Args:
        file_name: 备份文件名（仅文件名）。
        file_path: 备份记录中保存的绝对路径。

    Returns:
        文件存在时返回路径，否则返回 None。
    """
    # 1. 优先按文件名在当前备份目录解析（安全、可控）
    resolved = resolve_backup_file(file_name) if file_name else None
    if resolved:
        return resolved

    # 2. 回退到记录中保存的绝对路径（同机/同共享卷下依然有效）
    if file_path:
        candidate = Path(file_path)
        if candidate.is_file():
            return candidate

    return None


__all__ = [
    "get_backup_root",
    "ensure_backup_root",
    "resolve_backup_file",
    "locate_backup_file",
]
