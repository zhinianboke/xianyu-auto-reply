"""
GUI启动器界面

功能：
1. 显示机器码，支持一键复制
2. 输入激活码并验证
3. 激活后显示MySQL/Redis配置表单
4. 验证连接成功后保存配置并启动所有服务
5. 显示各服务运行状态
"""
import sys
import threading
import tkinter as tk
import tkinter.messagebox as messagebox
import tkinter.ttk as ttk
from pathlib import Path

from launcher.hardware_id import generate_machine_id
from launcher.activation import (
    verify_activation_code,
    renew_license,
    save_license,
    load_and_verify_license,
    format_expire_time,
    get_remaining_text,
)
from launcher.db_checker import check_mysql_connection, check_redis_connection
from launcher.config_store import save_connection_config, load_connection_config
from launcher.service_manager import ServiceManager
from launcher.gui_theme import (
    COLORS as _COLORS,
    setup_styles,
    make_card,
    make_header,
    build_form_fields,
)
from launcher.gui_running import show_running_page
from launcher.browser_setup import check_and_install_chromium, is_chromium_installed


class LauncherApp:
    """
    启动器主界面类
    
    管理激活流程、配置填写、服务启动的完整生命周期
    使用蓝白主题，现代化卡片式布局
    """
    
    # 窗口尺寸
    WINDOW_WIDTH = 960
    WINDOW_HEIGHT = 720
    
    def __init__(self):
        """初始化启动器界面"""
        self.root = tk.Tk()
        self.root.title("闲鱼自动回复系统")
        self.root.resizable(True, True)
        self.root.configure(bg=_COLORS["bg"])
        
        # 居中显示
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w - self.WINDOW_WIDTH) // 2
        y = (screen_h - self.WINDOW_HEIGHT) // 2
        self.root.geometry(f"{self.WINDOW_WIDTH}x{self.WINDOW_HEIGHT}+{x}+{y}")
        
        # 项目根目录
        from launcher.frozen_detect import get_project_root
        self.project_root = get_project_root()
        
        # 生成机器码
        self.machine_id = generate_machine_id()
        
        # 服务管理器
        self.service_manager = ServiceManager(self.project_root)
        
        # 当前页面标识
        self._current_page = None
        
        # 样式配置
        self._setup_styles()
        
        # 异步加载窗口图标（微信公众号二维码）
        self._load_window_icon()
        
        # 根据激活状态决定显示哪个页面
        self._check_and_show_page()
        
        # 关闭窗口时停止所有服务
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _setup_styles(self):
        """配置ttk样式主题（委托给gui_theme模块）"""
        setup_styles()
    
    def _load_window_icon(self):
        """异步下载微信公众号图片并设置为窗口图标和任务栏图标"""
        def _download():
            try:
                import gzip
                import io
                import tempfile
                import urllib.request
                url = "https://xy.zhinianboke.com/static/qrcode/wechat-official-group.jpg"
                req = urllib.request.Request(url)
                req.add_header("User-Agent", "XianyuAutoReply-GUI")
                req.add_header("Accept-Encoding", "gzip, deflate")
                with urllib.request.urlopen(req, timeout=10) as resp:
                    raw = resp.read()
                if raw[:2] == b'\x1f\x8b':
                    raw = gzip.decompress(raw)
                from PIL import Image
                img = Image.open(io.BytesIO(raw))
                # 生成多尺寸ico文件（Windows任务栏需要ico格式）
                ico_path = Path(tempfile.gettempdir()) / "xianyu_icon.ico"
                sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
                img.save(str(ico_path), format="ICO", sizes=sizes)
                self.root.after(0, lambda: self._set_icon(ico_path, img))
            except Exception:
                pass
        threading.Thread(target=_download, daemon=True).start()
    
    def _set_icon(self, ico_path, pil_img):
        """
        在主线程中设置窗口图标和任务栏图标

        Windows下仅使用iconbitmap（.ico文件），可同时覆盖标题栏和任务栏图标。
        """
        try:
            self.root.iconbitmap(str(ico_path))
        except Exception:
            # 回退到iconphoto（仅标题栏生效）
            try:
                from PIL import ImageTk
                photo = ImageTk.PhotoImage(pil_img.resize((48, 48)))
                self._icon_photo = photo
                self.root.iconphoto(True, photo)
            except Exception:
                pass
    
    def _clear_page(self):
        """清除当前页面所有组件"""
        for widget in self.root.winfo_children():
            widget.destroy()
    
    def _check_and_show_page(self):
        """检查激活状态并显示对应页面"""
        result = load_and_verify_license(self.machine_id)
        if result["valid"]:
            self._show_config_page()
        else:
            self._show_activation_page(result["message"])
    
    # ==================== 激活页面 ====================
    
    def _show_activation_page(self, hint_message: str = ""):
        """
        显示激活页面
        
        Args:
            hint_message: 页面顶部的提示信息
        """
        self._clear_page()
        self._current_page = "activation"
        
        container = tk.Frame(self.root, bg=_COLORS["bg"])
        container.pack(fill=tk.BOTH, expand=True)
        
        # 页面标题
        make_header(container, "闲鱼自动回复系统", "请先完成软件激活")
        
        # 提示信息
        if hint_message:
            hint_card = tk.Frame(container, bg=_COLORS["warning_bg"], padx=12, pady=8)
            hint_card.pack(fill=tk.X, padx=20, pady=(0, 12))
            tk.Label(hint_card, text=f"  {hint_message}",
                     font=("微软雅黑", 9), fg="#92400e", bg=_COLORS["warning_bg"],
                     anchor=tk.W).pack(fill=tk.X)
        
        # 机器码卡片
        id_card = make_card(container)
        tk.Label(id_card, text="机器码", font=("微软雅黑", 11, "bold"),
                 fg=_COLORS["primary"], bg=_COLORS["card_bg"]).pack(anchor=tk.W)
        tk.Label(id_card, text="请将以下机器码发送给管理员获取激活码或续期码",
                 font=("微软雅黑", 9), fg=_COLORS["text_secondary"],
                 bg=_COLORS["card_bg"]).pack(anchor=tk.W, pady=(2, 8))
        
        # 机器码显示行
        id_row = tk.Frame(id_card, bg=_COLORS["card_bg"])
        id_row.pack(fill=tk.X)
        
        self._machine_id_var = tk.StringVar(value=self.machine_id)
        machine_entry = ttk.Entry(
            id_row, textvariable=self._machine_id_var,
            state="readonly", font=("Consolas", 12), justify=tk.CENTER,
        )
        machine_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        ttk.Button(id_row, text="复制机器码", style="Normal.TButton",
                   command=self._copy_machine_id).pack(side=tk.RIGHT)
        
        # 激活码卡片
        act_card = make_card(container)
        tk.Label(act_card, text="激活码 / 续期码", font=("微软雅黑", 11, "bold"),
                 fg=_COLORS["primary"], bg=_COLORS["card_bg"]).pack(anchor=tk.W)
        tk.Label(act_card, text="请输入管理员提供的激活码或续期码",
                 font=("微软雅黑", 9), fg=_COLORS["text_secondary"],
                 bg=_COLORS["card_bg"]).pack(anchor=tk.W, pady=(2, 8))
        
        self._activation_var = tk.StringVar()
        ttk.Entry(
            act_card, textvariable=self._activation_var,
            font=("Consolas", 12), justify=tk.CENTER,
        ).pack(fill=tk.X)
        
        # 激活按钮
        btn_area = tk.Frame(container, bg=_COLORS["bg"])
        btn_area.pack(fill=tk.X, padx=20, pady=(4, 0))
        ttk.Button(btn_area, text="进入系统", style="Primary.TButton",
                   command=self._do_activate).pack(fill=tk.X, ipady=2)
        
        # 状态标签
        self._activation_status_var = tk.StringVar()
        self._activation_status_label = tk.Label(
            container, textvariable=self._activation_status_var,
            font=("微软雅黑", 10), fg=_COLORS["text_secondary"], bg=_COLORS["bg"],
        )
        self._activation_status_label.pack(pady=(10, 0))

        # 获取激活码地址提示
        act_url_frame = tk.Frame(container, bg="#EFF6FF", padx=12, pady=8)
        act_url_frame.pack(fill=tk.X, padx=20, pady=(10, 0))
        tk.Label(act_url_frame, text="🔑 获取激活码：", font=("微软雅黑", 9),
                 fg=_COLORS["text"], bg="#EFF6FF").pack(side=tk.LEFT)
        act_url = "https://xy.zhinianboke.com/get-activation"
        act_url_lbl = tk.Label(act_url_frame, text=act_url,
                               font=("Consolas", 9, "underline"),
                               fg=_COLORS["primary"], bg="#EFF6FF", cursor="hand2")
        act_url_lbl.pack(side=tk.LEFT)
        act_url_lbl.bind("<Button-1>",
                         lambda e: __import__("webbrowser").open(act_url))

        renew_url_frame = tk.Frame(container, bg="#ECFDF5", padx=12, pady=8)
        renew_url_frame.pack(fill=tk.X, padx=20, pady=(8, 0))
        tk.Label(renew_url_frame, text="♻ 获取续期码：", font=("微软雅黑", 9),
                 fg=_COLORS["text"], bg="#ECFDF5").pack(side=tk.LEFT)
        renew_url = "https://xy.zhinianboke.com/renew-activation"
        renew_url_lbl = tk.Label(renew_url_frame, text=renew_url,
                                 font=("Consolas", 9, "underline"),
                                 fg=_COLORS["success"], bg="#ECFDF5", cursor="hand2")
        renew_url_lbl.pack(side=tk.LEFT)
        renew_url_lbl.bind("<Button-1>",
                           lambda e: __import__("webbrowser").open(renew_url))
    
    def _copy_machine_id(self):
        """复制机器码到剪贴板"""
        self.root.clipboard_clear()
        self.root.clipboard_append(self.machine_id)
        self._activation_status_var.set("机器码已复制到剪贴板")
        self._activation_status_label.configure(fg=_COLORS["success"])

    def _do_activate(self):
        """执行激活操作：验证激活码签名和有效期，保存后跳转配置页"""
        code = self._activation_var.get().strip()
        if not code:
            self._activation_status_var.set("请输入激活码或续期码")
            self._activation_status_label.configure(fg=_COLORS["error"])
            return

        if code.upper().startswith("R"):
            renew_result = renew_license(self.machine_id, code)
            if renew_result["success"]:
                self._activation_status_var.set(renew_result["message"])
                self._activation_status_label.configure(fg=_COLORS["success"])
                self.root.after(800, self._show_config_page)
            else:
                self._activation_status_var.set(renew_result["message"])
                self._activation_status_label.configure(fg=_COLORS["error"])
            return

        result = verify_activation_code(self.machine_id, code)
        if not result["valid"]:
            self._activation_status_var.set("激活码无效，请检查后重试")
            self._activation_status_label.configure(fg=_COLORS["error"])
            return

        if result["expired"]:
            expire_str = format_expire_time(result["expire_ts"])
            self._activation_status_var.set(f"激活码已过期（{expire_str}），可输入续期码继续进入系统")
            self._activation_status_label.configure(fg=_COLORS["error"])
            return

        if save_license(self.machine_id, code, result["expire_ts"]):
            expire_str = format_expire_time(result["expire_ts"])
            self._activation_status_var.set(f"激活成功！到期时间: {expire_str}")
            self._activation_status_label.configure(fg=_COLORS["success"])
            self.root.after(800, self._show_config_page)
        else:
            self._activation_status_var.set("激活信息保存失败，请检查磁盘权限")
            self._activation_status_label.configure(fg=_COLORS["error"])
    
    # ==================== 配置页面 ====================
    
    def _show_config_page(self):
        """显示MySQL/Redis配置页面"""
        self._clear_page()
        self._current_page = "config"
        
        container = tk.Frame(self.root, bg=_COLORS["bg"])
        container.pack(fill=tk.BOTH, expand=True)
        
        # 页面标题
        make_header(container, "连接配置", "请填写数据库和缓存服务的连接信息")
        
        # 提示信息
        tip_frame = tk.Frame(container, bg="#E0F2FE", padx=12, pady=8)
        tip_frame.pack(fill=tk.X, padx=20, pady=(0, 10))
        tk.Label(tip_frame, text="💡 MySQL 和 Redis 可以自己本地部署，也可以使用远程服务器的数据库",
                 font=("微软雅黑", 9), fg="#0369A1", bg="#E0F2FE", wraplength=400).pack(anchor=tk.W)
        
        # 加载已保存的配置
        saved_config = load_connection_config()
        
        # ---- MySQL 卡片 ----
        mysql_card = make_card(container)
        
        mysql_title_row = tk.Frame(mysql_card, bg=_COLORS["card_bg"])
        mysql_title_row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(mysql_title_row, text="MySQL 配置", font=("微软雅黑", 11, "bold"),
                 fg=_COLORS["primary"], bg=_COLORS["card_bg"]).pack(side=tk.LEFT)
        self._mysql_test_var = tk.StringVar()
        self._mysql_test_label = tk.Label(
            mysql_title_row, textvariable=self._mysql_test_var,
            font=("微软雅黑", 9), fg=_COLORS["text_secondary"], bg=_COLORS["card_bg"])
        self._mysql_test_label.pack(side=tk.RIGHT)
        ttk.Button(mysql_title_row, text="测试连接", style="Normal.TButton",
                   command=self._test_mysql).pack(side=tk.RIGHT, padx=(0, 8))
        
        self._mysql_vars = {}
        mysql_fields = [
            ("mysql_host", "主机地址", "localhost"),
            ("mysql_port", "端口", "3306"),
            ("mysql_user", "用户名", "root"),
            ("mysql_password", "密码", ""),
            ("mysql_database", "数据库名", "xianyu_auto_reply"),
        ]
        build_form_fields(mysql_card, mysql_fields, self._mysql_vars, saved_config)
        
        # ---- Redis 卡片 ----
        redis_card = make_card(container)
        
        redis_title_row = tk.Frame(redis_card, bg=_COLORS["card_bg"])
        redis_title_row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(redis_title_row, text="Redis 配置", font=("微软雅黑", 11, "bold"),
                 fg=_COLORS["primary"], bg=_COLORS["card_bg"]).pack(side=tk.LEFT)
        self._redis_test_var = tk.StringVar()
        self._redis_test_label = tk.Label(
            redis_title_row, textvariable=self._redis_test_var,
            font=("微软雅黑", 9), fg=_COLORS["text_secondary"], bg=_COLORS["card_bg"])
        self._redis_test_label.pack(side=tk.RIGHT)
        ttk.Button(redis_title_row, text="测试连接", style="Normal.TButton",
                   command=self._test_redis).pack(side=tk.RIGHT, padx=(0, 8))
        
        self._redis_vars = {}
        redis_fields = [
            ("redis_host", "主机地址", "localhost"),
            ("redis_port", "端口", "6379"),
            ("redis_password", "密码", ""),
            ("redis_db", "数据库编号", "0"),
        ]
        build_form_fields(redis_card, redis_fields, self._redis_vars, saved_config)
        
        # 启动按钮
        btn_area = tk.Frame(container, bg=_COLORS["bg"])
        btn_area.pack(fill=tk.X, padx=20, pady=(4, 0))
        ttk.Button(btn_area, text="保存配置并启动服务", style="Primary.TButton",
                   command=self._do_start_services).pack(fill=tk.X, ipady=2)
        
        # 状态标签
        self._config_status_var = tk.StringVar()
        self._config_status_label = tk.Label(
            container, textvariable=self._config_status_var,
            font=("微软雅黑", 10), fg=_COLORS["text_secondary"], bg=_COLORS["bg"],
        )
        self._config_status_label.pack(pady=(8, 0))
    
    def _get_config_dict(self) -> dict:
        """从界面获取配置字典"""
        config = {}
        for key, var in self._mysql_vars.items():
            config[key] = var.get().strip()
        for key, var in self._redis_vars.items():
            config[key] = var.get().strip()
        return config
    
    def _test_mysql(self):
        """测试MySQL连接"""
        self._mysql_test_var.set("正在连接...")
        self._mysql_test_label.configure(fg=_COLORS["text_secondary"])
        self.root.update()
        
        config = self._get_config_dict()
        try:
            port = int(config["mysql_port"])
        except ValueError:
            self._mysql_test_var.set("端口号必须为数字")
            self._mysql_test_label.configure(fg=_COLORS["error"])
            return
        
        result = check_mysql_connection(
            host=config["mysql_host"],
            port=port,
            user=config["mysql_user"],
            password=config["mysql_password"],
            database=config["mysql_database"],
        )
        self._mysql_test_var.set(result["message"])
        self._mysql_test_label.configure(
            fg=_COLORS["success"] if result["success"] else _COLORS["error"])
    
    def _test_redis(self):
        """测试Redis连接"""
        self._redis_test_var.set("正在连接...")
        self._redis_test_label.configure(fg=_COLORS["text_secondary"])
        self.root.update()
        
        config = self._get_config_dict()
        try:
            port = int(config["redis_port"])
            db = int(config["redis_db"])
        except ValueError:
            self._redis_test_var.set("端口号和数据库编号必须为数字")
            self._redis_test_label.configure(fg=_COLORS["error"])
            return
        
        result = check_redis_connection(
            host=config["redis_host"],
            port=port,
            password=config["redis_password"],
            db=db,
        )
        self._redis_test_var.set(result["message"])
        self._redis_test_label.configure(
            fg=_COLORS["success"] if result["success"] else _COLORS["error"])
    
    def _do_start_services(self):
        """保存配置并启动服务"""
        config = self._get_config_dict()
        
        # 先验证连接
        self._config_status_var.set("正在验证MySQL连接...")
        self._config_status_label.configure(fg=_COLORS["text_secondary"])
        self.root.update()
        
        try:
            mysql_port = int(config["mysql_port"])
        except ValueError:
            self._config_status_var.set("MySQL端口号必须为数字")
            self._config_status_label.configure(fg=_COLORS["error"])
            return
        
        mysql_result = check_mysql_connection(
            host=config["mysql_host"], port=mysql_port,
            user=config["mysql_user"], password=config["mysql_password"],
            database=config["mysql_database"],
        )
        if not mysql_result["success"]:
            self._config_status_var.set(f"MySQL: {mysql_result['message']}")
            self._config_status_label.configure(fg=_COLORS["error"])
            return
        
        self._config_status_var.set("正在验证Redis连接...")
        self.root.update()
        
        try:
            redis_port = int(config["redis_port"])
            redis_db = int(config["redis_db"])
        except ValueError:
            self._config_status_var.set("Redis端口号和数据库编号必须为数字")
            self._config_status_label.configure(fg=_COLORS["error"])
            return
        
        redis_result = check_redis_connection(
            host=config["redis_host"], port=redis_port,
            password=config["redis_password"], db=redis_db,
        )
        if not redis_result["success"]:
            self._config_status_var.set(f"Redis: {redis_result['message']}")
            self._config_status_label.configure(fg=_COLORS["error"])
            return
        
        # 保存配置
        self._config_status_var.set("正在保存配置...")
        self.root.update()
        
        if not save_connection_config(config):
            self._config_status_var.set("配置保存失败，请检查磁盘权限")
            self._config_status_label.configure(fg=_COLORS["error"])
            return
        
        # 检查浏览器是否已安装，未安装则先安装
        if not is_chromium_installed():
            self._show_browser_install_page(config)
            return

        # 启动服务
        self._launch_services(config)
    
    def _launch_services(self, config: dict):
        """保存配置并在子线程中启动所有服务"""
        self._config_status_var.set("正在启动服务，请稍候...")
        self._config_status_label.configure(fg=_COLORS["primary"])
        self.root.update()
        threading.Thread(target=self._start_services_thread, args=(config,), daemon=True).start()

    def _start_services_thread(self, config: dict):
        """
        在子线程中启动所有服务
        
        Args:
            config: 连接配置字典
        """
        results = self.service_manager.start_all(config)
        # 回到主线程更新界面
        self.root.after(0, lambda: self._show_running_page(results))

    # ==================== 浏览器安装页面 ====================

    def _show_browser_install_page(self, config: dict):
        """
        显示浏览器安装进度页面

        首次启动时如果 Chromium 未安装，展示安装进度，
        安装完成后自动继续启动服务。

        Args:
            config: 连接配置字典（安装完成后传递给服务启动）
        """
        self._clear_page()
        self._current_page = "browser_install"

        container = tk.Frame(self.root, bg=_COLORS["bg"])
        container.pack(fill=tk.BOTH, expand=True)

        make_header(container, "闲鱼自动回复系统", "正在检查内置浏览器环境")

        # 安装状态卡片
        card = make_card(container)
        tk.Label(card, text="浏览器环境准备", font=("微软雅黑", 12, "bold"),
                 fg=_COLORS["primary"], bg=_COLORS["card_bg"]).pack(anchor=tk.W)
        tk.Label(card, text="系统需要 Chromium 浏览器来完成滑块验证和商品搜索，安装包正常情况下已内置该浏览器",
                 font=("微软雅黑", 9),
                 fg=_COLORS["text_secondary"], bg=_COLORS["card_bg"]).pack(
            anchor=tk.W, pady=(2, 12))

        # 进度条
        self._browser_progress = ttk.Progressbar(
            card, mode="indeterminate", length=400)
        self._browser_progress.pack(fill=tk.X, pady=(0, 8))
        self._browser_progress.start(15)

        # 状态文字
        self._browser_status_var = tk.StringVar(value="正在检测内置浏览器环境...")
        self._browser_status_label = tk.Label(
            card, textvariable=self._browser_status_var,
            font=("微软雅黑", 10), fg=_COLORS["text"],
            bg=_COLORS["card_bg"], wraplength=500, justify=tk.LEFT)
        self._browser_status_label.pack(anchor=tk.W, pady=(0, 4))

        # 详细日志区域
        self._browser_log_var = tk.StringVar(value="")
        tk.Label(card, textvariable=self._browser_log_var,
                 font=("Consolas", 8), fg=_COLORS["text_secondary"],
                 bg=_COLORS["card_bg"], wraplength=500, justify=tk.LEFT).pack(
            anchor=tk.W)

        # 提示
        tip_frame = tk.Frame(container, bg=_COLORS["warning_bg"], padx=12, pady=8)
        tip_frame.pack(fill=tk.X, padx=20, pady=(12, 0))
        tk.Label(tip_frame,
                 text="提示：当前策略为浏览器离线随包，正常情况下无需联网下载；若检测到内置浏览器缺失，会自动尝试修复",
                 font=("微软雅黑", 9), fg="#92400e", bg=_COLORS["warning_bg"],
                 anchor=tk.W).pack(fill=tk.X)

        # 开始安装
        def _on_progress(msg: str):
            """进度回调（子线程中调用，需切到主线程更新UI）"""
            self.root.after(0, lambda m=msg: self._update_browser_progress(m))

        def _on_done(success: bool, msg: str):
            """完成回调（子线程中调用）"""
            self.root.after(0, lambda: self._on_browser_install_done(
                success, msg, config))

        check_and_install_chromium(
            progress_callback=_on_progress,
            done_callback=_on_done,
        )

    def _update_browser_progress(self, message: str):
        """更新浏览器安装进度文字（主线程）"""
        try:
            self._browser_status_var.set(message)
            # 保留最后3行日志
            current = self._browser_log_var.get()
            lines = current.split("\n") if current else []
            lines.append(message)
            self._browser_log_var.set("\n".join(lines[-3:]))
        except Exception:
            pass

    def _on_browser_install_done(self, success: bool, message: str, config: dict):
        """
        浏览器安装完成回调（主线程）

        成功则自动继续启动服务，失败则显示错误和重试按钮。

        Args:
            success: 是否安装成功
            message: 结果消息
            config: 连接配置字典
        """
        try:
            self._browser_progress.stop()
        except Exception:
            pass

        if success:
            self._browser_status_var.set("浏览器环境已就绪，正在启动服务...")
            self._browser_status_label.configure(fg=_COLORS["success"])
            # 1秒后跳回配置页启动服务
            self.root.after(1000, lambda: self._after_browser_install(config))
        else:
            self._browser_status_var.set(f"安装失败: {message}")
            self._browser_status_label.configure(fg=_COLORS["error"])
            
            # 显示警告提示
            warn_frame = tk.Frame(self.root, bg="#FEF2F2", padx=12, pady=8)
            warn_frame.pack(fill=tk.X, padx=20, pady=(12, 0))
            tk.Label(warn_frame,
                     text="⚠ 浏览器未正确安装，滑块验证和商品搜索功能将不可用。建议重试安装后再启动服务。",
                     font=("微软雅黑", 9), fg="#991B1B", bg="#FEF2F2",
                     wraplength=450, justify=tk.LEFT).pack(fill=tk.X)
            
            # 显示重试和返回按钮（不再提供跳过，阻止启动无浏览器的服务）
            btn_frame = tk.Frame(self.root, bg=_COLORS["bg"])
            btn_frame.pack(pady=(12, 0))
            tk.Button(btn_frame, text="重试安装", font=("微软雅黑", 10),
                     fg="#ffffff", bg=_COLORS["primary"],
                     activeforeground="#ffffff",
                     activebackground=_COLORS["primary_hover"],
                     bd=0, cursor="hand2", padx=16, pady=6,
                     command=lambda: self._show_browser_install_page(config)
                     ).pack(side=tk.LEFT, padx=(0, 12))
            tk.Button(btn_frame, text="返回配置", font=("微软雅黑", 10),
                     fg=_COLORS["text"], bg=_COLORS["card_bg"],
                     activeforeground=_COLORS["text"],
                     activebackground=_COLORS["border"],
                     bd=1, cursor="hand2", padx=16, pady=6,
                     command=lambda: self._show_config_page()
                     ).pack(side=tk.LEFT)

    def _after_browser_install(self, config: dict):
        """
        浏览器安装流程结束后，回到配置页面并启动服务

        Args:
            config: 连接配置字典
        """
        # 重新显示配置页面（恢复状态标签等控件）
        self._show_config_page()
        # 自动启动服务
        self.root.after(200, lambda: self._launch_services(config))
    
    # ==================== 运行状态页面（委托给gui_running模块） ====================
    
    def _show_running_page(self, start_results: dict):
        """显示服务运行状态页面（委托给gui_running模块）"""
        show_running_page(self, start_results)
    
    def _on_close(self):
        """
        窗口关闭事件处理
        
        无论当前在哪个页面，关闭时都会停止所有服务并杀掉端口进程
        """
        if self._current_page == "running":
            if not messagebox.askyesno("确认", "关闭窗口将停止所有服务，确定要退出吗？"):
                return
        self.service_manager.stop_all()
        self.root.destroy()
    
    def run(self):
        """启动GUI主循环"""
        self.root.mainloop()
