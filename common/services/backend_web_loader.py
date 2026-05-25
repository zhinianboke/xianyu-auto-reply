"""
Backend-Web 共享加载器

功能：
1. 按文件路径动态加载 backend-web 中可复用的服务模块
2. 为 common 共享层提供统一的类加载能力
"""
from __future__ import annotations

import importlib.util
import sys
from functools import lru_cache
from pathlib import Path
from types import ModuleType


@lru_cache
def _get_repo_root() -> Path:
    """返回仓库根目录。"""
    return Path(__file__).resolve().parents[2]


@lru_cache
def _load_backend_web_module(module_name: str, relative_path: str) -> ModuleType:
    """按相对路径加载 backend-web 模块。"""
    source_path = _get_repo_root() / relative_path
    if not source_path.exists():
        raise FileNotFoundError(f"未找到 backend-web 模块文件: {source_path}")

    repo_root = str(_get_repo_root())
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    spec = importlib.util.spec_from_file_location(module_name, source_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 backend-web 模块: {source_path}")

    module = sys.modules.get(module_name)
    if module is None:
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    return module


@lru_cache
def load_backend_web_class(module_name: str, relative_path: str, class_name: str):
    """加载 backend-web 模块中的指定类。"""
    module = _load_backend_web_module(module_name, relative_path)
    target_class = getattr(module, class_name, None)
    if target_class is None:
        raise ImportError(f"模块 {module_name} 中不存在类 {class_name}")
    return target_class
