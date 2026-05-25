"""Scheduler服务启动入口（最小桩，业务逻辑见 _bootstrap.py）"""
from __future__ import annotations

import sys
import importlib.util
from pathlib import Path

# 将当前目录和项目根目录添加到 Python 路径（必须先于业务导入）
current_dir = Path(__file__).parent
project_root = current_dir.parent
sys.path.insert(0, str(current_dir))
sys.path.insert(0, str(project_root))

# 显式从当前目录加载 _bootstrap（兼容 Nuitka 打包环境）
_bootstrap_file = current_dir / "_bootstrap.py"
if _bootstrap_file.exists() and '_bootstrap' not in sys.modules:
    _spec = importlib.util.spec_from_file_location("_bootstrap", str(_bootstrap_file))
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules['_bootstrap'] = _mod
    _spec.loader.exec_module(_mod)

from _bootstrap import app  # noqa: E402

if __name__ == "__main__":
    from _bootstrap import run_server
    run_server()
