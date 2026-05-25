"""
子服务运行器

功能：
1. 作为打包后子进程的入口点
2. 接收命令行参数指定要启动的服务
3. 通过runpy.run_path执行各服务的main.py
4. 支持开发模式和打包模式（仅 .pyc 文件）

使用方式：
    python service_runner.py --service backend-web
    python service_runner.py --service websocket
    python service_runner.py --service scheduler
"""
import argparse
import os
import sys
from pathlib import Path
import importlib.abc
import importlib.machinery
import importlib.util

from launcher.frozen_detect import is_frozen, get_project_root


class PycFileLoader(importlib.abc.Loader):
    """
    自定义 .pyc 文件加载器
    
    确保正确设置 __file__ 等模块属性，支持从 .pyc 文件加载模块。
    """
    
    def __init__(self, fullname: str, pyc_path: str, is_pkg: bool = False):
        self.fullname = fullname
        self.pyc_path = pyc_path
        self._is_package = is_pkg
        # 计算对应的 .py 路径（用于 __file__）
        self.py_path = pyc_path[:-1] if pyc_path.endswith('.pyc') else pyc_path
    
    def is_package(self, fullname=None):
        """返回是否是包（spec_from_loader 会调用此方法）"""
        return self._is_package
    
    def create_module(self, spec):
        """返回 None 使用默认的模块创建机制"""
        return None
    
    def exec_module(self, module):
        """
        执行模块代码
        
        设置 __file__、__cached__、__path__ 等属性后执行字节码
        """
        import marshal
        
        # 设置模块属性
        module.__file__ = self.py_path  # 使用 .py 路径，兼容代码中的 __file__ 使用
        module.__cached__ = self.pyc_path
        module.__loader__ = self
        
        if self._is_package:
            # 包需要设置 __path__
            module.__path__ = [str(Path(self.pyc_path).parent)]
        
        # 读取 .pyc 文件并解析字节码
        with open(self.pyc_path, 'rb') as f:
            data = f.read()
        
        # .pyc 文件格式：magic(4) + bit_field(4) + [timestamp(4) + size(4) 或 hash(8)] + code
        # Python 3.7+ 使用16字节头，但为了兼容性，我们查找 code object 的起始位置
        # marshal 数据以 TYPE_CODE (0x63 = 'c') 开头
        header_size = 16  # Python 3.7+ 标准头大小
        code_data = data[header_size:]
        
        try:
            code_obj = marshal.loads(code_data)
        except Exception:
            # 如果16字节头失败，尝试其他常见大小
            for hs in (12, 8):
                try:
                    code_obj = marshal.loads(data[hs:])
                    break
                except Exception:
                    continue
            else:
                raise ValueError(f"无法解析 .pyc 文件: {self.pyc_path}")
        
        exec(code_obj, module.__dict__)


class PycFileFinder(importlib.abc.MetaPathFinder):
    """
    自定义导入查找器，支持从 .pyc 文件导入模块
    
    当目录中只有 .pyc 文件而没有 .py 文件时，Python 默认无法导入。
    此查找器会在 sys.path 中查找 .pyc 文件并加载。
    """
    
    def find_spec(self, fullname, path, target=None):
        """
        查找模块规格
        
        Args:
            fullname: 完整模块名，如 'app.api.routes'
            path: 父包的 __path__，或 None（顶级模块）
            target: 目标模块（重新加载时使用）
        Returns:
            ModuleSpec 或 None
        """
        # 将模块名转换为路径部分
        parts = fullname.split(".")
        
        # 确定搜索路径和要查找的路径部分
        if path is None:
            # 顶级模块，从 sys.path 查找完整路径
            search_paths = sys.path
            search_parts = parts
        else:
            # 子模块，从父包的 __path__ 查找最后一个部分
            search_paths = list(path)
            search_parts = [parts[-1]]
        
        for search_path in search_paths:
            search_dir = Path(search_path)
            if not search_dir.is_dir():
                continue
            
            # 构建可能的模块路径
            module_path = search_dir.joinpath(*search_parts)
            
            # 检查是否是包（目录 + __init__.pyc）
            init_pyc = module_path / "__init__.pyc"
            if init_pyc.exists():
                loader = PycFileLoader(fullname, str(init_pyc), is_pkg=True)
                spec = importlib.util.spec_from_loader(
                    fullname, loader,
                    origin=str(init_pyc),
                    is_package=True
                )
                spec.submodule_search_locations = [str(module_path)]
                return spec
            
            # 检查是否是模块文件（.pyc）
            pyc_file = module_path.with_suffix(".pyc")
            if pyc_file.exists():
                loader = PycFileLoader(fullname, str(pyc_file), is_pkg=False)
                return importlib.util.spec_from_loader(
                    fullname, loader,
                    origin=str(pyc_file),
                    is_package=False
                )
        
        return None


def _install_pyc_finder():
    """
    安装 .pyc 文件导入查找器
    
    将 PycFileFinder 添加到 sys.meta_path，使 Python 能够从 .pyc 文件导入模块。
    此函数应在打包模式下调用。
    """
    # 检查是否已安装
    for finder in sys.meta_path:
        if isinstance(finder, PycFileFinder):
            return
    # 插入到列表开头，优先使用
    sys.meta_path.insert(0, PycFileFinder())


def run_service(service_name: str) -> None:
    """
    运行指定的子服务
    
    通过设置sys.path和工作目录后，执行服务的入口文件。
    支持 main.py（开发模式）和 main.pyc（打包模式）。
    
    Args:
        service_name: 服务名称，可选 backend-web、websocket、scheduler
    """
    import runpy
    
    project_root = get_project_root()
    service_dir = project_root / service_name
    
    # 设置Python路径（service_dir 优先，确保服务自己的模块优先被导入）
    sys.path.insert(0, str(project_root))
    sys.path.insert(0, str(service_dir))
    
    # 移除已缓存的根目录 _bootstrap 模块，避免与服务目录的 _bootstrap 冲突
    if '_bootstrap' in sys.modules:
        del sys.modules['_bootstrap']
    
    # 同时从 sys.path 中移除根目录中排在 service_dir 之后的重复项
    # 确保 service_dir 的 _bootstrap.py 优先被找到
    root_str = str(project_root)
    service_str = str(service_dir)
    new_path = [service_str]
    seen_root = False
    for p in sys.path:
        if p == service_str:
            continue
        if p == root_str and not seen_root:
            seen_root = True
            new_path.append(p)
            continue
        if p == root_str:
            continue
        new_path.append(p)
    sys.path[:] = new_path
    
    # 查找入口文件
    main_py = service_dir / "main.py"
    main_pyc = service_dir / "main.pyc"
    entry_file = main_py if main_py.exists() else (main_pyc if main_pyc.exists() else None)
    
    if not entry_file:
        raise FileNotFoundError(f"找不到入口文件: {main_py} 或 {main_pyc}")
    
    # 在 Nuitka 打包环境中，必须用外部 python.exe 启动子服务，
    # 因为 Nuitka EXE 内置的 import hook 会拦截模块加载，导致找不到服务目录的 app 包。
    # 注意：此检查必须在预加载 _bootstrap 之前，否则 exec_module 会触发服务的模块级导入，
    # 而 Nuitka 内置的 import hook 会拦截这些导入导致 ModuleNotFoundError。
    if is_frozen():
        import subprocess
        # 优先使用 pythonw.exe（无控制台窗口），其次 python.exe
        python_exe = project_root / "pythonw.exe"
        if not python_exe.exists():
            python_exe = project_root / "python.exe"
        if not python_exe.exists():
            # 回退到系统 Python
            python_exe = Path(sys.executable).parent / "pythonw.exe"
            if not python_exe.exists():
                python_exe = Path(sys.executable).parent / "python.exe"
        
        env = os.environ.copy()
        env['PYTHONPATH'] = f"{service_dir}{os.pathsep}{project_root}"
        
        # Windows 下隐藏子进程窗口
        startupinfo = None
        creationflags = 0
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE
            creationflags = subprocess.CREATE_NO_WINDOW
        
        # 创建日志目录和日志文件
        logs_dir = service_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_file = logs_dir / f"{service_name}.stdout.log"
        
        # 使用 Popen 启动子进程（非阻塞），让服务在后台运行
        # 将输出重定向到日志文件
        with open(log_file, "w", encoding="utf-8") as stdout_handle:
            proc = subprocess.Popen(
                [str(python_exe), str(entry_file)],
                cwd=str(service_dir),
                env=env,
                stdout=stdout_handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                startupinfo=startupinfo,
                creationflags=creationflags,
            )
        
        # 等待一小段时间检查进程是否立即退出
        import time
        time.sleep(0.3)
        if proc.poll() is not None:
            # 进程已退出，返回错误码
            sys.exit(proc.returncode or 1)
        
        # 进程正常启动，返回成功
        sys.exit(0)
    
    # 以下为非打包环境（开发模式）的逻辑
    
    # 切换工作目录到服务目录（必须在预加载 _bootstrap 之前，因为它可能依赖工作目录）
    os.chdir(str(service_dir))
    
    # 移除 Nuitka 可能内置的 app 模块，确保从服务目录的文件系统加载
    for mod_name in list(sys.modules.keys()):
        if mod_name == 'app' or mod_name.startswith('app.'):
            del sys.modules[mod_name]
    
    # 预加载服务目录的 _bootstrap 模块到 sys.modules，
    # 防止 runpy.run_path 执行时找到根目录的 _bootstrap
    service_bootstrap = service_dir / "_bootstrap.py"
    service_bootstrap_pyc = service_dir / "_bootstrap.pyc"
    
    if service_bootstrap.exists() or service_bootstrap_pyc.exists():
        import importlib.util
        bootstrap_file = service_bootstrap if service_bootstrap.exists() else service_bootstrap_pyc
        spec = importlib.util.spec_from_file_location("_bootstrap", str(bootstrap_file))
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            sys.modules['_bootstrap'] = module
            spec.loader.exec_module(module)
    
    # 创建必要的子目录
    (service_dir / "logs").mkdir(parents=True, exist_ok=True)
    (service_dir / "static").mkdir(parents=True, exist_ok=True)
    
    # 非打包环境（开发模式）：在当前进程内执行
    if main_py.exists():
        runpy.run_path(str(main_py), run_name="__main__")
    elif main_pyc.exists():
        # 打包模式：安装 .pyc 导入钩子，然后加载入口文件
        _install_pyc_finder()
        
        # 使用自定义 PycFileLoader 加载入口文件，确保 __file__ 等属性正确设置
        loader = PycFileLoader("__main__", str(main_pyc), is_pkg=False)
        spec = importlib.util.spec_from_loader("__main__", loader, origin=str(main_pyc))
        module = importlib.util.module_from_spec(spec)
        sys.modules["__main__"] = module
        loader.exec_module(module)
    else:
        raise FileNotFoundError(f"找不到入口文件: {main_py} 或 {main_pyc}")


def main():
    """解析命令行参数并启动对应服务"""
    parser = argparse.ArgumentParser(description="闲鱼自动回复系统 - 子服务运行器")
    parser.add_argument(
        "--service",
        required=True,
        choices=["backend-web", "websocket", "scheduler"],
        help="要启动的服务名称",
    )
    args = parser.parse_args()
    run_service(args.service)


if __name__ == "__main__":
    main()
