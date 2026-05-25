"""
GUI仪表盘页面模块

功能：
1. 从远程服务器API获取已审核的公开广告数据（无需登录）
2. 左右两栏布局：左侧轮播图广告，右侧文字广告（一比一复刻前端Dashboard）
3. 轮播图：自动轮播、指示器圆点、底部渐变标题覆盖、点击跳转
4. 文字广告：标题+链接、可展开/折叠显示内容
"""
import gzip
import io
import ssl
import threading
import tkinter as tk
import webbrowser
from urllib import request as urllib_request
from urllib.error import URLError

from launcher.gui_theme import COLORS


# 远程服务器API地址（公开接口，无需登录）
_SERVER_URL = "https://xy.zhinianboke.com"

# 轮播间隔（毫秒）
_CAROUSEL_INTERVAL = 4000

# 轮播区域高度
_CAROUSEL_HEIGHT = 220

# 文字广告区域高度（与轮播高度一致）
_TEXT_ADS_HEIGHT = 220


def render_dashboard_page(app):
    """
    在右侧内容区渲染仪表盘页面（上下布局：轮播图在上，文字广告在下）

    Args:
        app: LauncherApp实例
    """
    content = app._content_frame

    # 初始化仪表盘状态
    app._carousel_index = 0
    app._carousel_timer_id = None
    app._carousel_images = []  # 保持引用防止GC
    app._carousel_loaded_images = {}
    app._carousel_data = []
    app._text_ad_expanded = {}  # {ad_id: bool} 展开状态

    # 滚动容器（内容可能超过窗口高度）
    scroll_canvas = tk.Canvas(content, bg=COLORS["card_bg"], highlightthickness=0)
    scroll_canvas.pack(fill=tk.BOTH, expand=True)

    inner = tk.Frame(scroll_canvas, bg=COLORS["card_bg"])
    canvas_window = scroll_canvas.create_window((0, 0), window=inner, anchor=tk.NW)

    def _on_inner_configure(e):
        scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all"))

    def _on_canvas_configure(e):
        scroll_canvas.itemconfig(canvas_window, width=e.width)

    inner.bind("<Configure>", _on_inner_configure)
    scroll_canvas.bind("<Configure>", _on_canvas_configure)

    # 鼠标滚轮
    def _on_mousewheel(e):
        try:
            if not scroll_canvas.winfo_exists():
                return
            scroll_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        except tk.TclError:
            return

    scroll_canvas.bind_all("<MouseWheel>", _on_mousewheel)

    def _on_canvas_destroy(e):
        try:
            if e.widget is scroll_canvas:
                scroll_canvas.unbind_all("<MouseWheel>")
        except tk.TclError:
            pass

    scroll_canvas.bind("<Destroy>", _on_canvas_destroy)

    # 标题区域
    header = tk.Frame(inner, bg=COLORS["card_bg"])
    header.pack(fill=tk.X, padx=20, pady=(16, 12))
    tk.Label(header, text="仪表盘", font=("微软雅黑", 14, "bold"),
             fg=COLORS["text"], bg=COLORS["card_bg"]).pack(anchor=tk.W)
    tk.Label(header, text="系统广告信息", font=("微软雅黑", 9),
             fg=COLORS["text_secondary"], bg=COLORS["card_bg"]).pack(anchor=tk.W, pady=(2, 0))

    app._dashboard_inner = inner
    app._dashboard_scroll = scroll_canvas

    # 加载提示
    loading_label = tk.Label(inner, text="正在加载广告数据...",
                             font=("微软雅黑", 10), fg=COLORS["text_secondary"],
                             bg=COLORS["card_bg"])
    loading_label.pack(pady=40)
    app._dashboard_loading = loading_label

    # 异步加载广告数据
    threading.Thread(target=_fetch_ads, args=(app,), daemon=True).start()


def _fetch_ads(app):
    """在子线程中请求远程服务器获取广告数据"""
    import json as json_mod
    try:
        url = f"{_SERVER_URL}/api/v1/advertisements/public"
        req = urllib_request.Request(url, method="GET")
        req.add_header("User-Agent", "XianyuLauncher-Dashboard/1.0")
        req.add_header("Accept-Encoding", "gzip, deflate")

        # 跳过SSL证书验证
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        with urllib_request.urlopen(req, timeout=10, context=ctx) as resp:
            raw = resp.read()

        # 处理gzip压缩
        if raw[:2] == b'\x1f\x8b':
            raw = gzip.decompress(raw)

        data = json_mod.loads(raw.decode("utf-8"))

        if data.get("success") and data.get("data"):
            carousel = data["data"].get("carousel", [])
            text_ads = data["data"].get("text", [])
            app.root.after(0, lambda: _render_ads(app, carousel, text_ads))
        else:
            app.root.after(0, lambda: _show_empty(app, "暂无广告数据"))
    except URLError as e:
        msg = str(getattr(e, 'reason', e))
        app.root.after(0, lambda: _show_empty(app, f"网络请求失败: {msg}"))
    except Exception as e:
        msg = str(e)
        app.root.after(0, lambda: _show_empty(app, f"加载失败: {msg}"))


def _show_empty(app, msg: str):
    """显示错误/空状态"""
    try:
        app._dashboard_loading.configure(text=msg, fg=COLORS["text_secondary"])
    except tk.TclError:
        pass


def _render_ads(app, carousel: list, text_ads: list):
    """在主线程中渲染广告内容（上下布局）"""
    try:
        app._dashboard_loading.destroy()
    except tk.TclError:
        return

    inner = app._dashboard_inner

    # ==================== 上方：轮播图广告 ====================
    top_card = _make_card(inner, "推荐广告")
    top_card.pack(fill=tk.X, padx=16, pady=(0, 10))

    if carousel:
        _render_carousel(app, top_card, carousel)
    else:
        _render_empty_placeholder(top_card, "暂无轮播广告", _CAROUSEL_HEIGHT)

    # ==================== 下方：文字广告 ====================
    bottom_card = _make_card(inner, "文字广告")
    bottom_card.pack(fill=tk.X, padx=16, pady=(0, 16))

    if text_ads:
        _render_text_ads(app, bottom_card, text_ads)
    else:
        _render_empty_placeholder(bottom_card, "广告位招租", 120)


def _make_card(parent, title: str) -> tk.Frame:
    """
    创建一个卡片容器（模拟前端 vben-card 样式）

    Args:
        parent: 父容器
        title: 卡片标题
    Returns:
        卡片内容区Frame
    """
    # 卡片外框
    card = tk.Frame(parent, bg="#ffffff", highlightbackground="#e2e8f0",
                    highlightthickness=1)

    # 卡片头部
    card_header = tk.Frame(card, bg="#ffffff", padx=12, pady=8)
    card_header.pack(fill=tk.X)
    tk.Label(card_header, text=title, font=("微软雅黑", 11, "bold"),
             fg=COLORS["text"], bg="#ffffff").pack(anchor=tk.W)

    # 分割线
    tk.Frame(card, bg="#e2e8f0", height=1).pack(fill=tk.X)

    # 卡片内容区
    card_body = tk.Frame(card, bg="#ffffff")
    card_body.pack(fill=tk.BOTH, expand=True)

    # 把 body 挂在 card 上方便后续使用
    card._body = card_body
    return card


def _render_empty_placeholder(card, text: str, height: int):
    """渲染空状态占位"""
    body = card._body
    placeholder = tk.Frame(body, bg="#ffffff", height=height)
    placeholder.pack(fill=tk.BOTH, expand=True)
    placeholder.pack_propagate(False)

    inner = tk.Frame(placeholder, bg="#ffffff",
                     highlightbackground="#cbd5e1", highlightthickness=1)
    inner.place(relx=0.5, rely=0.5, anchor=tk.CENTER,
                relwidth=0.8, relheight=0.6)
    tk.Label(inner, text=text, font=("微软雅黑", 10),
             fg="#94a3b8", bg="#ffffff").place(relx=0.5, rely=0.5, anchor=tk.CENTER)


# ==================== 轮播图广告 ====================

def _render_carousel(app, card, carousel: list):
    """渲染轮播图广告区域"""
    body = card._body
    app._carousel_data = carousel

    # 轮播显示区域（固定高度）
    display_frame = tk.Frame(body, bg="#f1f5f9", height=_CAROUSEL_HEIGHT)
    display_frame.pack(fill=tk.X)
    display_frame.pack_propagate(False)

    # 图片区域（用Canvas实现渐变覆盖效果）
    carousel_canvas = tk.Canvas(display_frame, bg="#f1f5f9", highlightthickness=0)
    carousel_canvas.pack(fill=tk.BOTH, expand=True)

    app._carousel_canvas_widget = carousel_canvas
    app._carousel_display_frame = display_frame

    # 指示器
    indicator_frame = tk.Frame(body, bg="#ffffff", pady=6)
    indicator_frame.pack(fill=tk.X)
    app._carousel_indicator_frame = indicator_frame

    # 显示第一条
    _update_carousel_display(app, 0)
    _start_carousel_timer(app)

    # 异步预加载所有轮播图片
    for i, ad in enumerate(carousel):
        image_url = ad.get("image_url")
        if image_url:
            threading.Thread(target=_load_carousel_image,
                             args=(app, i, image_url), daemon=True).start()


def _load_carousel_image(app, index: int, image_url: str):
    """异步加载轮播图片"""
    try:
        # 处理相对路径（服务器上的图片）
        if image_url.startswith("/"):
            image_url = f"{_SERVER_URL}{image_url}"

        # 创建不验证SSL证书的上下文（避免自签名证书导致加载失败）
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        req = urllib_request.Request(image_url)
        req.add_header("User-Agent", "XianyuLauncher-Dashboard/1.0")
        req.add_header("Accept-Encoding", "gzip, deflate")
        with urllib_request.urlopen(req, timeout=15, context=ctx) as resp:
            raw = resp.read()

        # 处理gzip压缩
        if raw[:2] == b'\x1f\x8b':
            raw = gzip.decompress(raw)

        from PIL import Image, ImageTk
        img = Image.open(io.BytesIO(raw))

        # 缩放：宽度撑满（右侧内容区约760px），高度自适应
        target_w = 720
        ratio = target_w / img.width
        target_h = min(int(img.height * ratio), _CAROUSEL_HEIGHT - 10)
        img = img.resize((target_w, target_h), Image.LANCZOS)

        photo = ImageTk.PhotoImage(img)

        # 保持引用防止GC
        app._carousel_images.append(photo)
        app._carousel_loaded_images[index] = photo

        # 回到主线程刷新显示
        app.root.after(0, lambda idx=index: _update_carousel_display(app, idx))
    except Exception as e:
        print(f"[仪表盘] 加载轮播图片失败 index={index}: {e}")


def _update_carousel_display(app, index: int):
    """更新轮播显示内容"""
    try:
        carousel = app._carousel_data
        if not carousel or index >= len(carousel):
            return

        ad = carousel[index]
        app._carousel_index = index

        canvas = app._carousel_canvas_widget
        canvas.delete("all")

        # 获取Canvas实际宽高
        canvas.update_idletasks()
        cw = canvas.winfo_width() or 380
        ch = canvas.winfo_height() or _CAROUSEL_HEIGHT

        photo = app._carousel_loaded_images.get(index)
        if photo:
            # 居中显示图片
            canvas.create_image(cw // 2, ch // 2, image=photo, anchor=tk.CENTER)
        else:
            # 无图片时显示渐变色背景+标题（模拟前端 from-blue-500 to-purple-600）
            canvas.create_rectangle(0, 0, cw, ch, fill="#6366f1", outline="")
            canvas.create_text(cw // 2, ch // 2 - 10,
                               text=ad.get("title", ""),
                               font=("微软雅黑", 14, "bold"),
                               fill="#ffffff")

        # 底部渐变遮罩区域（模拟 from-black/70 to-transparent）
        overlay_h = 50
        overlay_y = ch - overlay_h
        # 用半透明效果模拟：画一个深色矩形
        canvas.create_rectangle(0, overlay_y, cw, ch, fill="#1e293b",
                                outline="", stipple="gray50")

        # 底部标题文字
        title = ad.get("title", "")
        canvas.create_text(10, ch - overlay_h + 12, text=title,
                           font=("微软雅黑", 10, "bold"), fill="#ffffff",
                           anchor=tk.NW, width=cw - 20)

        # 底部内容文字（如果有）
        content = ad.get("content", "")
        if content:
            # 截断显示
            short = content[:60] + ("..." if len(content) > 60 else "")
            canvas.create_text(10, ch - overlay_h + 32, text=short,
                               font=("微软雅黑", 8), fill="#d1d5db",
                               anchor=tk.NW, width=cw - 20)

        # 点击跳转
        link = ad.get("link", "")
        if link:
            canvas.configure(cursor="hand2")
            canvas.bind("<Button-1>", lambda e, u=link: webbrowser.open(u))
        else:
            canvas.configure(cursor="")
            canvas.unbind("<Button-1>")

        # 更新指示器
        _update_indicators(app)
    except tk.TclError:
        pass


def _update_indicators(app):
    """更新轮播指示器圆点"""
    try:
        frame = app._carousel_indicator_frame
        for w in frame.winfo_children():
            w.destroy()

        count = len(app._carousel_data)
        if count <= 1:
            return

        dot_container = tk.Frame(frame, bg="#ffffff")
        dot_container.pack(anchor=tk.CENTER)

        for i in range(count):
            is_active = (i == app._carousel_index)
            color = "#ffffff" if is_active else "#94a3b8"
            border = COLORS["primary"] if is_active else "#cbd5e1"
            dot = tk.Canvas(dot_container, width=12, height=12,
                            bg="#ffffff", highlightthickness=0)
            dot.pack(side=tk.LEFT, padx=3)
            dot.create_oval(2, 2, 10, 10, fill=color, outline=border, width=2)
            dot.bind("<Button-1>", lambda e, idx=i: _go_to_carousel(app, idx))
            dot.configure(cursor="hand2")
    except tk.TclError:
        pass


def _go_to_carousel(app, index: int):
    """点击指示器跳转到指定轮播"""
    _update_carousel_display(app, index)
    _start_carousel_timer(app)


def _start_carousel_timer(app):
    """启动/重启轮播定时器"""
    if app._carousel_timer_id:
        try:
            app.root.after_cancel(app._carousel_timer_id)
        except Exception:
            pass
        app._carousel_timer_id = None

    count = len(app._carousel_data)
    if count <= 1:
        return

    def _next():
        try:
            next_idx = (app._carousel_index + 1) % count
            _update_carousel_display(app, next_idx)
            app._carousel_timer_id = app.root.after(_CAROUSEL_INTERVAL, _next)
        except tk.TclError:
            pass

    app._carousel_timer_id = app.root.after(_CAROUSEL_INTERVAL, _next)


# ==================== 文字广告 ====================

def _render_text_ads(app, card, text_ads: list):
    """渲染文字广告区域（直接列表，外层已有滚动容器）"""
    body = card._body

    # 文字广告列表容器（内边距）
    list_frame = tk.Frame(body, bg="#ffffff", padx=8, pady=6)
    list_frame.pack(fill=tk.X)

    # 渲染每条文字广告
    for ad in text_ads:
        _render_text_ad_item(app, list_frame, ad)


def _render_text_ad_item(app, parent, ad: dict):
    """
    渲染单条文字广告（模拟前端展开/折叠效果）

    Args:
        app: LauncherApp实例
        parent: 父容器
        ad: 广告数据字典
    """
    ad_id = ad.get("id", id(ad))
    title = ad.get("title", "无标题")
    content = ad.get("content", "")
    link = ad.get("link", "")

    # 卡片外框
    item_frame = tk.Frame(parent, bg="#ffffff", padx=4, pady=3)
    item_frame.pack(fill=tk.X, pady=(0, 4))

    card = tk.Frame(item_frame, bg="#f8fafc", highlightbackground="#e2e8f0",
                    highlightthickness=1)
    card.pack(fill=tk.X)

    # 标题行（标题+链接图标+展开按钮）
    header = tk.Frame(card, bg="#f8fafc", padx=10, pady=8)
    header.pack(fill=tk.X)

    # 展开/折叠按钮（右侧）
    toggle_text = tk.StringVar(value="▼")
    toggle_btn = tk.Label(header, textvariable=toggle_text, font=("微软雅黑", 8),
                          fg="#64748b", bg="#f8fafc", cursor="hand2", padx=4)
    toggle_btn.pack(side=tk.RIGHT)

    # 标题+链接
    title_text = f"{title}  ↗" if link else title
    title_label = tk.Label(header, text=title_text, font=("微软雅黑", 10, "bold"),
                           fg=COLORS["primary"], bg="#f8fafc", anchor=tk.W,
                           cursor="hand2" if link else "")
    title_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

    if link:
        title_label.bind("<Button-1>", lambda e, u=link: webbrowser.open(u))

    # 内容区（默认隐藏）
    content_frame = tk.Frame(card, bg="#ffffff")

    if content:
        # 分割线
        sep = tk.Frame(content_frame, bg="#e2e8f0", height=1)
        sep.pack(fill=tk.X)

        content_label = tk.Label(content_frame, text=content,
                                 font=("微软雅黑", 9),
                                 fg=COLORS["text_secondary"], bg="#ffffff",
                                 anchor=tk.NW, wraplength=300, justify=tk.LEFT,
                                 padx=10, pady=8)
        content_label.pack(fill=tk.X)

    # 展开/折叠逻辑
    app._text_ad_expanded[ad_id] = False

    def _toggle(e=None):
        expanded = app._text_ad_expanded.get(ad_id, False)
        if expanded:
            content_frame.pack_forget()
            toggle_text.set("▼")
            app._text_ad_expanded[ad_id] = False
        else:
            if content:
                content_frame.pack(fill=tk.X)
                toggle_text.set("▲")
                app._text_ad_expanded[ad_id] = True

    toggle_btn.bind("<Button-1>", _toggle)
    # 点击标题也可以展开（如果没有链接）
    if not link:
        title_label.bind("<Button-1>", _toggle)
