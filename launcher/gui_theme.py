"""
GUI主题样式和辅助组件模块

功能：
1. 定义蓝白主题色彩常量
2. 配置ttk样式（按钮、标签、输入框等）
3. 提供卡片容器、页面标题等可复用UI组件
"""
import tkinter as tk
import tkinter.ttk as ttk

# ==================== 主题色彩常量 ====================
COLORS = {
    "bg": "#f0f4f8",              # 页面背景
    "card_bg": "#ffffff",         # 卡片背景
    "primary": "#2563eb",         # 主色（蓝）
    "primary_hover": "#1d4ed8",
    "primary_text": "#ffffff",
    "success": "#16a34a",         # 成功（绿）
    "success_bg": "#dcfce7",
    "error": "#dc2626",           # 错误（红）
    "error_bg": "#fee2e2",
    "warning_bg": "#fef9c3",      # 警告（黄）
    "text": "#1e293b",            # 主文本
    "text_secondary": "#64748b",  # 副文本
    "border": "#e2e8f0",          # 边框
    "input_bg": "#f8fafc",        # 输入框背景
    "accent": "#3b82f6",          # 强调色
    "stop_btn": "#ef4444",        # 停止按钮
    "stop_hover": "#dc2626",
}


def setup_styles():
    """
    配置ttk全局样式主题
    
    使用clam主题基础，自定义蓝白配色的按钮、标签、输入框等样式
    """
    style = ttk.Style()
    style.theme_use("clam")
    
    # 全局背景
    style.configure(".", background=COLORS["bg"], font=("微软雅黑", 10))
    
    # 标题
    style.configure("Title.TLabel", font=("微软雅黑", 18, "bold"),
                     foreground=COLORS["text"], background=COLORS["bg"])
    style.configure("Subtitle.TLabel", font=("微软雅黑", 11),
                     foreground=COLORS["text_secondary"], background=COLORS["bg"])
    
    # 卡片内标题
    style.configure("CardTitle.TLabel", font=("微软雅黑", 11, "bold"),
                     foreground=COLORS["text"], background=COLORS["card_bg"])
    style.configure("CardText.TLabel", font=("微软雅黑", 10),
                     foreground=COLORS["text_secondary"], background=COLORS["card_bg"])
    
    # 状态标签
    style.configure("Success.TLabel", font=("微软雅黑", 10, "bold"),
                     foreground=COLORS["success"], background=COLORS["card_bg"])
    style.configure("Error.TLabel", font=("微软雅黑", 10),
                     foreground=COLORS["error"], background=COLORS["card_bg"])
    style.configure("Status.TLabel", font=("微软雅黑", 10),
                     foreground=COLORS["text_secondary"], background=COLORS["bg"])
    style.configure("StatusCard.TLabel", font=("微软雅黑", 10),
                     foreground=COLORS["text_secondary"], background=COLORS["card_bg"])
    
    # 通用帧
    style.configure("Card.TFrame", background=COLORS["card_bg"])
    style.configure("Bg.TFrame", background=COLORS["bg"])
    
    # LabelFrame（卡片区域）
    style.configure("Card.TLabelframe", background=COLORS["card_bg"],
                     borderwidth=1, relief="solid")
    style.configure("Card.TLabelframe.Label", font=("微软雅黑", 10, "bold"),
                     foreground=COLORS["primary"], background=COLORS["card_bg"])
    
    # 主要按钮（蓝色）
    style.configure("Primary.TButton", font=("微软雅黑", 11, "bold"),
                     foreground=COLORS["primary_text"], background=COLORS["primary"],
                     borderwidth=0, padding=(20, 8))
    style.map("Primary.TButton",
               background=[("active", COLORS["primary_hover"]),
                           ("pressed", COLORS["primary_hover"])])
    
    # 普通按钮（白色边框）
    style.configure("Normal.TButton", font=("微软雅黑", 10),
                     background=COLORS["card_bg"], foreground=COLORS["text"],
                     borderwidth=1, padding=(12, 6))
    style.map("Normal.TButton",
               background=[("active", COLORS["border"])])
    
    # 危险按钮（红色）
    style.configure("Danger.TButton", font=("微软雅黑", 10, "bold"),
                     foreground="#ffffff", background=COLORS["stop_btn"],
                     borderwidth=0, padding=(12, 6))
    style.map("Danger.TButton",
               background=[("active", COLORS["stop_hover"]),
                           ("pressed", COLORS["stop_hover"])])
    
    # 成功按钮（绿色）
    style.configure("Success.TButton", font=("微软雅黑", 10, "bold"),
                     foreground="#ffffff", background=COLORS["success"],
                     borderwidth=0, padding=(12, 6))
    style.map("Success.TButton",
               background=[("active", "#15803d"), ("pressed", "#15803d")])
    
    # 输入框
    style.configure("TEntry", fieldbackground=COLORS["input_bg"],
                     borderwidth=1, padding=5)
    style.map("TEntry", bordercolor=[("focus", COLORS["primary"])])


def make_card(parent, **pack_kwargs) -> tk.Frame:
    """
    创建一个白色卡片容器（带边框阴影效果）
    
    Args:
        parent: 父容器
        **pack_kwargs: 传递给outer.pack()的额外参数
    Returns:
        卡片内部Frame，可在其中添加子组件
    """
    outer = tk.Frame(parent, bg=COLORS["border"], padx=1, pady=1)
    outer.pack(fill=tk.X, padx=20, pady=(0, 12), **pack_kwargs)
    inner = tk.Frame(outer, bg=COLORS["card_bg"], padx=18, pady=14)
    inner.pack(fill=tk.BOTH, expand=True)
    return inner


def make_header(parent, title: str, subtitle: str = ""):
    """
    创建页面顶部标题区域（带蓝色左边线装饰）
    
    Args:
        parent: 父容器
        title: 主标题文字
        subtitle: 副标题文字（可选）
    """
    header = tk.Frame(parent, bg=COLORS["bg"])
    header.pack(fill=tk.X, padx=20, pady=(20, 16))
    
    # 蓝色装饰条 + 标题
    title_row = tk.Frame(header, bg=COLORS["bg"])
    title_row.pack(fill=tk.X)
    tk.Frame(title_row, bg=COLORS["primary"], width=4).pack(
        side=tk.LEFT, fill=tk.Y, padx=(0, 10))
    
    text_col = tk.Frame(title_row, bg=COLORS["bg"])
    text_col.pack(side=tk.LEFT, fill=tk.X)
    tk.Label(text_col, text=title, font=("微软雅黑", 18, "bold"),
             fg=COLORS["text"], bg=COLORS["bg"]).pack(anchor=tk.W)
    if subtitle:
        tk.Label(text_col, text=subtitle, font=("微软雅黑", 10),
                 fg=COLORS["text_secondary"], bg=COLORS["bg"]).pack(anchor=tk.W, pady=(2, 0))


def build_form_fields(parent, fields: list, var_dict: dict, saved_config: dict):
    """
    在卡片容器中构建表单字段行
    
    每个字段一行，左侧标签右侧输入框，密码字段自动隐藏输入
    
    Args:
        parent: 父容器（通常是卡片Frame）
        fields: 字段列表 [(key, label, default), ...]
        var_dict: 用于存放各字段StringVar的字典（会被修改）
        saved_config: 已保存的配置字典（可为None）
    """
    for key, label, default in fields:
        row = tk.Frame(parent, bg=COLORS["card_bg"])
        row.pack(fill=tk.X, pady=3)
        tk.Label(row, text=f"{label}", width=9, anchor=tk.E,
                 font=("微软雅黑", 10), fg=COLORS["text"],
                 bg=COLORS["card_bg"]).pack(side=tk.LEFT)
        var = tk.StringVar(value=saved_config.get(key, default) if saved_config else default)
        var_dict[key] = var
        entry = ttk.Entry(row, textvariable=var, font=("Consolas", 10))
        if "password" in key:
            entry.configure(show="*")
        entry.pack(side=tk.LEFT, padx=(8, 0), fill=tk.X, expand=True)
