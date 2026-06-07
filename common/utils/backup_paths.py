"""
数据库备份文件路径工具

功能：
1. 统一解析数据库备份文件的存储根目录（优先环境变量 BACKUP_DIR，本地回退到 backups）
2. 提供根据备份文件名解析真实文件路径的方法（供 scheduler 写入、backend-web 下载共用）
3. 确保备份目录存在

说明：
- Docker 环境通过共享卷把同一目录挂载到 scheduler（读写）与 backend-web（读）
- 禁止写死绝对路径，路径统一由 BACKUP_DIR 环境变量管理
"""
from __future__ import annotations

import os
from pathlib import Path


def get_backup_root() -> Path:
    """获取数据库备份文件根目录。

    优先使用环境变量 BACKUP_DIR；为相对路径时基于当前工作目录解析。
    未配置时回退到当前工作目录下的 backups 目录。
    """
    backup_env = os.environ.get("BACKUP_DIR", "").strip()
    if backup_env:
        root = Path(backup_env)
        if not root.is_absolute():
            root = Path.cwd() / root
    else:
        root = Path.cwd() / "backups"
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


__all__ = [
    "get_backup_root",
    "ensure_backup_root",
    "resolve_backup_file",
]
