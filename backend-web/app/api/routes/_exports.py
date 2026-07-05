"""
Backend-Web API路由注册

所有前端API接口的路由定义与挂载，
由 __init__.py 通过 from ._exports import * 重新导出。
"""
from __future__ import annotations

from fastapi import APIRouter

# 导入所有路由模块
from . import (
    activation,
    admin,
    advertisements,
    ai,
    announcements,
    auto_reply_logs,
    auth,
    auto_rate,
    blacklist,
    captcha,
    cards,
    card_dock,
    data_analysis,
    distribution,
    chat_new,
    chat_new_ws,
    chat_new_image,
    chat_quick_phrase,
    chat_customer_order,
    payment,
    popup_announcements,
    confirm_receipt_messages,
    api_cookie_renew_logs,
    cookie_refresh,
    cookies,
    cookies_refresh_logs,
    default_replies,
    face_verification,
    feedback,
    geetest,
    goofish_compass,
    goofish_crawler,
    health,
    items,
    keywords,
    message,
    message_filters,
    notifications,
    orders,
    password_login,
    product_publish,
    publish_addresses,
    personal_addresses,
    listing_monitor_category,
    listing_monitor,
    collect_fallback_account,
    order_fallback_account,
    external_cookie,
    proxy,
    refund_cancel,
    qr_login,
    qrcode,
    risk_control_logs,
    account_login_logs,
    db_backup_logs,
    search,
    shared_scan,
    system_control,
    system_settings,
    upload,
    user_settings,
    users,
    version,
)

# 创建API路由器
api_router = APIRouter()

# 健康检查（放在最前面）
api_router.include_router(health.router, tags=["健康检查"])  # 已定义prefix="/health"

# 注册所有路由
# 注意：路由文件中已定义prefix的，这里不再重复添加prefix
# 路由文件中未定义prefix的，在这里统一添加prefix

# 激活码（公开接口，无需登录）
api_router.include_router(activation.router, prefix="/activation", tags=["激活码"])

# 认证相关
api_router.include_router(auth.router, prefix="/auth", tags=["认证"])

# 用户管理
api_router.include_router(users.router, prefix="/users", tags=["用户管理"])
api_router.include_router(user_settings.router, prefix="/user-settings", tags=["用户设置"])

# 账号管理
api_router.include_router(cookies.router, prefix="/cookies", tags=["账号管理"])

# 商品和订单
api_router.include_router(items.items_router, tags=["商品管理"])  # items.py已定义prefix="/items"
api_router.include_router(orders.router, prefix="/orders", tags=["订单管理"])
api_router.include_router(product_publish.router, tags=["商品发布"])  # 已定义prefix="/product-publish"
api_router.include_router(publish_addresses.router, tags=["商品发布随机地址池"])  # 已定义prefix="/product-publish/addresses"
api_router.include_router(personal_addresses.router, tags=["个人发布地址库"])  # 已定义prefix="/product-publish/personal-addresses"
api_router.include_router(listing_monitor_category.router, tags=["商品监控分类"])  # 已定义prefix="/product-monitor/categories"
api_router.include_router(listing_monitor.router, tags=["商品上新监控"])  # 已定义prefix="/product-monitor/listing-tasks"
api_router.include_router(collect_fallback_account.router, tags=["兜底采集账号"])  # 已定义prefix="/product-monitor/collect-fallback-accounts"
api_router.include_router(order_fallback_account.router, tags=["兜底下单账号"])  # 已定义prefix="/product-monitor/order-fallback-accounts"
api_router.include_router(external_cookie.router, tags=["外部Cookie同步"])  # 已定义prefix="/external/account-cookie"
api_router.include_router(keywords.router, prefix="/keywords-with-item-id", tags=["关键词管理"])
api_router.include_router(cards.router, prefix="/cards", tags=["卡券管理"])
api_router.include_router(distribution.router, prefix="/distribution", tags=["分销管理"])
api_router.include_router(card_dock.router, tags=["分销卡券"])  # 已定义prefix="/card-dock"
api_router.include_router(payment.router, tags=["支付管理"])  # 已定义prefix="/payment"

# AI回复
api_router.include_router(ai.router, prefix="/ai-reply-settings", tags=["AI回复"])
api_router.include_router(ai.test_router, tags=["AI回复测试"])  # ai.py已定义prefix="/ai-reply-test"

# 消息和回复
api_router.include_router(message.router, prefix="/messages", tags=["消息管理"])
api_router.include_router(default_replies.router, prefix="/default-replies", tags=["默认回复"])
api_router.include_router(confirm_receipt_messages.router, prefix="/confirm-receipt-messages", tags=["确认收货消息"])
api_router.include_router(message_filters.router, prefix="/message-filters", tags=["消息过滤器"])

# 通知管理
api_router.include_router(notifications.channels_router, tags=["通知管理"])  # 已定义prefix="/notification-channels"
api_router.include_router(notifications.messages_router, tags=["通知管理"])  # 已定义prefix="/message-notifications"

# 自动化功能
api_router.include_router(auto_rate.router, prefix="/auto-rate", tags=["自动评价"])

# 系统设置
api_router.include_router(system_settings.router, prefix="/system-settings", tags=["系统设置"])
api_router.include_router(system_control.router, tags=["系统管理"])  # 已定义prefix="/system-control"
api_router.include_router(announcements.router, prefix="/announcements", tags=["公告管理"])
api_router.include_router(popup_announcements.router, prefix="/popup-announcements", tags=["弹窗公告"])
api_router.include_router(feedback.router, prefix="/feedbacks", tags=["反馈管理"])
api_router.include_router(advertisements.router, prefix="/advertisements", tags=["广告管理"])
api_router.include_router(auto_reply_logs.router, tags=["消息日志"])
api_router.include_router(account_login_logs.router, tags=["账号登录日志"])
api_router.include_router(db_backup_logs.router, tags=["数据库备份日志"])
api_router.include_router(risk_control_logs.router, tags=["风控日志"])

# 管理员功能
api_router.include_router(admin.router, prefix="/admin", tags=["管理员功能"])
api_router.include_router(cookies_refresh_logs.router, prefix="/admin", tags=["COOKIES刷新日志"])
api_router.include_router(api_cookie_renew_logs.router, prefix="/admin", tags=["接口续期Cookies日志"])

# 代理和上传
api_router.include_router(proxy.router, prefix="/proxy", tags=["代理配置"])
api_router.include_router(refund_cancel.router, prefix="/refund-cancel", tags=["退款订单注销配置"])
api_router.include_router(upload.router, prefix="/upload", tags=["文件上传"])
api_router.include_router(qrcode.router, tags=["群二维码"])  # 已定义prefix="/qrcode"

# Cookie和验证
api_router.include_router(cookie_refresh.router, tags=["Cookie刷新管理"])  # 已定义prefix="/cookie-refresh"
api_router.include_router(face_verification.router, tags=["人脸验证管理"])  # 已定义prefix="/face-verification"
api_router.include_router(geetest.router, tags=["极验验证码"])  # 已定义prefix="/geetest"
api_router.include_router(captcha.router, tags=["验证码"])  # 已定义prefix="/captcha"
api_router.include_router(qr_login.router, tags=["二维码登录"])  # 已定义prefix="/qr-login"
api_router.include_router(password_login.router, tags=["密码登录"])  # 已定义prefix="/password-login"
api_router.include_router(shared_scan.router, tags=["共享多人扫码登录"])  # 已定义prefix="/shared-scan"

# 数据分析
api_router.include_router(data_analysis.router, tags=["数据分析"])  # 已定义prefix="/data-analysis"

# Goofish相关
api_router.include_router(goofish_compass.router, tags=["Goofish数据罗盘"])  # 已定义prefix="/compass/goofish"
api_router.include_router(goofish_crawler.router, tags=["Goofish定时采集"])  # 已定义prefix="/goofish/crawler"

# 黑名单管理
api_router.include_router(blacklist.router, tags=["黑名单管理"])  # 已定义prefix="/blacklist"

# 搜索
api_router.include_router(search.router, tags=["商品搜索"])  # 已定义prefix="/search"

# 在线聊天
api_router.include_router(chat_new.router, tags=["在线聊天(新)"])  # 已定义prefix="/chat-new"
api_router.include_router(chat_new_ws.router, tags=["在线聊天(新)WebSocket"])  # 已定义prefix="/chat-new"
api_router.include_router(chat_new_image.router, tags=["在线聊天(新)图片发送"])  # 已定义prefix="/chat-new"
api_router.include_router(chat_quick_phrase.router, tags=["在线聊天(新)快捷短语"])  # 已定义prefix="/chat-new"
api_router.include_router(chat_customer_order.router, tags=["在线聊天(新)客户订单"])  # 已定义prefix="/chat-new"
# 版本检测（公开接口，无需登录即可查询版本信息）
api_router.include_router(version.router, tags=["版本检测"])  # 已定义prefix="/version"


__all__ = ["api_router"]
