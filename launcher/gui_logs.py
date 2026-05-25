"""
GUI日志查看器模块

功能：
1. 从子服务的stdout日志文件中读取内容并显示
2. 支持自动滚动到底部
3. 支持清空和刷新日志
4. 定时自动刷新日志内容（每2秒）
"""
import tkinter as tk
import tkinter.ttk as ttk
from pathlib import Path

from launcher.gui_theme import COLORS

# 日志服务配置：(服务key, 显示名称, 服务目录名)
LOG_SERVICES = [
    ("backend-web", "Backend 日志", "backend-web"),
    ("websocket", "WebSocket 日志", "websocket"),
    ("scheduler", "定时任务日志", "scheduler"),
]


def show_log_page(app, service_key: str):
    """
    在右侧内容区渲染指定服务的日志查看页面

    Args:
        app: LauncherApp实例
        service_key: 服务标识，如 "backend-web"
    """
    # 清空右侧内容区
    _clear_content(app)
    app._active_sub_page = f"log_{service_key}"

    # 找到显示名称
    display_name = service_key
    for key, name, _ in LOG_SERVICES:
        if key == service_key:
            display_name = name
            break

    content = app._content_frame

    # 标题行
    title_row = tk.Frame(content, bg=COLORS["card_bg"])
    title_row.pack(fill=tk.X, padx=16, pady=(14, 8))
    tk.Label(title_row, text=display_name, font=("微软雅黑", 13, "bold"),
             fg=COLORS["text"], bg=COLORS["card_bg"]).pack(side=tk.LEFT)

    # 操作按钮
    btn_row = tk.Frame(title_row, bg=COLORS["card_bg"])
    btn_row.pack(side=tk.RIGHT)
    ttk.Button(btn_row, text="刷新", style="Normal.TButton",
               command=lambda: _load_log(app, service_key)).pack(side=tk.LEFT, padx=(0, 4))
    ttk.Button(btn_row, text="清空日志", style="Normal.TButton",
               command=lambda: _clear_log_file(app, service_key)).pack(side=tk.LEFT)

    # 日志文本区域
    log_frame = tk.Frame(content, bg=COLORS["border"], padx=1, pady=1)
    log_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 14))

    text_widget = tk.Text(
        log_frame, wrap=tk.WORD, font=("Consolas", 9),
        bg="#1e1e2e", fg="#cdd6f4", insertbackground="#cdd6f4",
        selectbackground=COLORS["primary"], selectforeground="#ffffff",
        relief=tk.FLAT, padx=10, pady=8, state=tk.DISABLED,
        highlightthickness=0, borderwidth=0,
    )

    scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=text_widget.yview)
    text_widget.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    # 保存引用供刷新使用
    app._log_text_widget = text_widget
    app._log_service_key = service_key

    # 加载日志内容
    _load_log(app, service_key)

    # 启动定时刷新
    _auto_refresh_log(app, service_key)


def _get_log_path(app, service_key: str) -> Path:
    """
    获取指定服务的日志文件路径

    Args:
        app: LauncherApp实例
        service_key: 服务标识
    Returns:
        日志文件Path对象
    """
    service_dir = service_key
    for key, _, sdir in LOG_SERVICES:
        if key == service_key:
            service_dir = sdir
            break
    return app.project_root / service_dir / "logs" / f"{service_key}.stdout.log"


def _load_log(app, service_key: str):
    """
    从日志文件读取内容并显示到文本控件

    Args:
        app: LauncherApp实例
        service_key: 服务标识
    """
    if not hasattr(app, "_log_text_widget") or app._log_text_widget is None:
        return

    text_widget = app._log_text_widget
    log_path = _get_log_path(app, service_key)

    try:
        if log_path.exists():
            # 只读取最后50KB，避免大文件卡顿
            file_size = log_path.stat().st_size
            with open(str(log_path), "r", encoding="utf-8", errors="replace") as f:
                if file_size > 50 * 1024:
                    f.seek(file_size - 50 * 1024)
                    f.readline()  # 跳过不完整行
                    content = f"... (日志过大，只显示最后50KB) ...\n\n" + f.read()
                else:
                    content = f.read()
        else:
            content = "暂无日志，服务可能尚未启动或未产生输出。"
    except Exception as e:
        content = f"读取日志失败: {e}"

    # 更新文本控件
    text_widget.configure(state=tk.NORMAL)
    text_widget.delete("1.0", tk.END)
    text_widget.insert(tk.END, content)
    text_widget.configure(state=tk.DISABLED)

    # 自动滚动到底部
    text_widget.see(tk.END)


def _clear_log_file(app, service_key: str):
    """
    清空指定服务的日志文件内容

    Args:
        app: LauncherApp实例
        service_key: 服务标识
    """
    log_path = _get_log_path(app, service_key)
    try:
        if log_path.exists():
            with open(str(log_path), "w", encoding="utf-8") as f:
                f.write("")
    except Exception:
        pass
    _load_log(app, service_key)


def _auto_refresh_log(app, service_key: str):
    """
    每2秒自动刷新日志内容

    Args:
        app: LauncherApp实例
        service_key: 当前查看的服务标识
    """
    # 只在当前页面匹配时刷新
    if (app._current_page == "running"
            and hasattr(app, "_active_sub_page")
            and app._active_sub_page == f"log_{service_key}"):
        _load_log(app, service_key)
        app.root.after(2000, lambda: _auto_refresh_log(app, service_key))


def _clear_content(app):
    """清空右侧内容区"""
    if hasattr(app, "_content_frame") and app._content_frame:
        for w in app._content_frame.winfo_children():
            w.destroy()
