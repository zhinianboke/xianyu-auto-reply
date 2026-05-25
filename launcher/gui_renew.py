"""
GUI激活码续期页面模块

功能：
1. 作为左侧导航的"激活码续期"菜单对应内容页
2. 显示当前激活状态和到期时间
3. 输入续期码后叠加时长到原到期时间
"""
import tkinter as tk
import webbrowser
import tkinter.messagebox as messagebox
import tkinter.ttk as ttk

from launcher.gui_theme import COLORS
from launcher.activation import (
    load_and_verify_license,
    format_expire_time,
    get_remaining_text,
    renew_license,
    revoke_license,
)


def render_renew_page(app):
    """
    在右侧内容区渲染"激活码续期"页面

    显示当前到期信息和续期码输入框。
    Args:
        app: LauncherApp实例
    """
    content = app._content_frame

    # 滚动容器
    canvas = tk.Canvas(content, bg=COLORS["card_bg"], highlightthickness=0)
    canvas.pack(fill=tk.BOTH, expand=True)
    inner = tk.Frame(canvas, bg=COLORS["card_bg"])
    canvas.create_window((0, 0), window=inner, anchor=tk.NW)
    inner.bind("<Configure>",
               lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

    # 标题
    tk.Label(inner, text="激活码续期", font=("微软雅黑", 14, "bold"),
             fg=COLORS["text"], bg=COLORS["card_bg"]).pack(
        anchor=tk.W, padx=20, pady=(16, 4))
    tk.Label(inner, text="输入续期码可延长使用时间，时长将叠加到当前到期时间",
             font=("微软雅黑", 9),
             fg=COLORS["text_secondary"], bg=COLORS["card_bg"]).pack(
        anchor=tk.W, padx=20, pady=(0, 8))

    # 分割线
    tk.Frame(inner, height=1, bg=COLORS["border"]).pack(
        fill=tk.X, padx=20, pady=8)

    # 当前激活状态卡片
    status_frame = tk.Frame(inner, bg=COLORS["input_bg"],
                            highlightbackground=COLORS["border"],
                            highlightthickness=1)
    status_frame.pack(fill=tk.X, padx=20, pady=(0, 12))

    license_result = load_and_verify_license(app.machine_id)
    expire_ts = license_result.get("expire_ts", 0)

    # 状态标签
    if license_result.get("valid"):
        status_text = "✓ 已激活"
        status_color = COLORS["success"]
    elif license_result.get("expired"):
        status_text = "✗ 已过期"
        status_color = COLORS["error"]
    else:
        status_text = "✗ 未激活"
        status_color = COLORS["error"]

    tk.Label(status_frame, text=status_text, font=("微软雅黑", 11, "bold"),
             fg=status_color, bg=COLORS["input_bg"]).pack(
        anchor=tk.W, padx=16, pady=(12, 2))

    # 显示当前机器码（支持选中复制）
    mid_frame = tk.Frame(status_frame, bg=COLORS["input_bg"])
    mid_frame.pack(anchor=tk.W, padx=16, pady=(2, 0))
    tk.Label(mid_frame, text="机器码:", font=("微软雅黑", 9),
             fg=COLORS["text"], bg=COLORS["input_bg"]).pack(side=tk.LEFT)
    mid_entry = tk.Entry(mid_frame, font=("Consolas", 9), width=34,
                         fg=COLORS["primary"], bg=COLORS["input_bg"],
                         bd=0, highlightthickness=0, readonlybackground=COLORS["input_bg"])
    mid_entry.insert(0, app.machine_id)
    mid_entry.configure(state="readonly")
    mid_entry.pack(side=tk.LEFT, padx=(4, 0))

    def _copy_machine_id():
        """复制机器码到剪贴板"""
        app.root.clipboard_clear()
        app.root.clipboard_append(app.machine_id)
        copy_btn.configure(text="✓ 已复制", fg=COLORS["success"])
        app.root.after(1500, lambda: copy_btn.configure(
            text="复制", fg=COLORS["primary"]))

    copy_btn = tk.Button(mid_frame, text="复制", font=("微软雅黑", 8),
                         fg=COLORS["primary"], bg=COLORS["card_bg"],
                         activeforeground=COLORS["primary"],
                         activebackground=COLORS["border"],
                         bd=0, cursor="hand2", padx=6,
                         command=_copy_machine_id)
    copy_btn.pack(side=tk.LEFT, padx=(6, 0))

    if expire_ts > 0:
        expire_str = format_expire_time(expire_ts)
        remaining = get_remaining_text(expire_ts)
        tk.Label(status_frame, text=f"到期时间: {expire_str}",
                 font=("微软雅黑", 9),
                 fg=COLORS["text"], bg=COLORS["input_bg"]).pack(
            anchor=tk.W, padx=16)
        tk.Label(status_frame, text=remaining,
                 font=("微软雅黑", 9),
                 fg=COLORS["text_secondary"], bg=COLORS["input_bg"]).pack(
            anchor=tk.W, padx=16, pady=(0, 12))
    else:
        tk.Label(status_frame, text="暂无激活信息",
                 font=("微软雅黑", 9),
                 fg=COLORS["text_secondary"], bg=COLORS["input_bg"]).pack(
            anchor=tk.W, padx=16, pady=(0, 12))

    # 续期码输入区域
    tk.Label(inner, text="请输入续期码:", font=("微软雅黑", 10),
             fg=COLORS["text"], bg=COLORS["card_bg"]).pack(
        anchor=tk.W, padx=20, pady=(4, 4))

    code_var = tk.StringVar()
    code_entry = ttk.Entry(inner, textvariable=code_var, width=50,
                           font=("Consolas", 11))
    code_entry.pack(anchor=tk.W, padx=20, pady=(0, 8))

    # 结果提示标签
    result_label = tk.Label(inner, text="", font=("微软雅黑", 10),
                            bg=COLORS["card_bg"])
    result_label.pack(anchor=tk.W, padx=20, pady=(0, 8))

    # 续期按钮
    def _do_renew():
        """执行续期操作"""
        code = code_var.get().strip()
        if not code:
            result_label.configure(text="请输入续期码", fg=COLORS["error"])
            return

        result = renew_license(app.machine_id, code)
        if result["success"]:
            result_label.configure(text=result["message"],
                                   fg=COLORS["success"])
            # 刷新整个页面以更新状态信息
            app.root.after(1000, lambda: _refresh_page(app))
        else:
            result_label.configure(text=result["message"],
                                   fg=COLORS["error"])

    btn_frame = tk.Frame(inner, bg=COLORS["card_bg"])
    btn_frame.pack(anchor=tk.W, padx=20)

    tk.Button(btn_frame, text="确认续期", font=("微软雅黑", 9),
             fg="#ffffff", bg=COLORS["primary"],
             activeforeground="#ffffff", activebackground=COLORS["primary_hover"],
             bd=0, cursor="hand2", padx=14, pady=6,
             command=_do_renew).pack(side=tk.LEFT, padx=(0, 12))

    def _open_renew_page():
        """在浏览器中打开获取续期码页面"""
        webbrowser.open("https://xy.zhinianboke.com/renew-activation")

    tk.Button(btn_frame, text="获取续期码", font=("微软雅黑", 9),
             fg="#ffffff", bg=COLORS["success"],
             activeforeground="#ffffff", activebackground="#15803d",
             bd=0, cursor="hand2", padx=14, pady=6,
             command=_open_renew_page).pack(side=tk.LEFT, padx=(0, 12))

    def _do_revoke():
        """注销激活：二次确认后删除激活状态"""
        confirm = messagebox.askyesno(
            "注销激活",
            "确定要注销当前激活吗？\n\n"
            "注销后激活码将被清除，需要重新输入激活码才能继续使用。")
        if not confirm:
            return
        # 先停止所有服务
        try:
            app.service_manager.stop_all()
        except Exception:
            pass
        result = revoke_license()
        if result["success"]:
            result_label.configure(text=result["message"],
                                   fg=COLORS["success"])
            # 1.5秒后跳转到激活码输入界面
            app.root.after(1500, lambda: app._show_activation_page(
                "激活已注销，请重新输入激活码"))
        else:
            result_label.configure(text=result["message"],
                                   fg=COLORS["error"])

    tk.Button(btn_frame, text="注销激活", font=("微软雅黑", 9),
             fg="#ffffff", bg=COLORS["stop_btn"],
             activeforeground="#ffffff", activebackground=COLORS["stop_hover"],
             bd=0, cursor="hand2", padx=14, pady=6,
             command=_do_revoke).pack(side=tk.LEFT)


def _refresh_page(app):
    """刷新续期页面（重新渲染）"""
    try:
        for w in app._content_frame.winfo_children():
            w.destroy()
        render_renew_page(app)
    except Exception:
        pass
