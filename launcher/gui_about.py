"""
GUI关于页面模块

功能：
1. 作为左侧导航的"关于"菜单对应内容页
2. 显示系统版本信息
3. 从远程服务器加载并显示5个二维码（微信群/QQ群/公众号/Telegram/赞赏码）
4. 二维码图片异步加载，带加载状态提示
"""
import gzip
import io
import tkinter as tk
import threading
import urllib.request

from launcher.gui_theme import COLORS
from launcher.version import CURRENT_VERSION

# 远程二维码图片URL前缀
_QRCODE_URL_PREFIX = "https://xy.zhinianboke.com/static/qrcode/"

# 二维码配置：(文件名, 显示名称)
_QRCODE_ITEMS = [
    ("wechat-group.jpg", "微信群"),
    ("qq-group.jpg", "QQ群"),
    ("wechat-official-group.jpg", "公众号"),
    ("telegram-group.png", "Telegram"),
    ("reward-group.png", "赞赏码"),
]


def render_about_page(app):
    """
    在右侧内容区渲染"关于"页面

    显示版本号和5个二维码图片（异步加载）。
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
    tk.Label(inner, text="关于", font=("微软雅黑", 14, "bold"),
             fg=COLORS["text"], bg=COLORS["card_bg"]).pack(
        anchor=tk.W, padx=20, pady=(16, 4))

    # 系统名称和版本
    tk.Label(inner, text="闲鱼自动回复管理系统",
             font=("微软雅黑", 12),
             fg=COLORS["text"], bg=COLORS["card_bg"]).pack(
        anchor=tk.W, padx=20)
    tk.Label(inner, text=f"当前版本: v{CURRENT_VERSION}",
             font=("微软雅黑", 10),
             fg=COLORS["text_secondary"], bg=COLORS["card_bg"]).pack(
        anchor=tk.W, padx=20, pady=(0, 8))

    # 分割线
    tk.Frame(inner, height=1, bg=COLORS["border"]).pack(
        fill=tk.X, padx=20, pady=8)

    # 二维码区域标题
    tk.Label(inner, text="扫码关注 / 加群交流 / 赞赏支持",
             font=("微软雅黑", 10),
             fg=COLORS["text_secondary"], bg=COLORS["card_bg"]).pack(
        anchor=tk.W, padx=20)

    # 二维码网格
    qr_frame = tk.Frame(inner, bg=COLORS["card_bg"])
    qr_frame.pack(fill=tk.X, padx=20, pady=(8, 16))
    for col_idx in range(5):
        qr_frame.columnconfigure(col_idx, weight=1)

    # 用于保存PhotoImage引用和原始图片数据，防止GC回收
    if not hasattr(app, "_about_images"):
        app._about_images = {}
    if not hasattr(app, "_about_raw_data"):
        app._about_raw_data = {}

    for col_idx, (filename, label_text) in enumerate(_QRCODE_ITEMS):
        img_url = f"{_QRCODE_URL_PREFIX}{filename}"
        _create_qrcode_cell(app, qr_frame, col_idx, img_url, label_text)


def _create_qrcode_cell(app, parent, col, img_url, label_text):
    """
    创建单个二维码单元格

    Args:
        app: LauncherApp实例（用于保存图片引用）
        parent: 父Frame
        col: 列索引
        img_url: 二维码图片完整URL
        label_text: 显示名称
    """
    cell = tk.Frame(parent, bg=COLORS["card_bg"])
    cell.grid(row=0, column=col, padx=6, pady=4, sticky="nsew")

    # 名称标签
    tk.Label(cell, text=label_text, font=("微软雅黑", 9, "bold"),
             fg=COLORS["text"], bg=COLORS["card_bg"]).pack(pady=(0, 4))

    # 图片容器（固定大小，带边框）
    img_frame = tk.Frame(cell, width=120, height=120,
                         bg=COLORS["input_bg"],
                         highlightbackground=COLORS["border"],
                         highlightthickness=1)
    img_frame.pack()
    img_frame.pack_propagate(False)

    # 加载提示
    loading_label = tk.Label(img_frame, text="加载中...",
                             font=("微软雅黑", 8),
                             fg=COLORS["text_secondary"],
                             bg=COLORS["input_bg"])
    loading_label.pack(expand=True)

    # 异步下载图片
    threading.Thread(
        target=_load_qrcode_image,
        args=(app, img_frame, loading_label, img_url, label_text),
        daemon=True
    ).start()


def _load_qrcode_image(app, img_frame, loading_label, img_url, key):
    """
    异步从远程URL下载二维码图片并在主线程中显示

    Args:
        app: LauncherApp实例
        img_frame: 图片容器Frame
        loading_label: 加载提示Label
        img_url: 图片完整URL
        key: 标识key（用于保存引用）
    """
    try:
        req = urllib.request.Request(img_url)
        req.add_header("User-Agent", "XianyuAutoReply-GUI")
        req.add_header("Accept-Encoding", "gzip, deflate")
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw_data = resp.read()
            # 服务器可能返回gzip压缩数据，需要解压
            if raw_data[:2] == b'\x1f\x8b':
                img_data = gzip.decompress(raw_data)
            else:
                img_data = raw_data
        app.root.after(0, lambda: _display_image(
            app, img_frame, loading_label, img_data, key))
    except Exception:
        _show_no_image(app, img_frame, loading_label)


def _display_image(app, img_frame, loading_label, img_data, key):
    """
    在主线程中将图片数据显示到界面上

    优先使用Pillow解码并缩放，无Pillow则使用tkinter原生PhotoImage。
    Args:
        app: LauncherApp实例
        img_frame: 图片容器Frame
        loading_label: 加载提示Label
        img_data: 图片二进制数据
        key: 标识key（用于保存引用防GC回收）
    """
    try:
        from PIL import Image, ImageTk
        img = Image.open(io.BytesIO(img_data))
        img = img.resize((116, 116), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
    except ImportError:
        try:
            photo = tk.PhotoImage(data=img_data)
            w = photo.width()
            if w > 116:
                factor = max(w // 116, 1)
                photo = photo.subsample(factor)
        except Exception:
            _show_no_image(app, img_frame, loading_label)
            return
    except Exception:
        _show_no_image(app, img_frame, loading_label)
        return

    # 保存引用防止GC
    app._about_images[key] = photo
    # 保存原始数据用于点击放大
    app._about_raw_data[key] = img_data

    # 移除加载提示，显示图片（检查widget是否仍然存在）
    try:
        loading_label.destroy()
    except tk.TclError:
        return
    try:
        img_label = tk.Label(img_frame, image=photo, bg=COLORS["input_bg"],
                             cursor="hand2")
        img_label.pack(expand=True)
        # 点击放大预览
        img_label.bind("<Button-1>",
                       lambda e, k=key: _show_preview_dialog(app, k))
    except tk.TclError:
        pass


def _show_preview_dialog(app, key):
    """
    点击缩略图后弹出大图预览弹窗

    使用Pillow将原始图片按窗口大小等比缩放后显示。
    Args:
        app: LauncherApp实例
        key: 图片标识key
    """
    raw_data = app._about_raw_data.get(key)
    if not raw_data:
        return

    try:
        from PIL import Image, ImageTk
        img = Image.open(io.BytesIO(raw_data))
    except Exception:
        return

    # 计算预览尺寸：最大400x500，等比缩放
    max_w, max_h = 400, 500
    orig_w, orig_h = img.size
    ratio = min(max_w / orig_w, max_h / orig_h, 1.0)
    new_w = int(orig_w * ratio)
    new_h = int(orig_h * ratio)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    dlg = tk.Toplevel(app.root)
    dlg.title(key)
    dlg.resizable(False, False)
    dlg.transient(app.root)
    dlg.grab_set()
    dlg.configure(bg=COLORS["card_bg"])

    # 居中显示
    pad = 20
    win_w = new_w + pad * 2
    win_h = new_h + pad * 2 + 40
    sx = app.root.winfo_x() + (app.root.winfo_width() - win_w) // 2
    sy = app.root.winfo_y() + (app.root.winfo_height() - win_h) // 2
    dlg.geometry(f"{win_w}x{win_h}+{sx}+{sy}")

    photo = ImageTk.PhotoImage(img)
    # 保存引用防GC
    dlg._preview_photo = photo

    tk.Label(dlg, image=photo, bg=COLORS["card_bg"]).pack(
        padx=pad, pady=(pad, 8))
    tk.Button(dlg, text="关闭", command=dlg.destroy,
              font=("微软雅黑", 9), width=8).pack(pady=(0, pad))


def _show_no_image(app, img_frame, loading_label):
    """
    显示"未配置"占位提示

    Args:
        app: LauncherApp实例
        img_frame: 图片容器Frame
        loading_label: 加载提示Label
    """
    def _update():
        try:
            loading_label.configure(text="未配置")
        except tk.TclError:
            pass
    app.root.after(0, _update)
