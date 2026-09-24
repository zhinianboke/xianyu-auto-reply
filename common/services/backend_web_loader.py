"""
Backend-Web 共享加载器

功能：
1. 按文件路径动态加载 backend-web 中可复用的服务模块
2. 为 common 共享层提供统一的类加载能力
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
from functools import lru_cache
from pathlib import Path
from types import ModuleType


def _prepare_backend_web_package_paths(source_path: Path) -> None:
    """让动态加载的 backend-web 模块能够解析其 ``app`` 包内依赖。

    scheduler、websocket 和 promotion 都有各自的 ``app`` 包。共享层从这些
    服务调用动态加载器时，Python 可能已经把其他服务的 ``app.services``
    加载进 sys.modules，导致 backend-web 的同名模块无法被发现。将
    backend-web 的包目录加入已加载包的搜索路径即可保持各服务隔离，同时
    不覆盖调用方已经使用的 ``app`` 包。
    """
    # source_path: backend-web/app/<package>/<module>.py
    backend_app_root = source_path.parents[1]
    backend_parent = str(backend_app_root.parent)
    app_module = sys.modules.get("app")
    if app_module is None:
        if backend_parent not in sys.path:
            sys.path.insert(0, backend_parent)
        return

    app_paths = getattr(app_module, "__path__", None)
    if app_paths is None:
        if backend_parent not in sys.path:
            sys.path.insert(0, backend_parent)
        return
    if app_paths is not None and str(backend_app_root) not in app_paths:
        app_paths.append(str(backend_app_root))

    # 先加载调用方自己的 app 子包，避免 backend-web 的同名包覆盖 scheduler
    # 或 websocket；加载后再为这些包追加 backend-web 的模块搜索路径。
    package_parts = source_path.parent.relative_to(backend_app_root).parts
    package_names = {"app.core", "app.services"}
    package_names.update(
        "app." + ".".join(package_parts[:depth]) for depth in range(1, len(package_parts) + 1)
    )
    for package_name in sorted(package_names):
        if package_name not in sys.modules:
            importlib.import_module(package_name)

    # 已加载的 app.services/app.core 等子包也需要同步扩展搜索路径。
    app_prefix = "app."
    for module_name, module in list(sys.modules.items()):
        if not module_name.startswith(app_prefix):
            continue
        module_paths = getattr(module, "__path__", None)
        if module_paths is None:
            continue
        suffix = module_name[len(app_prefix) :].replace(".", "/")
        package_path = backend_app_root / suffix
        if package_path.is_dir() and str(package_path) not in module_paths:
            module_paths.append(str(package_path))


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

    _prepare_backend_web_package_paths(source_path)

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
