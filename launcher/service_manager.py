"""
服务进程管理模块

功能：
1. 启动4个子服务（backend-web、websocket、scheduler、前端静态服务）
2. 管理子进程生命周期
3. 生成各服务的.env配置文件
4. 前端使用带API代理功能的HTTP服务器托管dist静态文件
5. 支持开发模式（subprocess）和打包模式（standalone目录内subprocess）
"""
import functools
import http.server
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

from launcher.process_utils import kill_process_tree, kill_by_port, check_port
from launcher.frozen_detect import is_frozen, get_project_root
from typing import Optional


# 前端代理目标配置
# 注意：/static/uploads/ 代理到后端（上传文件），其余/static/由前端静态服务器直接提供
_PROXY_RULES = {
    "/api/": "http://127.0.0.1:8089",
    "/static/uploads/": "http://127.0.0.1:8089",
}


class FrontendHandler(http.server.SimpleHTTPRequestHandler):
    """
    前端静态文件服务器请求处理器
    
    功能：
    1. 托管前端dist目录的静态文件
    2. 对/api/和/static/请求代理到后端服务
    3. 对SPA路由返回index.html（Vue/React路由兼容）
    """
    
    def __init__(self, *args, dist_dir: str = "", **kwargs):
        """初始化，设置dist目录"""
        self._dist_dir = dist_dir
        super().__init__(*args, directory=dist_dir, **kwargs)
    
    def do_GET(self):
        """处理GET请求，支持代理和SPA路由回退"""
        # 检查是否需要代理
        for prefix, target in _PROXY_RULES.items():
            if self.path.startswith(prefix):
                self._proxy_request(target)
                return
        
        # 检查静态文件是否存在，不存在则回退到index.html（SPA路由）
        file_path = Path(self._dist_dir) / self.path.lstrip("/").split("?")[0]
        if not file_path.exists() and not file_path.suffix:
            self.path = "/index.html"
        
        super().do_GET()
    
    def do_POST(self):
        """处理POST请求，代理到后端"""
        for prefix, target in _PROXY_RULES.items():
            if self.path.startswith(prefix):
                self._proxy_request(target)
                return
        self.send_error(404)
    
    def do_PUT(self):
        """处理PUT请求，代理到后端"""
        for prefix, target in _PROXY_RULES.items():
            if self.path.startswith(prefix):
                self._proxy_request(target)
                return
        self.send_error(404)
    
    def do_DELETE(self):
        """处理DELETE请求，代理到后端"""
        for prefix, target in _PROXY_RULES.items():
            if self.path.startswith(prefix):
                self._proxy_request(target)
                return
        self.send_error(404)
    
    def _proxy_request(self, target_base: str):
        """
        将请求代理到后端服务
        
        Args:
            target_base: 后端服务基地址，如 http://127.0.0.1:8089
        """
        try:
            target_url = f"{target_base}{self.path}"
            
            # 读取请求体
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length > 0 else None
            
            # 构建代理请求
            req = urllib.request.Request(target_url, data=body, method=self.command)
            
            # 复制请求头（排除Host）
            for header, value in self.headers.items():
                if header.lower() not in ("host", "content-length"):
                    req.add_header(header, value)
            
            # 发送请求
            with urllib.request.urlopen(req, timeout=90) as resp:
                self.send_response(resp.status)
                for header, value in resp.getheaders():
                    if header.lower() not in ("transfer-encoding",):
                        self.send_header(header, value)
                self.end_headers()
                self.wfile.write(resp.read())
        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            error_msg = f'{{"success":false,"code":502,"message":"代理请求失败: {str(e)}","data":null}}'
            self.wfile.write(error_msg.encode("utf-8"))
    
    def log_message(self, format, *args):
        """抑制日志输出，避免控制台刷屏"""
        pass


class ServiceManager:
    """
    服务进程管理器
    
    负责启动、监控、停止4个子服务进程。
    支持两种模式：
    - 开发模式：用当前Python解释器subprocess启动各服务main.py
    - 打包模式：standalone目录中包含完整Python运行时，同样用subprocess启动
    """
    
    def __init__(self, project_root: Path):
        """
        初始化服务管理器
        
        Args:
            project_root: 项目根目录路径
        """
        self.project_root = project_root
        self._processes: dict[str, subprocess.Popen] = {}
        self._frontend_thread: Optional[threading.Thread] = None
        self._frontend_server = None
        self._stopped = False
        self._service_errors: dict[str, str] = {}
        self._log_handles: dict[str, object] = {}
    
    def _get_python_exe(self) -> str:
        """
        获取Python解释器路径
        
        打包后standalone目录中优先使用pythonw.exe（无窗口版本），
        避免启动子服务时弹出控制台窗口。
        开发模式使用当前解释器。
        
        Returns:
            Python解释器路径
        """
        if is_frozen():
            # Nuitka standalone模式下，优先使用pythonw.exe（无窗口版本）
            exe_dir = Path(sys.executable).parent
            for name in ("pythonw.exe", "python.exe", "python3.exe", "python"):
                candidate = exe_dir / name
                if candidate.exists():
                    return str(candidate)
            # 未找到嵌入式解释器，返回空字符串以便上层抛错
            return ""
        return sys.executable
    
    def generate_env_files(self, config: dict) -> None:
        """
        根据用户配置生成各服务的.env文件
        
        Args:
            config: 包含mysql和redis配置信息的字典
                - mysql_host, mysql_port, mysql_user, mysql_password, mysql_database
                - redis_host, redis_port, redis_password, redis_db
        """
        # 数据库备份目录：backend-web 与 scheduler 必须指向同一绝对路径，
        # 否则 scheduler 写入的备份文件 backend-web 无法读取下载（本地源码模式各服务 cwd 不同）
        backup_dir = (self.project_root / "backups").as_posix()

        # backend-web .env
        backend_env = (
            f"ENVIRONMENT=production\n"
            f"LOG_LEVEL=INFO\n"
            f"MYSQL_HOST={config['mysql_host']}\n"
            f"MYSQL_PORT={config['mysql_port']}\n"
            f"MYSQL_USER={config['mysql_user']}\n"
            f"MYSQL_PASSWORD={config['mysql_password']}\n"
            f"MYSQL_DATABASE={config['mysql_database']}\n"
            f"REDIS_HOST={config['redis_host']}\n"
            f"REDIS_PORT={config['redis_port']}\n"
            f"REDIS_PASSWORD={config['redis_password']}\n"
            f"REDIS_DB={config['redis_db']}\n"
            f"BACKEND_WEB_PORT=8089\n"
            f"JWT_ALGORITHM=HS256\n"
            f"ACCESS_TOKEN_EXPIRE_MINUTES=30\n"
            f"REFRESH_TOKEN_EXPIRE_MINUTES=10080\n"
            f"CORS_ORIGINS=*\n"
            f"WEBSOCKET_SERVICE_URL=http://127.0.0.1:8090\n"
            f"SCHEDULER_SERVICE_URL=http://127.0.0.1:8091\n"
            f"STATIC_DIR=static\n"
            f"BACKUP_DIR={backup_dir}\n"
            f"FRONTEND_PUBLIC_URL=http://127.0.0.1:9000\n"
            f"BACKEND_WEB_PUBLIC_URL=http://127.0.0.1:8089\n"
        )
        
        # websocket .env
        websocket_env = (
            f"ENVIRONMENT=production\n"
            f"LOG_LEVEL=INFO\n"
            f"MYSQL_HOST={config['mysql_host']}\n"
            f"MYSQL_PORT={config['mysql_port']}\n"
            f"MYSQL_USER={config['mysql_user']}\n"
            f"MYSQL_PASSWORD={config['mysql_password']}\n"
            f"MYSQL_DATABASE={config['mysql_database']}\n"
            f"REDIS_HOST={config['redis_host']}\n"
            f"REDIS_PORT={config['redis_port']}\n"
            f"REDIS_PASSWORD={config['redis_password']}\n"
            f"REDIS_DB={config['redis_db']}\n"
            f"WEBSOCKET_PORT=8090\n"
            f"MAX_CAPTCHA_CONCURRENT=1\n"
            f"BROWSER_HEADLESS=true\n"
            f"TOKEN_REFRESH_INTERVAL=72000\n"
            f"TOKEN_RETRY_INTERVAL=7200\n"
            f"BACKEND_WEB_SERVICE_URL=http://127.0.0.1:8089\n"
            f"STATIC_DIR=static\n"
        )
        
        # scheduler .env
        scheduler_env = (
            f"ENVIRONMENT=production\n"
            f"LOG_LEVEL=INFO\n"
            f"MYSQL_HOST={config['mysql_host']}\n"
            f"MYSQL_PORT={config['mysql_port']}\n"
            f"MYSQL_USER={config['mysql_user']}\n"
            f"MYSQL_PASSWORD={config['mysql_password']}\n"
            f"MYSQL_DATABASE={config['mysql_database']}\n"
            f"REDIS_HOST={config['redis_host']}\n"
            f"REDIS_PORT={config['redis_port']}\n"
            f"REDIS_PASSWORD={config['redis_password']}\n"
            f"REDIS_DB={config['redis_db']}\n"
            f"SCHEDULER_PORT=8091\n"
            f"REDELIVERY_INTERVAL=5\n"
            f"RATE_INTERVAL=20\n"
            f"WEBSOCKET_SERVICE_URL=http://127.0.0.1:8090\n"
            f"BACKEND_WEB_SERVICE_URL=http://127.0.0.1:8089\n"
            f"STATIC_DIR=static\n"
            f"BACKUP_DIR={backup_dir}\n"
        )
        
        env_map = {
            "backend-web": backend_env,
            "websocket": websocket_env,
            "scheduler": scheduler_env,
        }
        
        for service_name, env_content in env_map.items():
            env_path = self.project_root / service_name / ".env"
            env_path.write_text(env_content, encoding="utf-8")
    
    def start_python_service(self, name: str, service_dir: str) -> bool:
        """
        启动一个Python子服务
        
        开发模式：用Python解释器直接执行子服务的main.py
        打包模式：用编译后的exe调用service_runner --service xxx
        PYTHONPATH设为项目根目录以确保common模块可被导入。
        
        Args:
            name: 服务名称（用于日志和管理）
            service_dir: 服务目录名（相对于项目根目录）
        Returns:
            True启动成功，False启动失败
        """
        try:
            cwd = self.project_root / service_dir
            main_py = cwd / "main.py"
            main_pyc = cwd / "main.pyc"
            
            # 仅在开发模式下检查入口文件是否存在；
            # 打包模式由 service_runner 通过 import __pycache__ 自动加载
            entry_file = None
            if not is_frozen():
                if not main_py.exists() and not main_pyc.exists():
                    self._service_errors[name] = f"找不到 {main_py} 或 {main_pyc}"
                    return False
                # 确定实际的入口文件
                entry_file = main_py if main_py.exists() else main_pyc
            
            # 设置环境变量，确保能找到common模块
            env = os.environ.copy()
            env["PYTHONPATH"] = str(self.project_root)
            # 确保使用UTF-8编码
            env["PYTHONIOENCODING"] = "utf-8"
            from launcher.browser_setup import ensure_playwright_browser_path
            browser_dir = ensure_playwright_browser_path()
            if browser_dir:
                env["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_dir)
            
            # 创建日志目录
            logs_dir = cwd / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            
            # 创建静态文件目录
            static_dir = cwd / "static"
            static_dir.mkdir(parents=True, exist_ok=True)
            
            # 根据运行模式选择启动方式：
            # - 打包(frozen)模式：调用已编译的主exe，传入 --run-service 参数，避免依赖缺失与多开GUI
            # - 开发模式：使用当前Python解释器直接执行服务的 main.py/.pyc
            if is_frozen():
                # 直接调用已编译的主exe，传入 --run-service 参数
                # 同时通过环境变量传递以防argv丢失（双保险）
                cmd = [sys.executable, "--run-service", service_dir]
                env["XR_RUN_SERVICE"] = service_dir
            else:
                python_exe = self._get_python_exe()
                if not python_exe or not Path(python_exe).exists():
                    self._service_errors[name] = "未找到可用的 Python 解释器"
                    return False
                cmd = [python_exe, str(entry_file)]
            
            # 将子进程输出重定向到日志文件，避免GUI模式下句柄无效
            log_file = logs_dir / f"{name}.stdout.log"
            stdout_handle = open(str(log_file), "w", encoding="utf-8")
            
            # Windows下隐藏子进程窗口（防止弹出多余窗口）
            startupinfo = None
            creationflags = 0
            if sys.platform == "win32":
                creationflags = subprocess.CREATE_NO_WINDOW
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0  # SW_HIDE

            process = subprocess.Popen(
                cmd,
                cwd=str(cwd),
                env=env,
                stdout=stdout_handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=creationflags,
                startupinfo=startupinfo,
            )
            
            # 等待短暂时间检查是否立即退出
            time.sleep(0.5)
            if process.poll() is not None:
                # 进程已退出，从日志文件读取错误信息
                stdout_handle.close()
                try:
                    error_output = log_file.read_text(encoding="utf-8", errors="replace")
                    self._service_errors[name] = error_output[:200] if error_output else "进程启动后立即退出"
                except Exception:
                    self._service_errors[name] = "进程启动后立即退出"
                return False
            
            # 保存文件句柄，进程停止时关闭
            self._log_handles[name] = stdout_handle
            
            self._processes[name] = process
            self._service_errors.pop(name, None)
            return True
        except Exception as e:
            self._service_errors[name] = str(e)
            return False
    
    def start_frontend_server(self, port: int = 9000) -> bool:
        """
        启动前端静态文件服务器
        
        使用内置HTTP服务器托管frontend/dist目录，
        并提供API代理功能将/api/和/static/请求转发到后端。
        
        Args:
            port: 前端服务端口号
        Returns:
            True启动成功，False启动失败
        """
        dist_dir = self.project_root / "frontend" / "dist"
        if not dist_dir.exists():
            self._service_errors["frontend"] = f"前端dist目录不存在: {dist_dir}"
            return False
        
        dist_dir_str = str(dist_dir)
        
        def _serve():
            """在子线程中运行静态文件服务器"""
            try:
                handler = functools.partial(FrontendHandler, dist_dir=dist_dir_str)
                self._frontend_server = http.server.HTTPServer(
                    ("0.0.0.0", port), handler
                )
                self._frontend_server.serve_forever()
            except Exception as e:
                self._service_errors["frontend"] = str(e)
        
        self._frontend_thread = threading.Thread(target=_serve, daemon=True)
        self._frontend_thread.start()
        # 等待服务器启动
        time.sleep(0.3)
        self._service_errors.pop("frontend", None)
        return True
    
    def start_all(self, config: dict) -> dict[str, bool]:
        """
        启动所有服务
        
        Args:
            config: 数据库和Redis配置信息
        Returns:
            各服务启动状态字典
        """
        import urllib.request
        import urllib.error
        
        # 先生成.env配置文件
        self.generate_env_files(config)
        
        results = {}
        
        # 启动3个Python后端服务，按依赖顺序启动
        services = [
            ("backend-web", "backend-web", 8089),
            ("websocket", "websocket", 8090),
            ("scheduler", "scheduler", 8091),
        ]
        
        for name, service_dir, port in services:
            results[name] = self.start_python_service(name, service_dir)
            
            if not results[name]:
                # 启动失败，跳过等待
                continue
            
            # 等待服务健康检查通过（最多等待 30 秒）
            health_url = f"http://127.0.0.1:{port}/health"
            max_wait = 30
            waited = 0
            interval = 0.5
            
            while waited < max_wait:
                try:
                    req = urllib.request.Request(health_url, method='GET')
                    with urllib.request.urlopen(req, timeout=2) as resp:
                        if resp.status == 200:
                            break
                except (urllib.error.URLError, OSError):
                    pass
                time.sleep(interval)
                waited += interval
            
            if waited >= max_wait:
                # 超时但进程还在运行，记录警告但继续
                pass
        
        # 启动前端静态服务
        results["frontend"] = self.start_frontend_server(9000)
        
        return results
    
    def stop_all(self) -> None:
        """
        停止所有服务进程
        
        先尝试正常终止子进程，再通过端口杀进程确保彻底停止。
        """
        self._stopped = True
        
        # 停止前端服务器（在子线程中shutdown，避免阻塞）
        if self._frontend_server:
            t = threading.Thread(target=self._shutdown_frontend, daemon=True)
            t.start()
            t.join(timeout=1)  # 最多等1秒
        
        # 终止所有Python子进程（包括子进程树）
        for name, process in self._processes.items():
            kill_process_tree(process.pid)
        
        # 等待进程退出
        for name, process in self._processes.items():
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
        
        # 通过端口强杀残留进程，确保端口被释放
        for port in [8089, 8090, 8091, 9000]:
            kill_by_port(port)
        
        # 关闭日志文件句柄
        for name, handle in self._log_handles.items():
            try:
                handle.close()
            except Exception:
                pass
        self._log_handles.clear()
        
        self._processes.clear()
        self._stopped = False
    
    def _shutdown_frontend(self):
        """在子线程中关闭前端HTTP服务器，避免阻塞主流程"""
        try:
            self._frontend_server.shutdown()
        except Exception:
            pass
    
    def get_status(self) -> dict[str, str]:
        """
        获取所有服务的运行状态
        
        纯端口检测，不依赖_processes字典，
        即使stop_all清空了_processes也能正确检测。
        
        Returns:
            各服务状态字典，值为 "运行中" 或 "已停止"
        """
        # 所有服务及其端口（固定列表，不依赖_processes）
        all_services = {
            "backend-web": 8089,
            "websocket": 8090,
            "scheduler": 8091,
            "frontend": 9000,
        }
        
        status = {}
        for name, port in all_services.items():
            status[name] = "运行中" if check_port(port) else "已停止"
        
        return status
    
    def get_errors(self) -> dict[str, str]:
        """
        获取各服务的错误信息
        
        Returns:
            服务名 -> 错误信息 的字典，无错误的服务不包含在内
        """
        return dict(self._service_errors)
