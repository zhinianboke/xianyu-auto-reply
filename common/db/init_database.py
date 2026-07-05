#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库初始化脚本

功能：
1. 创建所有数据表（如果不存在）
2. 创建默认管理员用户 (admin/admin123)
3. 初始化系统设置

使用方法：
- 服务器启动时自动调用
- 也可以手动运行：python -m common.db.init_database
"""

from __future__ import annotations

import logging
import warnings
from contextlib import contextmanager

from loguru import logger
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SAWarning

from common.db.default_publish_addresses import (
    REMOVED_PUBLISH_ADDRESS_PREFIXES,
    build_default_publish_addresses,
)
from common.db.session import async_engine, async_session_maker
from common.utils.time_utils import get_beijing_now_naive
from common.utils.security import generate_secret_key, get_password_hash


@contextmanager
def suppress_db_warnings():
    """
    上下文管理器：抑制数据库初始化时的重复警告日志
    
    包括：
    - Table 'xxx' already exists
    - Duplicate entry 'xxx' for key 'PRIMARY'
    """
    # 保存原始日志级别
    sqlalchemy_logger = logging.getLogger('sqlalchemy.engine')
    original_level = sqlalchemy_logger.level
    
    # 过滤MySQL警告
    warnings.filterwarnings('ignore', category=SAWarning)
    
    # 设置自定义过滤器
    class DBInitFilter(logging.Filter):
        """过滤数据库初始化时的常见警告"""
        IGNORE_PATTERNS = [
            'already exists',
            'Duplicate entry',
        ]
        
        def filter(self, record):
            msg = record.getMessage()
            for pattern in self.IGNORE_PATTERNS:
                if pattern in msg:
                    return False
            return True
    
    db_filter = DBInitFilter()
    
    # 添加过滤器到所有相关logger
    loggers_to_filter = [
        logging.getLogger('sqlalchemy.engine'),
        logging.getLogger('sqlalchemy.pool'),
        logging.getLogger('asyncmy'),
        logging.getLogger(),  # root logger
    ]
    
    for lg in loggers_to_filter:
        lg.addFilter(db_filter)
    
    try:
        yield
    finally:
        # 恢复原始状态
        for lg in loggers_to_filter:
            lg.removeFilter(db_filter)
        warnings.filterwarnings('default', category=SAWarning)


class DatabaseInitializer:
    """数据库初始化器"""

    DEFAULT_SETTINGS = (
        (
            "disclaimer.title",
            "免责声明",
            "系统免责声明标题",
        ),
        (
            "disclaimer.content",
            "数据存储说明\n1. 本系统在运行过程中，为保障服务正常运行，会存储用户账号密码、登录 Cookie、商品信息、卡券信息等业务数据。\n2. 上述数据仅用于系统功能运行、自动化处理和业务管理，不作为其他用途。\n3. 请您自行确认服务器环境、账号权限和数据保管措施的安全性。\n\n用户须知\n1. 用户应确保使用本系统的行为符合相关平台规则和法律法规。\n2. 因用户自身违规操作、账号共享、密码泄露、服务器安全问题导致的损失，由用户自行承担。\n3. 建议用户定期备份重要数据，因系统故障、第三方平台变更、不可抗力等导致的异常或损失，本系统不承担责任。\n4. 本系统依赖第三方平台接口和网络环境，无法保证服务始终连续、稳定、无中断。\n\n隐私与风险提示\n1. 请勿在未充分评估风险的情况下接入生产环境或敏感账号。\n2. 使用本系统即表示您已充分理解并接受相关风险，并愿意自行承担相应责任。",
            "系统免责声明正文",
        ),
        (
            "disclaimer.checkbox_text",
            "我已阅读并同意以上免责声明",
            "免责声明勾选提示文案",
        ),
        (
            "disclaimer.agree_button_text",
            "同意并继续",
            "免责声明同意按钮文案",
        ),
        (
            "disclaimer.disagree_button_text",
            "不同意",
            "免责声明不同意按钮文案",
        ),
        (
            "login.system_name",
            "闲鱼管理系统",
            "登录页系统名称",
        ),
        (
            "login.system_title",
            "高效专业的\n闲鱼自动化管理平台",
            "登录页系统标题",
        ),
        (
            "login.system_description",
            "自动回复、智能客服、订单管理、数据分析，一站式解决闲鱼运营难题",
            "登录页系统描述",
        ),
        (
            "auth.footer_ad_html",
            "© 2026 划算云服务器 ·<a href=\"http://www.hsykj.com\" target=\"_BLANK\">www.hsykj.com</a>",
            "登录页和注册页底部广告 HTML",
        ),
        (
            "theme.effect",
            "solid",
            "系统主题效果（solid-纯色，gradient-炫彩）",
        ),
        (
            "theme.color_preset",
            "ocean",
            "系统主题颜色预设",
        ),
        (
            "log.retention_days",
            "7",
            "日志保留天数（所有模块生效，修改后重启服务生效）",
        ),
        (
            "show_default_login_info",
            "true",
            "登录页是否展示默认账号密码提示",
        ),
    )

    DEFAULT_SCHEDULED_TASKS = (
        (
            "redelivery",
            "补发货任务",
            5,
            True,
            "定时补发货任务",
        ),
        (
            "rate",
            "补评价任务",
            20,
            True,
            "定时补评价任务",
        ),
        (
            "polish",
            "擦亮任务",
            60,
            True,
            "定时擦亮商品任务",
        ),
        (
            "day_switch",
            "平台日切换任务",
            60,
            True,
            "定时执行平台日切换任务",
        ),
        (
            "cleanup_browser_data",
            "清理被禁用账号浏览器数据任务",
            600,
            False,
            "定时清理被禁用账号的浏览器数据",
        ),
        (
            "fetch_orders",
            "获取闲鱼订单任务",
            600,
            True,
            "定时获取闲鱼订单数据",
        ),
        (
            "fetch_pending_orders",
            "获取待发货订单任务",
            60,
            True,
            "定时获取待发货订单并同步收货人姓名/手机号/地址等信息",
        ),
        (
            "fetch_refund_orders",
            "退款订单获取任务",
            120,
            True,
            "定时获取退款订单数据，更新订单状态并触发退款订单注销",
        ),
        (
            "fetch_items",
            "获取闲鱼商品任务",
            1200,
            True,
            "定时获取所有启用账号的闲鱼在售商品并入库（新增或更新）",
        ),
        (
            "login_renew",
            "登录续期任务",
            600,
            False,
            "定时执行闲鱼账号登录续期",
        ),
        (
            "cookies_refresh",
            "COOKIES续期任务",
            600,
            False,
            "定时执行闲鱼账号浏览器COOKIES续期",
        ),
        (
            "api_cookie_renew",
            "接口续期Cookies任务",
            3600,
            True,
            "定时通过 hasLogin.do 接口为启用账号续期Cookies并同步Set-Cookie",
        ),
        (
            "close_notice",
            "关闭账号消息通知任务",
            600,
            False,
            "定时关闭账号消息通知",
        ),
        (
            "red_flower",
            "求小红花任务",
            300,
            True,
            "定时自动求小红花",
        ),
        (
            "db_backup",
            "数据库备份任务",
            3600,
            True,
            "定时备份数据库所有表结构与数据到文件",
        ),
        (
            "delivery_timeout",
            "发货超时检测任务",
            60,
            True,
            "定时将超过阈值仍处于 unknown 的自动发货消息日志标记为 timeout",
        ),
        (
            "listing_monitor",
            "商品监控任务",
            60,
            True,
            "定时执行商品监控：按监控类型调用闲鱼搜索接口采集商品并入库，每次记录监控日志",
        ),
        (
            "seller_fill",
            "采集商品卖家ID补全",
            60,
            True,
            "定时查询采集商品中卖家ID为空的数据，调用商品详情接口补全卖家真实ID与详情",
        ),
        (
            "dm_send",
            "采集商品发送私信",
            60,
            True,
            "定时查询卖家ID已补全且未私信的采集商品，用监控任务配置的私信账号发起私信",
        ),
        (
            "auto_order",
            "采集商品自动下单",
            60,
            True,
            "定时查询已私信且未下单的采集商品，用监控任务配置的下单账号创建订单（拍下，不自动付款）",
        ),
    )
    
    # ========== 所有数据表的DDL定义 ==========
    # 表名统一使用 xy_ 前缀
    # 所有表都有主键，无外键约束
    
    TABLES_DDL = {
        # 1. 用户表
        "xy_users": """
            CREATE TABLE IF NOT EXISTS xy_users (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '用户ID',
                external_id VARCHAR(64) COMMENT '外部ID',
                username VARCHAR(64) NOT NULL UNIQUE COMMENT '用户名',
                email VARCHAR(255) NOT NULL UNIQUE COMMENT '邮箱',
                phone VARCHAR(32) COMMENT '手机号',
                password_hash VARCHAR(255) NOT NULL COMMENT '密码哈希',
                status ENUM('ACTIVE', 'INACTIVE', 'SUSPENDED', 'DELETED') DEFAULT 'ACTIVE' COMMENT '用户状态',
                role ENUM('ADMIN', 'OPERATOR', 'MEMBER') DEFAULT 'MEMBER' COMMENT '用户角色',
                account_limit INT DEFAULT NULL COMMENT '可添加账号数量',
                last_login_at DATETIME COMMENT '最后登录时间',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX idx_external_id (external_id),
                INDEX idx_username (username),
                INDEX idx_email (email),
                INDEX idx_user_created (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户表';
        """,

        # 2. 用户设置表
        "xy_user_settings": """
            CREATE TABLE IF NOT EXISTS xy_user_settings (
                id INT PRIMARY KEY AUTO_INCREMENT COMMENT '设置ID',
                user_id INT NOT NULL COMMENT '用户ID',
                `key` VARCHAR(120) NOT NULL COMMENT '设置键',
                value TEXT NOT NULL COMMENT '设置值',
                description TEXT COMMENT '设置描述',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX idx_user_id (user_id),
                UNIQUE KEY uk_user_key (user_id, `key`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户设置表';
        """,
        
        # 3. 系统设置表
        "xy_system_settings": """
            CREATE TABLE IF NOT EXISTS xy_system_settings (
                `key` VARCHAR(120) PRIMARY KEY COMMENT '设置键',
                value TEXT NOT NULL COMMENT '设置值',
                description TEXT COMMENT '设置描述',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统设置表';
        """,
        
        # 4. 闲鱼账号表
        "xy_accounts": """
            CREATE TABLE IF NOT EXISTS xy_accounts (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '账号ID',
                owner_id BIGINT NOT NULL COMMENT '所属用户ID',
                account_id VARCHAR(80) NOT NULL COMMENT '账号标识',
                display_name VARCHAR(120) COMMENT '显示名称',
                unb VARCHAR(64) COMMENT 'UNB标识',
                cookie TEXT NOT NULL COMMENT 'Cookie信息',
                login_method VARCHAR(20) NOT NULL COMMENT '登录方式',
                status VARCHAR(20) NOT NULL DEFAULT 'active' COMMENT '账号状态',
                username VARCHAR(120) COMMENT '登录用户名',
                login_password TEXT COMMENT '登录密码',
                remark VARCHAR(255) COMMENT '备注',
                pause_duration INT DEFAULT 10 COMMENT '暂停时长(分钟)',
                auto_confirm TINYINT(1) DEFAULT 0 COMMENT '自动确认发货',
                show_browser TINYINT(1) DEFAULT 0 COMMENT '显示浏览器',
                metadata JSON COMMENT '元数据',
                last_login_at DATETIME COMMENT '最后登录时间',
                last_refresh_at DATETIME COMMENT '最后刷新时间',
                proxy_type VARCHAR(20) DEFAULT 'none' COMMENT '代理类型',
                proxy_host VARCHAR(255) COMMENT '代理主机',
                proxy_port INT COMMENT '代理端口',
                proxy_user VARCHAR(120) COMMENT '代理用户名',
                proxy_pass VARCHAR(255) COMMENT '代理密码',
                message_expire_time INT DEFAULT 3600 COMMENT '相同消息等待时间(秒)',
                reply_delay_seconds INT DEFAULT 0 COMMENT '自动回复延迟时间(秒)，0表示立即回复',
                disable_reason VARCHAR(255) COMMENT '禁用原因',
                scheduled_redelivery TINYINT(1) NOT NULL DEFAULT 0 COMMENT '定时补发货开关',
                scheduled_rate TINYINT(1) NOT NULL DEFAULT 0 COMMENT '定时补评价开关',
                auto_polish TINYINT(1) NOT NULL DEFAULT 0 COMMENT '商品自动擦亮开关',
                confirm_before_send TINYINT(1) NOT NULL DEFAULT 0 COMMENT '发货成功再发卡券开关',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX idx_owner_id (owner_id),
                UNIQUE KEY uk_account_id (account_id),
                INDEX idx_unb (unb),
                INDEX idx_account_created (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='闲鱼账号表';
        """,

        # 5. 关键词规则表
        "xy_keyword_rules": """
            CREATE TABLE IF NOT EXISTS xy_keyword_rules (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '规则ID',
                owner_id BIGINT NOT NULL COMMENT '所属用户ID',
                account_id BIGINT COMMENT '关联账号ID',
                keyword VARCHAR(120) NOT NULL COMMENT '关键词',
                reply_content TEXT COMMENT '回复内容',
                reply_type VARCHAR(16) COMMENT '回复类型(text/image)',
                image_url VARCHAR(512) COMMENT '图片URL',
                item_id VARCHAR(64) COMMENT '商品ID',
                priority INT DEFAULT 100 COMMENT '优先级',
                is_active TINYINT(1) DEFAULT 1 COMMENT '是否启用',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX idx_owner_id (owner_id),
                INDEX idx_account_id (account_id),
                INDEX idx_keyword (keyword),
                INDEX idx_kw_account_item (account_id, item_id),
                INDEX idx_kw_account_active (account_id, is_active)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='关键词规则表';
        """,
        
        # 6. 商品目录表
        "xy_catalog_items": """
            CREATE TABLE IF NOT EXISTS xy_catalog_items (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '商品ID',
                owner_id BIGINT NOT NULL COMMENT '所属用户ID',
                account_id BIGINT NOT NULL COMMENT '关联账号ID',
                item_id VARCHAR(64) NOT NULL COMMENT '商品标识',
                title VARCHAR(255) COMMENT '商品标题',
                price VARCHAR(32) COMMENT '商品价格',
                ai_prompt TEXT COMMENT '商品AI提示词',
                is_polished TINYINT(1) DEFAULT 0 COMMENT '是否擦亮',
                metadata JSON COMMENT '商品元数据',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX idx_owner_id (owner_id),
                INDEX idx_account_id (account_id),
                INDEX idx_item_id (item_id),
                INDEX idx_cat_account_item (account_id, item_id),
                INDEX idx_cat_owner_created (owner_id, created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商品目录表';
        """,
        
        # 8. 订单表
        "xy_orders": """
            CREATE TABLE IF NOT EXISTS xy_orders (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '订单ID',
                owner_id BIGINT NOT NULL COMMENT '所属用户ID',
                order_no VARCHAR(64) NOT NULL COMMENT '订单号',
                status VARCHAR(32) NOT NULL COMMENT '订单状态',
                buyer_nick VARCHAR(120) COMMENT '买家昵称',
                buyer_id VARCHAR(64) COMMENT '买家ID',
                chat_id VARCHAR(64) COMMENT '聊天会话ID',
                item_id VARCHAR(64) COMMENT '商品ID',
                spec_name VARCHAR(120) COMMENT '规格名称',
                spec_value VARCHAR(120) COMMENT '规格值',
                quantity INT DEFAULT 1 COMMENT '数量',
                amount DECIMAL(12,2) COMMENT '金额',
                currency VARCHAR(8) DEFAULT 'CNY' COMMENT '货币',
                account_id VARCHAR(64) COMMENT '账号标识',
                account_name VARCHAR(120) COMMENT '账号名称',
                is_bargain TINYINT(1) DEFAULT 0 COMMENT '是否小刀',
                receiver_name VARCHAR(120) COMMENT '收货人姓名',
                receiver_phone VARCHAR(32) COMMENT '收货人手机号',
                receiver_address VARCHAR(512) COMMENT '收货地址',
                delivery_fail_reason VARCHAR(2000) COMMENT '发货失败原因',
                item_snapshot JSON COMMENT '商品快照',
                metadata JSON COMMENT '元数据',
                source VARCHAR(32) COMMENT '数据来源：fetch_xianyu-获取闲鱼订单按钮',
                placed_at DATETIME COMMENT '下单时间',
                synced_at DATETIME COMMENT '同步时间',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                UNIQUE KEY uk_order_account_no (account_id, order_no),
                INDEX idx_owner_id (owner_id),
                INDEX idx_order_no (order_no),
                INDEX idx_account_id (account_id),
                INDEX idx_order_created_at (created_at),
                INDEX idx_order_placed_status (placed_at, status),
                INDEX idx_order_created_status (created_at, status),
                INDEX idx_order_owner_placed (owner_id, placed_at),
                INDEX idx_order_owner_created (owner_id, created_at),
                INDEX idx_order_owner_account_placed (owner_id, account_id, placed_at),
                INDEX idx_order_owner_account_buyer_created (owner_id, account_id, buyer_id, created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='订单表';
        """,

        # 9. 卡券表
        "xy_cards": """
            CREATE TABLE IF NOT EXISTS xy_cards (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '卡券ID',
                user_id BIGINT NOT NULL COMMENT '所属用户ID',
                item_id VARCHAR(64) COMMENT '关联商品ID',
                name VARCHAR(255) NOT NULL COMMENT '卡券名称',
                type VARCHAR(50) NOT NULL COMMENT '卡券类型(api/text/data/image)',
                description TEXT COMMENT '卡券描述',
                enabled TINYINT(1) DEFAULT 1 COMMENT '是否启用',
                delay_seconds INT DEFAULT 0 COMMENT '延迟秒数',
                delivery_count INT DEFAULT 0 COMMENT '发货次数',
                price VARCHAR(32) COMMENT '对接价格',
                is_dockable TINYINT(1) DEFAULT 0 COMMENT '是否可对接',
                fee_payer VARCHAR(32) COMMENT '手续费支付方式：distributor-分销主支付，dealer-分销商支付',
                is_multi_spec TINYINT(1) DEFAULT 0 COMMENT '是否多规格',
                spec_name VARCHAR(255) COMMENT '规格名称',
                spec_value VARCHAR(255) COMMENT '规格值',
                api_config TEXT COMMENT 'API配置(JSON)',
                text_content TEXT COMMENT '文本内容',
                data_content TEXT COMMENT '数据内容',
                image_url VARCHAR(512) COMMENT '图片URL',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX idx_user_id (user_id),
                INDEX idx_item_id (item_id),
                INDEX idx_card_user_item (user_id, item_id),
                INDEX idx_cards_dockable_enabled (is_dockable, enabled)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='卡券表';
        """,
        
        # 10. 默认回复表
        "xy_default_replies": """
            CREATE TABLE IF NOT EXISTS xy_default_replies (
                id INT PRIMARY KEY AUTO_INCREMENT COMMENT '回复ID',
                account_id VARCHAR(80) NOT NULL COMMENT '账号标识',
                item_id VARCHAR(64) DEFAULT NULL COMMENT '商品ID(空为账号默认回复)',
                enabled TINYINT(1) DEFAULT 0 COMMENT '是否启用',
                reply_type VARCHAR(16) DEFAULT 'text' COMMENT '回复类型：text-文本(可附带图片)，api-接口',
                reply_content TEXT COMMENT '回复内容',
                reply_image VARCHAR(512) COMMENT '回复图片URL',
                api_url VARCHAR(1024) DEFAULT NULL COMMENT 'API地址(reply_type=api时POST此地址)',
                api_timeout INT DEFAULT 80 COMMENT 'API请求超时时间(秒)',
                reply_once TINYINT(1) DEFAULT 0 COMMENT '只回复一次',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX idx_account_id (account_id),
                INDEX idx_item_id (item_id),
                UNIQUE KEY uk_account_item (account_id, item_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='默认回复表';
        """,
        
        # 11. 默认回复记录表
        "xy_default_reply_records": """
            CREATE TABLE IF NOT EXISTS xy_default_reply_records (
                id INT PRIMARY KEY AUTO_INCREMENT COMMENT '记录ID',
                account_id VARCHAR(80) NOT NULL COMMENT '账号标识',
                item_id VARCHAR(64) DEFAULT NULL COMMENT '商品ID(空为账号默认回复)',
                user_id VARCHAR(64) NOT NULL COMMENT '被回复用户ID',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                INDEX idx_account_id (account_id),
                INDEX idx_user_id (user_id),
                INDEX idx_account_item_user (account_id, item_id, user_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='默认回复记录表';
        """,
        
        # 12. AI聊天消息表
        "xy_ai_chat_messages": """
            CREATE TABLE IF NOT EXISTS xy_ai_chat_messages (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '消息ID',
                chat_id VARCHAR(64) NOT NULL COMMENT '聊天ID',
                cookie_id VARCHAR(80) NOT NULL COMMENT '账号标识',
                user_id VARCHAR(64) NOT NULL COMMENT '用户ID',
                item_id VARCHAR(64) COMMENT '商品ID',
                role VARCHAR(20) NOT NULL COMMENT '角色(user/assistant)',
                content TEXT NOT NULL COMMENT '消息内容',
                intent VARCHAR(20) COMMENT '意图(price/tech/default)',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                INDEX idx_chat_id (chat_id),
                INDEX idx_cookie_id (cookie_id),
                INDEX ix_ai_chat_messages_chat_cookie (chat_id, cookie_id),
                INDEX ix_ai_chat_messages_intent (cookie_id, intent)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI聊天消息表';
        """,

        # 14. 风控日志表
        "xy_risk_control_logs": """
            CREATE TABLE IF NOT EXISTS xy_risk_control_logs (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '日志ID',
                owner_id BIGINT COMMENT '所属用户ID',
                account_id BIGINT COMMENT '关联账号ID',
                account_identifier VARCHAR(80) COMMENT '账号标识',
                event_type VARCHAR(64) DEFAULT 'slider_captcha' COMMENT '事件类型',
                event_description TEXT COMMENT '事件描述',
                processing_result TEXT COMMENT '处理结果',
                processing_status VARCHAR(32) DEFAULT 'processing' COMMENT '处理状态',
                captcha_engine VARCHAR(32) DEFAULT NULL COMMENT '验证通过引擎：playwright-主引擎/drissionpage-兜底引擎/real_mouse-真人鼠标引擎',
                call_type VARCHAR(16) DEFAULT 'local' COMMENT '调用类型：local-本机/remote-远程(外部凭秘钥调用)',
                call_user VARCHAR(128) DEFAULT NULL COMMENT '调用用户：仅远程调用记录(按秘钥查到的用户名)',
                error_message TEXT COMMENT '错误信息',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX idx_owner_id (owner_id),
                INDEX idx_account_id (account_id),
                INDEX idx_event_type (event_type),
                INDEX idx_rcl_account_status (account_id, processing_status),
                INDEX idx_rcl_identifier_status_created (account_identifier, processing_status, created_at),
                INDEX idx_rcl_owner_created (owner_id, created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='风控日志表';
        """,

        # 14.1 账号登录日志表（记录密码登录的每一次尝试与最终结果）
        "xy_account_login_logs": """
            CREATE TABLE IF NOT EXISTS xy_account_login_logs (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '日志ID',
                owner_id BIGINT COMMENT '所属用户ID',
                account_id BIGINT COMMENT '关联账号ID（xy_accounts.id）',
                account_identifier VARCHAR(80) COMMENT '业务账号ID',
                username VARCHAR(255) COMMENT '登录用户名快照',
                trigger_reason VARCHAR(128) COMMENT '触发本次登录的原因',
                login_status VARCHAR(32) DEFAULT 'failed' COMMENT '登录状态：success/failed/skipped_cooldown/no_credentials',
                failure_reason VARCHAR(64) COMMENT '失败大类：bad_credentials/baxia_punish_captcha/account_info_missing/exception/...',
                error_message TEXT COMMENT '详细错误消息',
                updated_cookie_names VARCHAR(500) DEFAULT NULL COMMENT '接口续期更新的Cookie字段名（逗号分隔）',
                duration_ms INT COMMENT '整个登录流程耗时（毫秒）',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                INDEX idx_all_owner_id (owner_id),
                INDEX idx_all_account_id (account_id),
                INDEX idx_all_login_status (login_status),
                INDEX idx_all_identifier_status_created (account_identifier, login_status, created_at),
                INDEX idx_all_owner_created (owner_id, created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='账号登录日志表';
        """,
        
        # 15. 通知渠道表
        "xy_notification_channels": """
            CREATE TABLE IF NOT EXISTS xy_notification_channels (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '渠道ID',
                owner_id BIGINT NOT NULL COMMENT '所属用户ID',
                name VARCHAR(120) NOT NULL COMMENT '渠道名称',
                channel_type VARCHAR(32) NOT NULL COMMENT '渠道类型',
                config JSON COMMENT '渠道配置',
                enabled TINYINT(1) DEFAULT 1 COMMENT '是否启用',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX idx_owner_id (owner_id),
                INDEX idx_channel_type (channel_type)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='通知渠道表';
        """,
        
        # 16. 消息通知表
        "xy_message_notifications": """
            CREATE TABLE IF NOT EXISTS xy_message_notifications (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '通知ID',
                owner_id BIGINT NOT NULL COMMENT '所属用户ID',
                account_pk BIGINT NOT NULL COMMENT '关联账号ID',
                account_identifier VARCHAR(80) NOT NULL COMMENT '账号标识',
                channel_id BIGINT NOT NULL COMMENT '渠道ID',
                enabled TINYINT(1) DEFAULT 1 COMMENT '是否启用',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX idx_owner_id (owner_id),
                INDEX idx_account_pk (account_pk),
                INDEX idx_channel_id (channel_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='消息通知表';
        """,

        # 17. 消息过滤规则表
        "xy_message_filters": """
            CREATE TABLE IF NOT EXISTS xy_message_filters (
                id INT PRIMARY KEY AUTO_INCREMENT COMMENT '规则ID',
                account_id VARCHAR(80) NOT NULL COMMENT '账号标识',
                keyword VARCHAR(255) NOT NULL COMMENT '过滤关键词',
                filter_type VARCHAR(20) NOT NULL COMMENT '过滤类型',
                enabled TINYINT(1) DEFAULT 1 COMMENT '是否启用',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX idx_account_id (account_id),
                INDEX idx_keyword (keyword),
                UNIQUE KEY uk_account_keyword_type (account_id, keyword, filter_type)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='消息过滤规则表';
        """,
        
        # 18. 意见反馈表
        "xy_feedbacks": """
            CREATE TABLE IF NOT EXISTS xy_feedbacks (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '反馈ID',
                user_id BIGINT NOT NULL COMMENT '用户ID',
                cookie_id VARCHAR(64) COMMENT '关联账号ID',
                title VARCHAR(100) NOT NULL COMMENT '标题',
                content TEXT NOT NULL COMMENT '内容',
                feedback_type ENUM('FEATURE', 'BUG', 'OTHER') DEFAULT 'OTHER' COMMENT '反馈类型',
                images TEXT COMMENT '图片URL(JSON数组)',
                is_resolved TINYINT(1) DEFAULT 0 COMMENT '是否已解决',
                resolved_at DATETIME COMMENT '解决时间',
                admin_reply TEXT COMMENT '管理员回复',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX idx_user_id (user_id),
                INDEX idx_is_resolved (is_resolved),
                INDEX idx_feedback_type (feedback_type)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='意见反馈表';
        """,

        # 18.1 意见反馈消息表（对话记录）
        "xy_feedback_messages": """
            CREATE TABLE IF NOT EXISTS xy_feedback_messages (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '消息ID',
                feedback_id BIGINT NOT NULL COMMENT '关联反馈ID',
                user_id BIGINT NOT NULL COMMENT '发送者用户ID',
                content TEXT NOT NULL COMMENT '消息内容',
                is_admin TINYINT(1) DEFAULT 0 COMMENT '是否为管理员消息',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX idx_feedback_id (feedback_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='意见反馈消息表';
        """,

        # 18.2 广告表
        "xy_advertisements": """
            CREATE TABLE IF NOT EXISTS xy_advertisements (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '广告ID',
                user_id BIGINT NOT NULL COMMENT '申请用户ID',
                title VARCHAR(200) NOT NULL COMMENT '广告标题',
                content TEXT COMMENT '广告正文',
                link VARCHAR(500) COMMENT '广告链接',
                expire_date DATE COMMENT '到期日期',
                image_url VARCHAR(500) COMMENT '图片URL',
                ad_type ENUM('carousel', 'text') DEFAULT 'text' COMMENT '广告类型',
                months INT COMMENT '购买月数',
                total_amount VARCHAR(32) COMMENT '广告总金额',
                status ENUM('unpaid', 'pending', 'approved') DEFAULT 'unpaid' COMMENT '审核状态',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX idx_user_id (user_id),
                INDEX idx_status (status),
                INDEX idx_ad_type (ad_type),
                INDEX idx_expire_date (expire_date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='广告表';
        """,

        # 19. Goofish 定时抓取任务表
        "xy_goofish_crawl_jobs": """
            CREATE TABLE IF NOT EXISTS xy_goofish_crawl_jobs (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
                owner_id BIGINT NOT NULL COMMENT '归属用户ID',
                cookie_id VARCHAR(80) NOT NULL COMMENT '账号标识',
                keyword VARCHAR(80) NOT NULL COMMENT '抓取关键词',
                interval_seconds INT NOT NULL DEFAULT 900 COMMENT '执行间隔(秒)',
                start_page INT NOT NULL DEFAULT 1 COMMENT '起始页码',
                pages INT NOT NULL DEFAULT 1 COMMENT '抓取页数',
                page_size INT NOT NULL DEFAULT 20 COMMENT '每页数量',
                fetch_detail TINYINT(1) DEFAULT 1 COMMENT '是否抓取详情',
                detail_limit INT NOT NULL DEFAULT 20 COMMENT '抓取详情数量上限',
                enabled TINYINT(1) DEFAULT 1 COMMENT '是否启用',
                last_run_at DATETIME COMMENT '最近一次执行时间',
                last_error TEXT COMMENT '最近一次错误信息',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX idx_owner_id (owner_id),
                INDEX idx_cookie_id (cookie_id),
                INDEX idx_enabled (enabled)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """,

        # 20. Goofish 定时抓取商品表
        "xy_goofish_crawl_items": """
            CREATE TABLE IF NOT EXISTS xy_goofish_crawl_items (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
                job_id BIGINT NOT NULL COMMENT '关联的抓取任务ID',
                item_id VARCHAR(64) NOT NULL COMMENT '闲鱼商品ID',
                title TEXT COMMENT '商品标题',
                price VARCHAR(64) COMMENT '商品价格',
                area VARCHAR(120) COMMENT '所在地区',
                seller_name VARCHAR(120) COMMENT '卖家昵称',
                item_url TEXT COMMENT '商品链接',
                main_image VARCHAR(512) COMMENT '主图URL',
                publish_time VARCHAR(64) COMMENT '发布时间',
                want_count INT COMMENT '想要人数',
                view_count INT COMMENT '浏览次数',
                description TEXT COMMENT '商品描述',
                detail_error VARCHAR(255) COMMENT '详情抓取错误信息',
                raw_json JSON COMMENT '原始数据JSON',
                fetched_at DATETIME NOT NULL COMMENT '抓取时间',
                UNIQUE KEY uk_job_item (job_id, item_id),
                INDEX idx_job_id (job_id),
                INDEX idx_fetched_at (fetched_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """,

        # 21. 定时补发货执行日志表
        "xy_scheduled_redelivery_log": """
            CREATE TABLE IF NOT EXISTS `xy_scheduled_redelivery_log` (
                `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
                `batch_id` VARCHAR(36) NOT NULL COMMENT '批次ID',
                `account_id` VARCHAR(80) NOT NULL COMMENT '账号ID',
                `order_no` VARCHAR(64) NOT NULL COMMENT '订单号',
                `status` VARCHAR(20) NOT NULL COMMENT '状态',
                `error_message` VARCHAR(500) DEFAULT NULL COMMENT '错误信息',
                `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                PRIMARY KEY (`id`),
                INDEX `idx_batch_id` (`batch_id`),
                INDEX `idx_account_id` (`account_id`),
                INDEX `idx_created_at` (`created_at`),
                INDEX `idx_srl_created_batch` (`created_at`, `batch_id`),
                INDEX `idx_srl_batch_created_status` (`batch_id`, `created_at`, `status`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='定时补发货执行日志表';
        """,

        # 22. 公告信息表
        "xy_announcements": """
            CREATE TABLE IF NOT EXISTS xy_announcements (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '公告ID',
                title VARCHAR(200) NOT NULL COMMENT '公告标题',
                content TEXT NOT NULL COMMENT '公告内容',
                is_deleted TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已删除',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='公告信息表';
        """,

        # 22.1 弹窗公告表（用户每次登录时弹窗展示）
        "xy_popup_announcements": """
            CREATE TABLE IF NOT EXISTS xy_popup_announcements (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '弹窗公告ID',
                title VARCHAR(200) NOT NULL COMMENT '公告标题',
                content TEXT NOT NULL COMMENT '公告内容',
                link VARCHAR(500) NULL COMMENT '跳转链接',
                is_enabled TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
                is_deleted TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已删除',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='弹窗公告表';
        """,

        # 23. 确认收货消息表
        "xy_confirm_receipt_messages": """
            CREATE TABLE IF NOT EXISTS xy_confirm_receipt_messages (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
                account_id VARCHAR(80) NOT NULL COMMENT '账号ID',
                enabled TINYINT(1) DEFAULT 0 COMMENT '是否启用',
                message_content TEXT COMMENT '消息文本内容',
                message_image VARCHAR(512) COMMENT '消息图片URL',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                UNIQUE KEY uk_account_id (account_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='确认收货消息配置表';
        """,

        # 24. 自动评价配置表
        "xy_auto_rate_configs": """
            CREATE TABLE IF NOT EXISTS xy_auto_rate_configs (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
                account_id VARCHAR(80) NOT NULL COMMENT '账号ID',
                enabled TINYINT(1) DEFAULT 0 COMMENT '是否启用自动评价',
                rate_type VARCHAR(20) DEFAULT 'text' COMMENT '评价类型',
                text_content TEXT COMMENT '固定评价文字内容',
                api_url VARCHAR(512) COMMENT 'API地址',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                UNIQUE KEY uk_account_id (account_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='自动评价配置表';
        """,

        # 25. 定时补评价执行日志表
        "xy_scheduled_rate_log": """
            CREATE TABLE IF NOT EXISTS `xy_scheduled_rate_log` (
                `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
                `batch_id` VARCHAR(36) NOT NULL COMMENT '批次ID',
                `account_id` VARCHAR(80) NOT NULL COMMENT '账号ID',
                `order_no` VARCHAR(64) NOT NULL COMMENT '订单号',
                `status` VARCHAR(20) NOT NULL COMMENT '状态',
                `error_message` VARCHAR(500) DEFAULT NULL COMMENT '错误信息',
                `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                PRIMARY KEY (`id`),
                INDEX `idx_batch_id` (`batch_id`),
                INDEX `idx_account_id` (`account_id`),
                INDEX `idx_created_at` (`created_at`),
                INDEX `idx_srate_created_batch` (`created_at`, `batch_id`),
                INDEX `idx_srate_batch_created_status` (`batch_id`, `created_at`, `status`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='定时补评价执行日志表';
        """,

        # 26. 定时擦亮执行日志表
        "xy_scheduled_polish_log": """
            CREATE TABLE IF NOT EXISTS `xy_scheduled_polish_log` (
                `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
                `batch_id` VARCHAR(36) NOT NULL COMMENT '批次ID',
                `account_id` VARCHAR(80) NOT NULL COMMENT '账号ID',
                `item_id` VARCHAR(64) NOT NULL COMMENT '商品ID',
                `status` VARCHAR(20) NOT NULL COMMENT '状态',
                `error_message` VARCHAR(500) DEFAULT NULL COMMENT '错误信息',
                `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                PRIMARY KEY (`id`),
                INDEX `idx_batch_id` (`batch_id`),
                INDEX `idx_account_id` (`account_id`),
                INDEX `idx_created_at` (`created_at`),
                INDEX `idx_spol_created_batch` (`created_at`, `batch_id`),
                INDEX `idx_spol_batch_created_status` (`batch_id`, `created_at`, `status`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='定时擦亮执行日志表';
        """,

        # 26.1 登录续期执行日志表
        "xy_scheduled_login_renew_log": """
            CREATE TABLE IF NOT EXISTS `xy_scheduled_login_renew_log` (
                `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
                `batch_id` VARCHAR(36) NOT NULL COMMENT '批次ID',
                `account_id` VARCHAR(80) NOT NULL COMMENT '账号ID',
                `status` VARCHAR(20) NOT NULL COMMENT '状态：success/token_refreshed/session_expired/failed',
                `error_message` VARCHAR(500) DEFAULT NULL COMMENT '错误信息或处理说明',
                `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                PRIMARY KEY (`id`),
                INDEX `idx_batch_id` (`batch_id`),
                INDEX `idx_account_id` (`account_id`),
                INDEX `idx_created_at` (`created_at`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='登录续期执行日志表';
        """,

        # 26.2 Cookie续期计划表
        "xy_cookie_refresh_schedules": """
            CREATE TABLE IF NOT EXISTS `xy_cookie_refresh_schedules` (
                `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
                `account_id` VARCHAR(80) NOT NULL COMMENT '账号ID',
                `expire_at` DATETIME NOT NULL COMMENT '当前Cookie续期到期时间',
                `last_refresh_at` DATETIME DEFAULT NULL COMMENT '最近一次续期成功时间',
                `last_status` VARCHAR(20) DEFAULT NULL COMMENT '最近一次状态：initialized/success/failed',
                `last_error_message` VARCHAR(500) DEFAULT NULL COMMENT '最近一次错误信息',
                `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                PRIMARY KEY (`id`),
                UNIQUE KEY `uk_account_id` (`account_id`),
                INDEX `idx_expire_at` (`expire_at`),
                INDEX `idx_created_at` (`created_at`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Cookie续期计划表';
        """,

        # 26.3 COOKIES刷新日志表
        "xy_scheduled_cookies_refresh_log": """
            CREATE TABLE IF NOT EXISTS `xy_scheduled_cookies_refresh_log` (
                `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
                `batch_id` VARCHAR(36) NOT NULL COMMENT '批次ID',
                `account_id` VARCHAR(80) NOT NULL COMMENT '账号ID',
                `status` VARCHAR(20) NOT NULL COMMENT '状态：initialized/success/failed',
                `updated_cookie_count` INT NOT NULL DEFAULT 0 COMMENT '本次增量更新的Cookie字段数量',
                `next_expire_at` DATETIME DEFAULT NULL COMMENT '下次到期时间',
                `error_message` VARCHAR(500) DEFAULT NULL COMMENT '错误信息或处理说明',
                `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                PRIMARY KEY (`id`),
                INDEX `idx_batch_id` (`batch_id`),
                INDEX `idx_account_id` (`account_id`),
                INDEX `idx_status` (`status`),
                INDEX `idx_created_at` (`created_at`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='COOKIES刷新日志表';
        """,

        # 26.4 接口续期Cookies执行日志表
        "xy_scheduled_api_cookie_renew_log": """
            CREATE TABLE IF NOT EXISTS `xy_scheduled_api_cookie_renew_log` (
                `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
                `batch_id` VARCHAR(36) NOT NULL COMMENT '批次ID，标识一次定时任务执行',
                `account_id` VARCHAR(80) NOT NULL COMMENT '账号ID',
                `status` VARCHAR(30) NOT NULL COMMENT '状态：success/cookie_updated/browser_renewed/need_password_login/failed',
                `updated_cookie_count` INT NOT NULL DEFAULT 0 COMMENT '本次更新的Cookie字段数量',
                `updated_cookie_names` TEXT DEFAULT NULL COMMENT '本次更新的Cookie字段名列表（逗号分隔）',
                `response_content` TEXT DEFAULT NULL COMMENT '接口返回内容（用于失败排查），最大裁剪到2000字符',
                `error_message` VARCHAR(500) DEFAULT NULL COMMENT '错误信息或处理说明',
                `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                PRIMARY KEY (`id`),
                INDEX `idx_batch_id` (`batch_id`),
                INDEX `idx_account_id` (`account_id`),
                INDEX `idx_status` (`status`),
                INDEX `idx_created_at` (`created_at`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='接口续期Cookies执行日志表';
        """,

        # 27. 定时任务配置表
        "xy_scheduled_tasks": """
            CREATE TABLE IF NOT EXISTS `xy_scheduled_tasks` (
                `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
                `task_code` VARCHAR(50) NOT NULL COMMENT '任务代码',
                `task_name` VARCHAR(100) NOT NULL COMMENT '任务名称',
                `interval_seconds` INT NOT NULL DEFAULT 60 COMMENT '执行间隔(秒)',
                `enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
                `description` TEXT COMMENT '任务描述',
                `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                PRIMARY KEY (`id`),
                UNIQUE KEY `uk_task_code` (`task_code`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='定时任务配置表';
        """,

        # 28. 卡券与商品多对多关联表
        "xy_card_item_relations": """
            CREATE TABLE IF NOT EXISTS xy_card_item_relations (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
                user_id BIGINT NOT NULL COMMENT '所属用户ID',
                card_id BIGINT NOT NULL COMMENT '卡券ID',
                item_id VARCHAR(64) NOT NULL COMMENT '商品ID',
                source VARCHAR(20) DEFAULT 'own' COMMENT '卡券来源：own-自有，dock_l1-一级对接，dock_l2-二级对接',
                dock_record_id BIGINT NOT NULL DEFAULT 0 COMMENT '对接记录ID（对接卡券时关联，0表示自有卡券）',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX idx_user_id (user_id),
                INDEX idx_card_id (card_id),
                INDEX idx_item_id (item_id),
                INDEX idx_cir_user_item (user_id, item_id),
                UNIQUE KEY uk_card_item_dock (card_id, item_id, dock_record_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='卡券商品关联表';
        """,

        # 29. 对接记录表
        "xy_dock_records": """
            CREATE TABLE IF NOT EXISTS xy_dock_records (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
                user_id BIGINT NOT NULL COMMENT '用户ID',
                card_id BIGINT NOT NULL COMMENT '来源卡券ID',
                dock_name VARCHAR(255) NOT NULL COMMENT '对接名称',
                markup_amount VARCHAR(32) NOT NULL DEFAULT '0.00' COMMENT '加价金额',
                remark TEXT COMMENT '备注',
                delivery_count INT NOT NULL DEFAULT 0 COMMENT '发货次数',
                status TINYINT(1) DEFAULT 1 COMMENT '对接状态：1启用 0停用',
                disable_reason VARCHAR(255) DEFAULT NULL COMMENT '禁用原因',
                owner_disabled TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否被上级禁用锁定：1是 0否',
                level INT NOT NULL DEFAULT 1 COMMENT '分销层级：1=一级分销，2=二级分销',
                parent_dock_id BIGINT DEFAULT NULL COMMENT '上级对接记录ID，一级分销为NULL',
                source_user_id BIGINT DEFAULT NULL COMMENT '上级分销商用户ID，一级分销为NULL',
                allow_sub_dock TINYINT(1) DEFAULT 0 COMMENT '是否允许下级对接',
                sub_dock_price VARCHAR(32) DEFAULT NULL COMMENT '给下级的对接价格（一级分销商设定）',
                sub_dock_visibility VARCHAR(32) DEFAULT NULL COMMENT '下级对接可见性：public-所有人可见，dealer_only-仅绑定对接码的分销商可见',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX idx_user_id (user_id),
                INDEX idx_card_id (card_id),
                INDEX idx_parent_dock_id (parent_dock_id),
                INDEX idx_dock_user_level (user_id, level),
                INDEX idx_dock_source_level (source_user_id, level)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='对接记录表';
        """,

        # 30. 资金流水表
        "xy_fund_flows": """
            CREATE TABLE IF NOT EXISTS xy_fund_flows (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
                user_id BIGINT NOT NULL COMMENT '用户ID',
                type VARCHAR(32) NOT NULL COMMENT '流水类型：income-收入，expense-支出',
                amount VARCHAR(32) NOT NULL COMMENT '发生额',
                balance_before VARCHAR(32) NOT NULL COMMENT '发生前余额',
                balance_after VARCHAR(32) NOT NULL COMMENT '发生后余额',
                order_id BIGINT DEFAULT NULL COMMENT '关联订单ID',
                dock_record_id BIGINT DEFAULT NULL COMMENT '关联对接记录ID',
                description VARCHAR(500) DEFAULT NULL COMMENT '流水描述',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '发生时间',
                INDEX idx_user_id (user_id),
                INDEX idx_order_id (order_id),
                INDEX idx_dock_record_id (dock_record_id),
                INDEX idx_created_at (created_at),
                INDEX idx_ff_user_id_desc (user_id, id),
                INDEX idx_ff_user_type_id_desc (user_id, type, id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='资金流水表';
        """,

        # 31. 充值订单表
        "xy_recharge_orders": """
            CREATE TABLE IF NOT EXISTS xy_recharge_orders (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
                order_no VARCHAR(64) NOT NULL COMMENT '充值订单号',
                user_id BIGINT NOT NULL COMMENT '用户ID',
                amount VARCHAR(32) NOT NULL COMMENT '充值金额',
                status VARCHAR(32) NOT NULL DEFAULT 'pending' COMMENT '订单状态：pending-待支付，paid-已支付，expired-已过期，failed-失败',
                trade_no VARCHAR(128) DEFAULT NULL COMMENT '支付宝交易号',
                qr_code VARCHAR(512) DEFAULT NULL COMMENT '支付二维码内容',
                paid_at DATETIME DEFAULT NULL COMMENT '支付时间',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                UNIQUE INDEX idx_order_no (order_no),
                INDEX idx_user_id (user_id),
                INDEX idx_status (status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='充值订单表';
        """,

        # 32. 对接码绑定表
        "xy_dock_code_bindings": """
            CREATE TABLE IF NOT EXISTS xy_dock_code_bindings (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
                user_id BIGINT NOT NULL COMMENT '绑定用户ID（分销商）',
                dock_code VARCHAR(32) NOT NULL COMMENT '对接码',
                target_user_id BIGINT NOT NULL COMMENT '对接码拥有者用户ID（供应商）',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '绑定时间',
                UNIQUE INDEX uq_user_target (user_id, target_user_id),
                INDEX idx_user_id (user_id),
                INDEX idx_target_user_id (target_user_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='对接码绑定表';
        """,

        # 33. 代理订单表（对接卡券发货记录）
        "xy_agent_orders": """
            CREATE TABLE IF NOT EXISTS xy_agent_orders (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
                user_id BIGINT NOT NULL COMMENT '下单用户ID（发货方）',
                order_no VARCHAR(64) NOT NULL COMMENT '闲鱼订单号',
                item_id VARCHAR(64) NOT NULL COMMENT '商品ID',
                card_id BIGINT NOT NULL COMMENT '使用的卡券ID',
                dock_record_id BIGINT NOT NULL COMMENT '对接记录ID',
                dock_level INT NOT NULL COMMENT '对接层级：1=一级，2=二级',
                sale_price VARCHAR(32) NOT NULL COMMENT '售价（用户卖出的价格）',
                dock_price VARCHAR(32) NOT NULL COMMENT '对接价格（拿货价）',
                card_price VARCHAR(32) DEFAULT NULL COMMENT '卡券成本（货主对接价）',
                level2_cost VARCHAR(32) DEFAULT NULL COMMENT '二级拿货价（一级的sub_dock_price）',
                profit VARCHAR(32) NOT NULL DEFAULT '0.00' COMMENT '利润（售价-对接价）',
                fee_amount VARCHAR(32) DEFAULT NULL COMMENT '手续费金额',
                fee_payer VARCHAR(32) DEFAULT NULL COMMENT '手续费承担方：dealer-分销商，distributor-货主',
                upstream_user_id BIGINT DEFAULT NULL COMMENT '上级用户ID',
                upstream_dock_record_id BIGINT DEFAULT NULL COMMENT '上级对接记录ID',
                owner_user_id BIGINT DEFAULT NULL COMMENT '货主用户ID',
                delivery_content TEXT COMMENT '发货内容',
                buyer_id VARCHAR(64) DEFAULT NULL COMMENT '买家ID',
                status VARCHAR(32) NOT NULL DEFAULT 'delivered' COMMENT '状态：delivered-已发货，settled-已结算，failed-失败',
                settle_remark VARCHAR(500) DEFAULT NULL COMMENT '结算备注',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX idx_user_id (user_id),
                INDEX idx_order_no (order_no),
                INDEX idx_dock_record_id (dock_record_id),
                INDEX idx_upstream_user_id (upstream_user_id),
                INDEX idx_status (status),
                INDEX idx_agent_order_created (created_at),
                INDEX idx_ao_upstream_status (upstream_user_id, status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='代理订单表';
        """,

        # 34. Token缓存表
        "xy_token_cache": """
            CREATE TABLE IF NOT EXISTS xy_token_cache (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
                user_id VARCHAR(128) NOT NULL COMMENT '用户ID（myid）',
                token TEXT NOT NULL COMMENT 'IM Token',
                device_id VARCHAR(128) NOT NULL COMMENT '设备ID',
                expire_at DATETIME NOT NULL COMMENT '过期时间',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                UNIQUE KEY uk_user_id (user_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Token缓存表';
        """,

        # 35. 结算记录表
        "xy_settlement_records": """
            CREATE TABLE IF NOT EXISTS xy_settlement_records (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
                user_id BIGINT NOT NULL COMMENT '用户ID',
                alipay_id VARCHAR(128) NOT NULL COMMENT '支付宝ID',
                amount VARCHAR(32) NOT NULL COMMENT '提现金额',
                status VARCHAR(32) NOT NULL DEFAULT 'pending_review' COMMENT '状态：pending_review-待审核，approved-已通过，rejected-已拒绝，paid-已打款',
                remark TEXT COMMENT '备注',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX idx_user_id (user_id),
                INDEX idx_status (status),
                INDEX idx_created_at (created_at),
                INDEX idx_sr_user_created_id (user_id, created_at, id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='结算记录表';
        """,

        # 36. 激活码生成日志表
        "xy_activation_logs": """
            CREATE TABLE IF NOT EXISTS xy_activation_logs (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
                machine_id VARCHAR(32) NOT NULL COMMENT '机器码',
                code_type VARCHAR(20) NOT NULL COMMENT '类型：generate-获取激活码，renew-续期码',
                generated_code VARCHAR(255) NOT NULL COMMENT '生成的激活码/续期码',
                days INT NOT NULL COMMENT '有效天数',
                ip_address VARCHAR(64) COMMENT '请求IP地址',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间（北京时间）',
                INDEX idx_machine_id (machine_id),
                INDEX idx_code_type (code_type),
                INDEX idx_machine_type_time (machine_id, code_type, created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='激活码生成日志表';
        """,

        # 37. 商品素材库表
        "xy_product_materials": """
            CREATE TABLE IF NOT EXISTS xy_product_materials (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
                user_id BIGINT NOT NULL COMMENT '所属用户ID',
                title VARCHAR(200) NOT NULL COMMENT '商品标题',
                description TEXT NOT NULL COMMENT '商品描述',
                price DECIMAL(12,2) NOT NULL COMMENT '价格',
                original_price DECIMAL(12,2) DEFAULT NULL COMMENT '原价（划线价）',
                category VARCHAR(100) DEFAULT NULL COMMENT '商品分类',
                images JSON DEFAULT NULL COMMENT '图片URL列表（最多9张）',
                delivery_method VARCHAR(20) DEFAULT 'express' COMMENT '发货方式：express-快递, pickup-自提',
                postage DECIMAL(8,2) DEFAULT 0 COMMENT '邮费，0表示包邮',
                address VARCHAR(200) DEFAULT NULL COMMENT '宝贝所在地',
                brand VARCHAR(100) DEFAULT NULL COMMENT '品牌',
                `condition` VARCHAR(20) DEFAULT '全新' COMMENT '成色',
                remark VARCHAR(500) DEFAULT NULL COMMENT '备注（仅内部使用）',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX idx_user_id (user_id),
                INDEX idx_created_at (created_at),
                INDEX idx_pm_user_created (user_id, created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商品素材库表';
        """,

        # 38.1 定时求小红花执行日志表
        "xy_scheduled_red_flower_log": """
            CREATE TABLE IF NOT EXISTS `xy_scheduled_red_flower_log` (
                `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
                `batch_id` VARCHAR(36) NOT NULL COMMENT '批次ID',
                `account_id` VARCHAR(80) NOT NULL COMMENT '账号ID',
                `order_no` VARCHAR(64) NOT NULL COMMENT '订单号',
                `status` VARCHAR(20) NOT NULL COMMENT '状态：success/failed',
                `error_message` VARCHAR(500) DEFAULT NULL COMMENT '错误信息',
                `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                PRIMARY KEY (`id`),
                INDEX `idx_batch_id` (`batch_id`),
                INDEX `idx_account_id` (`account_id`),
                INDEX `idx_created_at` (`created_at`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='定时求小红花执行日志表';
        """,

        # 38.2 账号消息通知关闭执行日志表
        "xy_scheduled_close_notice_log": """
            CREATE TABLE IF NOT EXISTS `xy_scheduled_close_notice_log` (
                `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
                `batch_id` VARCHAR(36) NOT NULL COMMENT '批次ID',
                `account_id` VARCHAR(80) NOT NULL COMMENT '账号ID',
                `status` VARCHAR(20) NOT NULL COMMENT '状态：success/failed',
                `error_message` VARCHAR(500) DEFAULT NULL COMMENT '错误信息',
                `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                PRIMARY KEY (`id`),
                INDEX `idx_batch_id` (`batch_id`),
                INDEX `idx_account_id` (`account_id`),
                INDEX `idx_created_at` (`created_at`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='账号消息通知关闭执行日志表';
        """,

        # 38.3 数据库备份日志表（记录每次数据库备份任务的结果与备份文件信息）
        "xy_db_backup_log": """
            CREATE TABLE IF NOT EXISTS `xy_db_backup_log` (
                `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID',
                `status` VARCHAR(20) NOT NULL COMMENT '状态：success/failed',
                `file_name` VARCHAR(255) DEFAULT NULL COMMENT '备份文件名',
                `file_path` VARCHAR(500) DEFAULT NULL COMMENT '备份文件绝对路径',
                `file_size` BIGINT DEFAULT NULL COMMENT '备份文件大小(字节)',
                `table_count` INT DEFAULT NULL COMMENT '备份的数据表数量',
                `total_rows` BIGINT DEFAULT NULL COMMENT '备份的数据总行数',
                `duration_ms` INT DEFAULT NULL COMMENT '备份耗时(毫秒)',
                `error_message` VARCHAR(1000) DEFAULT NULL COMMENT '错误信息',
                `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                PRIMARY KEY (`id`),
                INDEX `idx_status` (`status`),
                INDEX `idx_created_at` (`created_at`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='数据库备份日志表';
        """,

        "xy_auto_reply_message_logs": """
            CREATE TABLE IF NOT EXISTS xy_auto_reply_message_logs (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
                owner_id BIGINT DEFAULT NULL COMMENT '所属系统用户ID',
                owner_username VARCHAR(120) DEFAULT NULL COMMENT '所属系统用户名',
                account_pk BIGINT DEFAULT NULL COMMENT '账号主键ID',
                account_id VARCHAR(80) NOT NULL COMMENT '闲鱼账号ID',
                account_name VARCHAR(120) DEFAULT NULL COMMENT '闲鱼账号显示名称',
                chat_id VARCHAR(128) NOT NULL COMMENT '聊天会话ID',
                item_id VARCHAR(64) DEFAULT NULL COMMENT '商品ID',
                item_title VARCHAR(255) DEFAULT NULL COMMENT '商品标题',
                order_no VARCHAR(64) DEFAULT NULL COMMENT '订单号（自动发货等场景关联订单）',
                source_message_id VARCHAR(128) DEFAULT NULL COMMENT '源消息ID',
                sender_user_id VARCHAR(64) NOT NULL COMMENT '发送方闲鱼用户ID',
                sender_user_name VARCHAR(120) DEFAULT NULL COMMENT '发送方昵称',
                source_message TEXT COMMENT '收到的消息内容',
                source_message_time DATETIME DEFAULT NULL COMMENT '收到消息时间',
                process_status VARCHAR(20) NOT NULL DEFAULT 'processing' COMMENT '处理状态：processing/success/skipped/failed',
                decision_reason VARCHAR(64) NOT NULL DEFAULT 'processing' COMMENT '决策原因',
                reply_strategy VARCHAR(20) NOT NULL DEFAULT 'none' COMMENT '回复策略：keyword/ai/default/none',
                reply_mode VARCHAR(20) NOT NULL DEFAULT 'none' COMMENT '回复模式：text/image/text_image/none',
                matched_keyword VARCHAR(255) DEFAULT NULL COMMENT '命中的关键词',
                matched_rule_type VARCHAR(32) DEFAULT NULL COMMENT '命中的规则类型',
                default_reply_scope VARCHAR(20) DEFAULT NULL COMMENT '默认回复作用域：item/account',
                default_reply_once TINYINT(1) NOT NULL DEFAULT 0 COMMENT '默认回复是否仅回复一次',
                ai_model_name VARCHAR(120) DEFAULT NULL COMMENT 'AI模型名称',
                ai_provider_name VARCHAR(80) DEFAULT NULL COMMENT 'AI服务商名称',
                reply_text TEXT COMMENT '回复文本内容',
                reply_image_url VARCHAR(1000) DEFAULT NULL COMMENT '回复图片URL',
                reply_segments JSON DEFAULT NULL COMMENT '拆分后的回复分段',
                error_message TEXT COMMENT '错误信息',
                send_status VARCHAR(20) NOT NULL DEFAULT 'unknown' COMMENT '发送状态：success-发送成功/failed-发送失败/unknown-未知(无响应)/timeout-超时(无响应超过阈值)',
                send_fail_reason TEXT COMMENT '发送失败原因（如被安全拦截的明文文案）',
                raw_message_json JSON DEFAULT NULL COMMENT '原始消息JSON',
                context_snapshot JSON DEFAULT NULL COMMENT '上下文快照',
                send_result_json JSON DEFAULT NULL COMMENT '发送结果快照',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX idx_owner_id (owner_id),
                INDEX idx_account_pk (account_pk),
                INDEX idx_account_id (account_id),
                INDEX idx_chat_id (chat_id),
                INDEX idx_item_id (item_id),
                INDEX idx_order_no (order_no),
                INDEX idx_source_message_id (source_message_id),
                INDEX idx_sender_user_id (sender_user_id),
                INDEX idx_process_status (process_status),
                INDEX idx_decision_reason (decision_reason),
                INDEX idx_created_at (created_at),
                INDEX idx_arml_account_created (account_id, created_at),
                INDEX idx_arml_account_status_created (account_id, process_status, created_at),
                INDEX idx_arml_owner_created (owner_id, created_at),
                INDEX idx_arml_owner_status_created (owner_id, process_status, created_at),
                INDEX idx_arml_status_created (process_status, created_at),
                INDEX idx_arml_status_strategy_created (process_status, reply_strategy, created_at),
                INDEX idx_arml_strategy_created (reply_strategy, created_at),
                INDEX idx_arml_order_strategy_id (order_no, reply_strategy, id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='自动回复消息日志表';
        """,

        "xy_publish_addresses": """
            CREATE TABLE IF NOT EXISTS xy_publish_addresses (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
                name VARCHAR(120) NOT NULL COMMENT '地址名称',
                search_keyword VARCHAR(200) NOT NULL COMMENT '地址搜索关键词',
                expected_text VARCHAR(200) DEFAULT NULL COMMENT '期望命中的候选文本',
                account_id VARCHAR(80) DEFAULT NULL COMMENT '限定使用的闲鱼账号ID，空表示全局通用',
                weight INT NOT NULL DEFAULT 1 COMMENT '随机权重',
                sort_order INT NOT NULL DEFAULT 100 COMMENT '排序值',
                is_enabled TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
                use_count INT NOT NULL DEFAULT 0 COMMENT '使用次数',
                last_used_at DATETIME DEFAULT NULL COMMENT '最后使用时间',
                created_by BIGINT DEFAULT NULL COMMENT '创建人用户ID',
                remark VARCHAR(500) DEFAULT NULL COMMENT '备注',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX idx_account_id (account_id),
                INDEX idx_pa_enabled_account (is_enabled, account_id),
                INDEX idx_pa_sort_created (sort_order, created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商品发布随机地址池表';
        """,

        "xy_user_publish_addresses": """
            CREATE TABLE IF NOT EXISTS xy_user_publish_addresses (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
                owner_id BIGINT NOT NULL COMMENT '归属用户ID',
                address VARCHAR(200) NOT NULL COMMENT '地址文本（去重键）',
                is_deleted TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已删除（软删除）',
                use_count INT NOT NULL DEFAULT 0 COMMENT '使用次数',
                last_used_at DATETIME DEFAULT NULL COMMENT '最后使用时间',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX idx_upa_owner_deleted (owner_id, is_deleted),
                INDEX idx_upa_owner_addr (owner_id, address)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='个人发布地址库表';
        """,

        # 38. 商品发布日志表
        "xy_publish_logs": """
            CREATE TABLE IF NOT EXISTS xy_publish_logs (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
                user_id BIGINT NOT NULL COMMENT '操作用户ID',
                account_id VARCHAR(80) NOT NULL COMMENT '闲鱼账号ID（cookie_id）',
                title VARCHAR(200) NOT NULL COMMENT '商品标题',
                description TEXT DEFAULT NULL COMMENT '商品描述',
                price VARCHAR(20) DEFAULT NULL COMMENT '发布价格',
                material_id BIGINT DEFAULT NULL COMMENT '关联的素材ID（批量发布时使用）',
                batch_id VARCHAR(36) DEFAULT NULL COMMENT '批次ID（批量发布任务标识）',
                status VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT '状态：pending/publishing/success/failed',
                item_url VARCHAR(500) DEFAULT NULL COMMENT '发布成功后的商品链接',
                item_id VARCHAR(64) DEFAULT NULL COMMENT '发布成功后的商品ID',
                error_message VARCHAR(1000) DEFAULT NULL COMMENT '失败原因',
                resolved_address_id BIGINT DEFAULT NULL COMMENT '本次发布命中的地址池ID',
                resolved_address_text VARCHAR(200) DEFAULT NULL COMMENT '本次发布实际使用的地址搜索词',
                address_source VARCHAR(20) DEFAULT NULL COMMENT '地址来源：material/account_pool/global_pool',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX idx_user_id (user_id),
                INDEX idx_account_id (account_id),
                INDEX idx_batch_id (batch_id),
                INDEX idx_status (status),
                INDEX idx_created_at (created_at),
                INDEX idx_publish_user_created (user_id, created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商品发布日志表';
        """,

        # 45.1 商品上新监控任务表
        # 45.1 商品监控分类表
        "xy_listing_monitor_categories": """
            CREATE TABLE IF NOT EXISTS xy_listing_monitor_categories (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
                owner_id BIGINT NOT NULL COMMENT '归属用户ID',
                name VARCHAR(100) NOT NULL COMMENT '分类名称',
                is_deleted TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已删除（软删除）',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX idx_lmc_owner (owner_id),
                INDEX idx_lmc_owner_deleted (owner_id, is_deleted)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商品监控分类表';
        """,

        # 45.2 商品监控任务表
        "xy_listing_monitor_tasks": """
            CREATE TABLE IF NOT EXISTS xy_listing_monitor_tasks (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
                owner_id BIGINT DEFAULT NULL COMMENT '归属用户ID，用于多用户数据隔离',
                category_id BIGINT DEFAULT NULL COMMENT '所属分类ID（NULL=未分类）',
                monitor_type VARCHAR(20) NOT NULL DEFAULT 'listing' COMMENT '监控类型：listing-上新监控，price_drop-降价监控',
                keyword VARCHAR(200) NOT NULL COMMENT '商品监控关键字',
                price_min DECIMAL(12,2) DEFAULT NULL COMMENT '商品价格区间最低值',
                price_max DECIMAL(12,2) DEFAULT NULL COMMENT '商品价格区间最高值',
                publish_days INT DEFAULT NULL COMMENT '上新天数筛选（searchFilter 的 publishDays，单位天，NULL/0=不限）',
                interval_minutes INT NOT NULL DEFAULT 5 COMMENT '任务执行间隔（分钟）',
                collect_pages INT NOT NULL DEFAULT 1 COMMENT '每次采集页数',
                proxy_url VARCHAR(255) DEFAULT NULL COMMENT '代理API地址（GET返回IP:PORT列表，取一个作HTTP代理；空=不使用代理）',
                account_ids JSON DEFAULT NULL COMMENT '关联的闲鱼账号ID列表（JSON数组）',
                order_account_ids JSON DEFAULT NULL COMMENT '下单账号ID列表（多选，私信与下单共用）',
                dm_content VARCHAR(1000) DEFAULT NULL COMMENT '私信内容（配置下单账号后必填）',
                dm_batch_size INT NOT NULL DEFAULT 5 COMMENT '每次定时私信任务最多处理条数',
                order_batch_size INT NOT NULL DEFAULT 5 COMMENT '每次定时下单任务最多处理条数',
                direct_order TINYINT(1) NOT NULL DEFAULT 0 COMMENT '采集后是否直接下单（开启则新采集商品立即用下单账号下单后再入库）',
                is_enabled TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用监控任务',
                is_deleted TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已删除（软删除）',
                last_run_at DATETIME DEFAULT NULL COMMENT '最近一次执行时间',
                created_by BIGINT DEFAULT NULL COMMENT '创建人用户ID',
                remark VARCHAR(500) DEFAULT NULL COMMENT '备注',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX idx_lmt_owner_enabled (owner_id, is_enabled),
                INDEX idx_lmt_owner_deleted (owner_id, is_deleted),
                INDEX idx_lmt_created_at (created_at),
                INDEX idx_lmt_category (category_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商品上新监控任务表';
        """,

        # 45.3 商品监控采集商品信息表
        "xy_listing_monitor_items": """
            CREATE TABLE IF NOT EXISTS xy_listing_monitor_items (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
                monitor_task_id BIGINT NOT NULL COMMENT '关联的商品监控任务ID',
                owner_id BIGINT DEFAULT NULL COMMENT '归属用户ID',
                item_id VARCHAR(64) NOT NULL COMMENT '闲鱼商品ID',
                title VARCHAR(500) DEFAULT NULL COMMENT '商品标题',
                price VARCHAR(32) DEFAULT NULL COMMENT '商品价格（展示文本）',
                area VARCHAR(120) DEFAULT NULL COMMENT '商品所在地区',
                pic_url VARCHAR(1000) DEFAULT NULL COMMENT '商品主图URL',
                seller_id VARCHAR(120) DEFAULT NULL COMMENT '卖家ID（搜索返回，可能为加密串）',
                seller_user_id VARCHAR(64) DEFAULT NULL COMMENT '卖家真实用户ID（商品详情接口补全）',
                seller_nick VARCHAR(120) DEFAULT NULL COMMENT '卖家昵称',
                seller_avatar VARCHAR(1000) DEFAULT NULL COMMENT '卖家头像URL',
                want_count VARCHAR(32) DEFAULT NULL COMMENT '想要数（从营销标签解析的真实想要人数）',
                tags VARCHAR(500) DEFAULT NULL COMMENT '商品营销标签（逗号分隔，如：4天内上新,235人想要）',
                publish_time DATETIME DEFAULT NULL COMMENT '商品发布时间',
                target_url VARCHAR(1000) DEFAULT NULL COMMENT '商品详情跳转URL',
                raw_json TEXT DEFAULT NULL COMMENT '商品原始数据（搜索结果项JSON，兜底）',
                detail_json MEDIUMTEXT DEFAULT NULL COMMENT '商品详情数据（详情接口返回JSON）',
                seller_fill_status VARCHAR(20) DEFAULT NULL COMMENT '卖家ID补全结果：failed-明确失败不再补全（如跨境商品/已下架）',
                seller_fill_fail_reason VARCHAR(500) DEFAULT NULL COMMENT '卖家ID补全失败原因（明确业务失败的原文）',
                is_dm_sent TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已发起私信（已处理，避免重复发送）',
                dm_account_id VARCHAR(80) DEFAULT NULL COMMENT '成功私信使用的账号ID（后续优先用该账号下单）',
                dm_chat_id VARCHAR(80) DEFAULT NULL COMMENT '私信会话ID（create-chat 返回的 chat_id）',
                dm_status VARCHAR(20) DEFAULT NULL COMMENT '私信发送结果：success/failed/unknown',
                dm_fail_reason VARCHAR(500) DEFAULT NULL COMMENT '私信发送失败原因',
                dm_attempts INT NOT NULL DEFAULT 0 COMMENT '私信发送尝试次数（失败重试用）',
                is_ordered TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已下单成功',
                order_id VARCHAR(64) DEFAULT NULL COMMENT '下单成功的订单ID（拍下）',
                order_account_id VARCHAR(80) DEFAULT NULL COMMENT '下单成功使用的账号ID（发起私信时严格使用该账号）',
                order_status VARCHAR(20) DEFAULT NULL COMMENT '下单结果：success/failed/duplicate',
                order_fail_reason VARCHAR(500) DEFAULT NULL COMMENT '下单失败原因',
                order_attempts INT NOT NULL DEFAULT 0 COMMENT '下单尝试次数（失败重试用）',
                dm_sent_at DATETIME DEFAULT NULL COMMENT '实际私信成功/发起时间（用于按日统计私信数）',
                ordered_at DATETIME DEFAULT NULL COMMENT '下单成功时间（用于按日统计下单数）',
                last_seen_at DATETIME DEFAULT NULL COMMENT '最近一次采集到的时间',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                UNIQUE KEY uk_lmi_task_item (monitor_task_id, item_id),
                INDEX idx_lmi_task (monitor_task_id),
                INDEX idx_lmi_owner (owner_id),
                INDEX idx_lmi_publish_time (publish_time),
                INDEX idx_lmi_created (created_at),
                INDEX idx_lmi_dm_send (order_status, is_dm_sent, ordered_at),
                INDEX idx_lmi_order_pending (is_ordered, order_attempts),
                INDEX idx_lmi_item_ordered (item_id, is_ordered),
                INDEX idx_lmi_owner_publish (owner_id, publish_time)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商品监控采集商品信息表';
        """,

        # 45.3 商品监控执行日志表
        "xy_listing_monitor_logs": """
            CREATE TABLE IF NOT EXISTS xy_listing_monitor_logs (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
                monitor_task_id BIGINT NOT NULL COMMENT '关联的商品监控任务ID',
                owner_id BIGINT DEFAULT NULL COMMENT '归属用户ID',
                monitor_type VARCHAR(20) DEFAULT NULL COMMENT '监控类型：listing-上新监控，price_drop-降价监控',
                keyword VARCHAR(200) DEFAULT NULL COMMENT '监控关键字',
                trigger_type VARCHAR(10) NOT NULL DEFAULT 'auto' COMMENT '触发方式：auto-定时自动，manual-手动',
                account_id VARCHAR(80) DEFAULT NULL COMMENT '本次实际使用的主账号ID',
                used_account_ids JSON DEFAULT NULL COMMENT '本次执行实际使用过的账号ID列表（可能多个）',
                pages INT NOT NULL DEFAULT 0 COMMENT '本次采集页数',
                fetched_count INT NOT NULL DEFAULT 0 COMMENT '本次获取的商品数',
                inserted_count INT NOT NULL DEFAULT 0 COMMENT '本次新增的商品数',
                updated_count INT NOT NULL DEFAULT 0 COMMENT '本次更新的商品数',
                status VARCHAR(20) NOT NULL DEFAULT 'success' COMMENT '执行状态：success/failed/partial',
                message VARCHAR(1000) DEFAULT NULL COMMENT '执行结果说明',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX idx_lml_task (monitor_task_id),
                INDEX idx_lml_owner (owner_id),
                INDEX idx_lml_created_at (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商品监控执行日志表';
        """,

        # 45.6 用户级兜底下单账号配置表（任务无可用下单账号时回退使用）
        "xy_order_fallback_accounts": """
            CREATE TABLE IF NOT EXISTS xy_order_fallback_accounts (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
                owner_id BIGINT NOT NULL COMMENT '归属用户ID',
                category_id BIGINT DEFAULT NULL COMMENT '所属分类ID（NULL=未分类全局兜底）',
                account_ids JSON DEFAULT NULL COMMENT '兜底下单账号ID列表（JSON数组，多选轮换使用）',
                is_deleted TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已删除（软删除）',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                UNIQUE KEY uk_ofa_owner_category (owner_id, category_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户级兜底下单账号配置表（按分类配置）';
        """,

        # 45.7 用户级兜底采集账号配置表（任务无可用采集账号时回退使用）
        "xy_collect_fallback_accounts": """
            CREATE TABLE IF NOT EXISTS xy_collect_fallback_accounts (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
                owner_id BIGINT NOT NULL COMMENT '归属用户ID',
                category_id BIGINT DEFAULT NULL COMMENT '所属分类ID（NULL=未分类全局兜底）',
                account_ids JSON DEFAULT NULL COMMENT '兜底采集账号ID列表（JSON数组，多选轮换使用）',
                is_deleted TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已删除（软删除）',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                UNIQUE KEY uk_cfa_owner_category (owner_id, category_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户级兜底采集账号配置表（按分类配置）';
        """,

        # 46. 共享扫码登录会话表
        "xy_shared_scan_sessions": """
            CREATE TABLE IF NOT EXISTS xy_shared_scan_sessions (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
                session_id VARCHAR(36) NOT NULL UNIQUE COMMENT '会话唯一ID（UUID）',
                owner_id BIGINT NOT NULL COMMENT '创建者用户ID',
                owner_username VARCHAR(120) NOT NULL COMMENT '创建者用户名',
                status VARCHAR(20) NOT NULL DEFAULT 'active' COMMENT '会话状态：active/closed',
                expires_at DATETIME NOT NULL COMMENT '过期时间（默认72小时）',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX idx_session_id (session_id),
                INDEX idx_owner_id (owner_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='共享扫码登录会话表';
        """,

        # 48. 禁止发货规则配置表
        "xy_delivery_block_rules": """
            CREATE TABLE IF NOT EXISTS xy_delivery_block_rules (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
                account_id VARCHAR(64) NOT NULL COMMENT '账号ID',
                rule_code VARCHAR(50) NOT NULL COMMENT '规则编码',
                enabled TINYINT(1) NOT NULL DEFAULT 0 COMMENT '规则开关',
                priority INT NOT NULL DEFAULT 0 COMMENT '执行优先级（越小越先执行）',
                block_reason VARCHAR(500) DEFAULT NULL COMMENT '禁止发货原因（发给买家的消息）',
                auto_close_order TINYINT(1) NOT NULL DEFAULT 0 COMMENT '命中后主动关闭订单',
                only_card_after_close TINYINT(1) NOT NULL DEFAULT 0 COMMENT '关闭订单后继续发货（只发卡券）',
                excluded_item_ids JSON DEFAULT NULL COMMENT '该规则的排除商品列表（命中则跳过本规则）',
                config JSON DEFAULT NULL COMMENT '规则专属参数',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX idx_account_id (account_id),
                UNIQUE KEY uk_account_rule (account_id, rule_code)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='禁止发货规则配置表';
        """,

        # 47. 共享扫码登录兼职工作者表
        "xy_shared_scan_workers": """
            CREATE TABLE IF NOT EXISTS xy_shared_scan_workers (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
                shared_session_id VARCHAR(36) NOT NULL COMMENT '关联的共享会话ID',
                sub_session_id VARCHAR(36) NOT NULL UNIQUE COMMENT '兼职子会话唯一ID（UUID）',
                xianyu_session_id VARCHAR(36) DEFAULT NULL COMMENT '关联的闲鱼QR登录会话ID',
                status VARCHAR(20) NOT NULL DEFAULT 'qrcode_ready' COMMENT '状态：qrcode_ready/scanning/success/failed',
                qr_code_url LONGTEXT DEFAULT NULL COMMENT '二维码图片base64 data URL',
                account_id VARCHAR(80) DEFAULT NULL COMMENT '扫码成功后的闲鱼账号ID（unb）',
                cookie_saved TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'Cookie是否已保存到账号表',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX idx_shared_session_id (shared_session_id),
                INDEX idx_sub_session_id (sub_session_id),
                INDEX idx_account_id (account_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='共享扫码登录兼职工作者表';
        """,

        # 49. 个人黑名单表
        "xy_personal_blacklist": """
            CREATE TABLE IF NOT EXISTS xy_personal_blacklist (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
                owner_id BIGINT NOT NULL COMMENT '用户ID',
                account_id VARCHAR(64) DEFAULT NULL COMMENT '账号ID',
                buyer_id VARCHAR(64) NOT NULL COMMENT '买家ID',
                buyer_nick VARCHAR(120) DEFAULT NULL COMMENT '买家昵称',
                item_id VARCHAR(64) DEFAULT NULL COMMENT '商品ID',
                reason VARCHAR(500) DEFAULT NULL COMMENT '拉黑原因',
                is_enabled TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX idx_pb_owner_id (owner_id),
                INDEX idx_pb_owner_buyer (owner_id, buyer_id),
                INDEX idx_pb_owner_account (owner_id, account_id),
                INDEX idx_pb_owner_created (owner_id, created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='个人黑名单表';
        """,

        # 50. 闲鱼黑名单表
        "xy_platform_blacklist": """
            CREATE TABLE IF NOT EXISTS xy_platform_blacklist (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
                owner_id BIGINT NOT NULL COMMENT '拉黑用户（本系统用户ID）',
                buyer_id VARCHAR(64) NOT NULL COMMENT '买家ID',
                buyer_nick VARCHAR(120) DEFAULT NULL COMMENT '买家昵称',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX idx_plb_owner_id (owner_id),
                INDEX idx_plb_owner_buyer (owner_id, buyer_id),
                INDEX idx_plb_created (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='闲鱼黑名单表';
        """,

        # 51. 在线聊天快捷短语表
        "xy_chat_quick_phrases": """
            CREATE TABLE IF NOT EXISTS xy_chat_quick_phrases (
                id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
                owner_id BIGINT NOT NULL COMMENT '归属用户（本系统用户ID）',
                title VARCHAR(80) NOT NULL COMMENT '短语标题',
                content TEXT NOT NULL COMMENT '短语内容（发送的文本）',
                sort_order INT NOT NULL DEFAULT 0 COMMENT '排序值，越小越靠前',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                INDEX ix_xy_chat_quick_phrases_owner_id (owner_id),
                INDEX idx_chat_quick_phrase_owner_sort (owner_id, sort_order)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='在线聊天快捷短语';
        """,
    }
    
    # 字段迁移定义：表名 -> [(字段名, 字段定义, 在哪个字段后面)]
    COLUMN_MIGRATIONS = {
        "xy_listing_monitor_tasks": [
            ("monitor_type", "VARCHAR(20) NOT NULL DEFAULT 'listing' COMMENT '监控类型：listing-上新监控，price_drop-降价监控'", "owner_id"),
            ("category_id", "BIGINT DEFAULT NULL COMMENT '所属分类ID（NULL=未分类）'", "owner_id"),
            ("collect_pages", "INT NOT NULL DEFAULT 1 COMMENT '每次采集页数'", "interval_minutes"),
            ("dm_content", "VARCHAR(1000) DEFAULT NULL COMMENT '私信内容（配置下单账号后必填）'", "account_ids"),
            ("order_account_ids", "JSON DEFAULT NULL COMMENT '下单账号ID列表（多选，私信与下单共用）'", "account_ids"),
            ("dm_batch_size", "INT NOT NULL DEFAULT 5 COMMENT '每次定时私信任务最多处理条数'", "dm_content"),
            ("order_batch_size", "INT NOT NULL DEFAULT 5 COMMENT '每次定时下单任务最多处理条数'", "dm_batch_size"),
            ("publish_days", "INT DEFAULT NULL COMMENT '上新天数筛选（searchFilter 的 publishDays，单位天，NULL/0=不限）'", "price_max"),
            ("proxy_url", "VARCHAR(255) DEFAULT NULL COMMENT '代理API地址（GET返回IP:PORT列表，取一个作HTTP代理；空=不使用代理）'", "collect_pages"),
            ("direct_order", "TINYINT(1) NOT NULL DEFAULT 0 COMMENT '采集后是否直接下单（开启则新采集商品立即用下单账号下单后再入库）'", "order_batch_size"),
        ],
        "xy_listing_monitor_logs": [
            ("used_account_ids", "JSON DEFAULT NULL COMMENT '本次执行实际使用过的账号ID列表（可能多个）'", "account_id"),
            ("trigger_type", "VARCHAR(10) NOT NULL DEFAULT 'auto' COMMENT '触发方式：auto-定时自动，manual-手动'", "keyword"),
        ],
        "xy_listing_monitor_items": [
            ("is_dm_sent", "TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已私信'", "raw_json"),
            ("is_ordered", "TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已下单'", "is_dm_sent"),
            ("seller_user_id", "VARCHAR(64) DEFAULT NULL COMMENT '卖家真实用户ID（商品详情接口补全）'", "seller_id"),
            ("detail_json", "MEDIUMTEXT DEFAULT NULL COMMENT '商品详情数据（详情接口返回JSON）'", "raw_json"),
            ("order_id", "VARCHAR(64) DEFAULT NULL COMMENT '下单成功的订单ID（拍下）'", "is_ordered"),
            ("order_account_id", "VARCHAR(80) DEFAULT NULL COMMENT '下单成功使用的账号ID（发起私信时严格使用该账号）'", "order_id"),
            ("dm_status", "VARCHAR(20) DEFAULT NULL COMMENT '私信发送结果：success/failed/unknown'", "is_dm_sent"),
            ("dm_fail_reason", "VARCHAR(500) DEFAULT NULL COMMENT '私信发送失败原因'", "dm_status"),
            ("dm_attempts", "INT NOT NULL DEFAULT 0 COMMENT '私信发送尝试次数（失败重试用）'", "dm_fail_reason"),
            ("order_status", "VARCHAR(20) DEFAULT NULL COMMENT '下单结果：success/failed/duplicate'", "order_id"),
            ("order_fail_reason", "VARCHAR(500) DEFAULT NULL COMMENT '下单失败原因'", "order_status"),
            ("order_attempts", "INT NOT NULL DEFAULT 0 COMMENT '下单尝试次数（失败重试用）'", "order_fail_reason"),
            ("dm_sent_at", "DATETIME DEFAULT NULL COMMENT '实际私信成功/发起时间（用于按日统计私信数）'", "dm_attempts"),
            ("ordered_at", "DATETIME DEFAULT NULL COMMENT '下单成功时间（用于按日统计下单数）'", "order_attempts"),
            ("dm_account_id", "VARCHAR(80) DEFAULT NULL COMMENT '成功私信使用的账号ID（后续优先用该账号下单）'", "is_dm_sent"),
            ("dm_chat_id", "VARCHAR(80) DEFAULT NULL COMMENT '私信会话ID（create-chat 返回的 chat_id）'", "dm_account_id"),
            ("seller_fill_status", "VARCHAR(20) DEFAULT NULL COMMENT '卖家ID补全结果：failed-明确失败不再补全（如跨境商品/已下架）'", "detail_json"),
            ("seller_fill_fail_reason", "VARCHAR(500) DEFAULT NULL COMMENT '卖家ID补全失败原因（明确业务失败的原文）'", "seller_fill_status"),
            ("seller_avatar", "VARCHAR(1000) DEFAULT NULL COMMENT '卖家头像URL'", "seller_nick"),
            ("tags", "VARCHAR(500) DEFAULT NULL COMMENT '商品营销标签（逗号分隔，如：4天内上新,235人想要）'", "want_count"),
        ],
        "xy_order_fallback_accounts": [
            ("category_id", "BIGINT DEFAULT NULL COMMENT '所属分类ID（NULL=未分类全局兜底）'", "owner_id"),
            ("is_deleted", "TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已删除（软删除）'", "account_ids"),
        ],
        "xy_collect_fallback_accounts": [
            ("category_id", "BIGINT DEFAULT NULL COMMENT '所属分类ID（NULL=未分类全局兜底）'", "owner_id"),
            ("is_deleted", "TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已删除（软删除）'", "account_ids"),
        ],
        "xy_auto_reply_message_logs": [
            ("send_status", "VARCHAR(20) NOT NULL DEFAULT 'unknown' COMMENT '发送状态：success-发送成功/failed-发送失败/unknown-未知(无响应)/timeout-超时(无响应超过阈值)'", "error_message"),
            ("send_fail_reason", "TEXT COMMENT '发送失败原因（如被安全拦截的明文文案）'", "send_status"),
            ("order_no", "VARCHAR(64) DEFAULT NULL COMMENT '订单号（自动发货等场景关联订单）'", "item_title"),
        ],
        "xy_risk_control_logs": [
            ("captcha_engine", "VARCHAR(32) DEFAULT NULL COMMENT '验证通过引擎：playwright-主引擎/drissionpage-兜底引擎/real_mouse-真人鼠标引擎'", "processing_status"),
            ("call_type", "VARCHAR(16) DEFAULT 'local' COMMENT '调用类型：local-本机/remote-远程(外部凭秘钥调用)'", "captcha_engine"),
            ("call_user", "VARCHAR(128) DEFAULT NULL COMMENT '调用用户：仅远程调用记录(按秘钥查到的用户名)'", "call_type"),
        ],
        "xy_accounts": [
            ("proxy_type", "VARCHAR(20) DEFAULT 'none' COMMENT '代理类型'", "last_refresh_at"),
            ("proxy_host", "VARCHAR(255) COMMENT '代理主机'", "proxy_type"),
            ("proxy_port", "INT COMMENT '代理端口'", "proxy_host"),
            ("proxy_user", "VARCHAR(120) COMMENT '代理用户名'", "proxy_port"),
            ("proxy_pass", "VARCHAR(255) COMMENT '代理密码'", "proxy_user"),
            ("message_expire_time", "INT DEFAULT 3600 COMMENT '相同消息等待时间(秒)'", "proxy_pass"),
            ("reply_delay_seconds", "INT DEFAULT 0 COMMENT '自动回复延迟时间(秒)，0表示立即回复'", "message_expire_time"),
            ("disable_reason", "VARCHAR(255) COMMENT '禁用原因'", "message_expire_time"),
            ("scheduled_redelivery", "TINYINT(1) NOT NULL DEFAULT 0 COMMENT '定时补发货开关'", "disable_reason"),
            ("scheduled_rate", "TINYINT(1) NOT NULL DEFAULT 0 COMMENT '定时补评价开关'", "scheduled_redelivery"),
            ("auto_polish", "TINYINT(1) NOT NULL DEFAULT 0 COMMENT '商品自动擦亮开关'", "scheduled_rate"),
            ("confirm_before_send", "TINYINT(1) NOT NULL DEFAULT 0 COMMENT '发货成功再发卡券开关'", "auto_polish"),
            ("send_before_confirm", "TINYINT(1) NOT NULL DEFAULT 0 COMMENT '卡券发送成功再确认发货开关'", "confirm_before_send"),
            ("auto_red_flower", "TINYINT(1) NOT NULL DEFAULT 0 COMMENT '自动求小红花开关'", "send_before_confirm"),
            ("delivery_disabled", "TINYINT(1) NOT NULL DEFAULT 0 COMMENT '禁止发货开关'", "auto_red_flower"),
            ("delivery_disabled_reason", "VARCHAR(500) DEFAULT NULL COMMENT '禁止发货原因'", "delivery_disabled"),
            ("auto_close_order", "TINYINT(1) NOT NULL DEFAULT 0 COMMENT '主动关闭订单开关'", "delivery_disabled_reason"),
            ("delivery_only_card_after_close", "TINYINT(1) NOT NULL DEFAULT 0 COMMENT '关闭订单后继续发货（只发卡券）'", "auto_close_order"),
            ("delivery_disabled_excluded_items", "JSON DEFAULT NULL COMMENT '禁止发货排除商品列表（item_id 数组，命中后按正常流程发货）'", "delivery_only_card_after_close"),
            ("ai_reply_block_ordered_users", "TINYINT(1) NOT NULL DEFAULT 0 COMMENT '已下单用户禁止AI回复'", "delivery_disabled_excluded_items"),
            ("refund_cancel_enabled", "TINYINT(1) NOT NULL DEFAULT 0 COMMENT '退款订单注销开关'", "ai_reply_block_ordered_users"),
            ("refund_cancel_url", "VARCHAR(255) DEFAULT NULL COMMENT '退款订单注销请求URL'", "refund_cancel_enabled"),
            ("refund_cancel_timeout", "INT DEFAULT 60 COMMENT '退款订单注销超时时间(秒)'", "refund_cancel_url"),
        ],
        "xy_orders": [
            ("is_bargain", "TINYINT(1) DEFAULT 0 COMMENT '是否小刀'", "account_name"),
            ("chat_id", "VARCHAR(64) COMMENT '聊天会话ID'", "buyer_id"),
            ("buyer_fish_nick", "VARCHAR(120) COMMENT '买家闲鱼昵称（明文）'", "buyer_nick"),
            ("receiver_name", "VARCHAR(120) COMMENT '收货人姓名'", "is_bargain"),
            ("receiver_phone", "VARCHAR(32) COMMENT '收货人手机号'", "receiver_name"),
            ("receiver_address", "VARCHAR(512) COMMENT '收货地址'", "receiver_phone"),
            ("is_rated", "TINYINT(1) DEFAULT 0 COMMENT '是否已评价'", "receiver_address"),
            ("delivery_method", "VARCHAR(32) COMMENT '发货方式'", "is_rated"),
            ("delivery_content", "VARCHAR(2000) COMMENT '发货内容'", "delivery_method"),
            ("delivery_fail_reason", "VARCHAR(2000) COMMENT '发货失败原因'", "delivery_content"),
            ("source", "VARCHAR(32) COMMENT '数据来源：fetch_xianyu-获取闲鱼订单按钮'", "metadata"),
            ("is_red_flower", "TINYINT(1) DEFAULT 0 COMMENT '是否已求小红花'", "is_rated"),
            ("is_unregistered", "TINYINT(1) DEFAULT 0 COMMENT '是否已请求注销接口'", "is_red_flower"),
            ("unregister_error_reason", "VARCHAR(500) DEFAULT NULL COMMENT '注销接口错误原因'", "is_unregistered"),
        ],
        "xy_cards": [
            ("delivery_count", "INT DEFAULT 0 COMMENT '发货次数'", "delay_seconds"),
            ("price", "VARCHAR(32) COMMENT '对接价格'", "delivery_count"),
            ("is_dockable", "TINYINT(1) DEFAULT 0 COMMENT '是否可对接'", "price"),
            ("image_urls", "TEXT COMMENT '多图片URL列表(JSON数组，最多3张)'", "image_url"),
            ("fee_payer", "VARCHAR(32) COMMENT '手续费支付方式：distributor-分销主支付，dealer-分销商支付'", "is_dockable"),
            ("min_price", "VARCHAR(32) COMMENT '最低售价'", "fee_payer"),
            ("dock_visibility", "VARCHAR(32) DEFAULT NULL COMMENT '对接可见性：public-所有人可见，dealer_only-仅分销商可见'", "min_price"),
        ],
        "xy_dock_records": [
            ("delivery_count", "INT NOT NULL DEFAULT 0 COMMENT '发货次数'", "remark"),
            ("disable_reason", "VARCHAR(255) DEFAULT NULL COMMENT '禁用原因'", "status"),
            ("owner_disabled", "TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否被上级禁用锁定：1是 0否'", "disable_reason"),
            ("level", "INT NOT NULL DEFAULT 1 COMMENT '分销层级：1=一级分销，2=二级分销'", "disable_reason"),
            ("parent_dock_id", "BIGINT DEFAULT NULL COMMENT '上级对接记录ID，一级分销为NULL'", "level"),
            ("source_user_id", "BIGINT DEFAULT NULL COMMENT '上级分销商用户ID，一级分销为NULL'", "parent_dock_id"),
            ("allow_sub_dock", "TINYINT(1) DEFAULT 0 COMMENT '是否允许下级对接'", "source_user_id"),
            ("sub_dock_price", "VARCHAR(32) DEFAULT NULL COMMENT '给下级的对接价格（一级分销商设定）'", "allow_sub_dock"),
            ("sub_dock_visibility", "VARCHAR(32) DEFAULT NULL COMMENT '下级对接可见性：public-所有人可见，dealer_only-仅绑定对接码的分销商可见'", "sub_dock_price"),
        ],
        "xy_users": [
            ("account_limit", "INT DEFAULT NULL COMMENT '可添加账号数量'", "role"),
            ("login_fail_count", "INT DEFAULT 0 COMMENT '登录失败次数'", "last_login_at"),
            ("login_locked_until", "DATETIME COMMENT '登录锁定截止时间'", "login_fail_count"),
            ("dock_code", "VARCHAR(32) DEFAULT NULL UNIQUE COMMENT '对接码，用于分销商识别'", "login_locked_until"),
            ("secret_key", "VARCHAR(64) DEFAULT NULL UNIQUE COMMENT '分销秘钥，32位随机字符，全局唯一'", "dock_code"),
            ("expire_at", "DATETIME DEFAULT NULL COMMENT '账号到期日（精确到秒，NULL=永不过期）'", "secret_key"),
        ],
        "xy_default_replies": [
            ("item_id", "VARCHAR(64) DEFAULT NULL COMMENT '商品ID'", "account_id"),
            ("reply_image", "VARCHAR(512) COMMENT '回复图片URL'", "reply_content"),
            ("reply_type", "VARCHAR(16) DEFAULT 'text' COMMENT '回复类型：text-文本(可附带图片)，api-接口'", "enabled"),
            ("api_url", "VARCHAR(1024) DEFAULT NULL COMMENT 'API地址(reply_type=api时POST此地址)'", "reply_image"),
            ("api_timeout", "INT DEFAULT 80 COMMENT 'API请求超时时间(秒)'", "api_url"),
        ],
        "xy_default_reply_records": [
            ("item_id", "VARCHAR(64) DEFAULT NULL COMMENT '商品ID'", "account_id"),
        ],
        "xy_catalog_items": [
            ("ai_prompt", "TEXT COMMENT '商品AI提示词'", "price"),
            ("is_polished", "TINYINT(1) DEFAULT 0 COMMENT '是否擦亮'", "ai_prompt"),
            ("updated_at", "DATETIME COMMENT '更新时间'", "created_at"),
        ],
        "xy_announcements": [
            ("is_deleted", "TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已删除'", "content"),
        ],
        "xy_card_item_relations": [
            ("source", "VARCHAR(20) DEFAULT 'own' COMMENT '卡券来源：own-自有，dock_l1-一级对接，dock_l2-二级对接'", "item_id"),
            ("dock_record_id", "BIGINT DEFAULT NULL COMMENT '对接记录ID（对接卡券时关联）'", "source"),
        ],
        "xy_agent_orders": [
            ("card_price", "VARCHAR(32) DEFAULT NULL COMMENT '卡券成本（货主对接价）'", "dock_price"),
            ("level2_cost", "VARCHAR(32) DEFAULT NULL COMMENT '二级拿货价（一级的sub_dock_price）'", "card_price"),
            ("fee_payer", "VARCHAR(32) DEFAULT NULL COMMENT '手续费承担方：dealer-分销商，distributor-货主'", "fee_amount"),
            ("owner_user_id", "BIGINT DEFAULT NULL COMMENT '货主用户ID'", "upstream_dock_record_id"),
        ],
        "xy_advertisements": [
            ("months", "INT COMMENT '购买月数'", "ad_type"),
            ("total_amount", "VARCHAR(32) COMMENT '广告总金额'", "months"),
        ],
        "xy_settlement_records": [
            ("payment_type", "VARCHAR(16) COMMENT '收款方式：alipay-支付宝，wechat-微信'", "alipay_id"),
            ("payment_qrcode", "VARCHAR(512) COMMENT '收款码图片路径'", "payment_type"),
            ("reject_reason", "VARCHAR(512) COMMENT '拒绝原因'", "remark"),
        ],
        "xy_publish_logs": [
            ("resolved_address_id", "BIGINT DEFAULT NULL COMMENT '本次发布命中的地址池ID'", "error_message"),
            ("resolved_address_text", "VARCHAR(200) DEFAULT NULL COMMENT '本次发布实际使用的地址搜索词'", "resolved_address_id"),
            ("address_source", "VARCHAR(20) DEFAULT NULL COMMENT '地址来源：material/account_pool/global_pool'", "resolved_address_text"),
        ],
        "xy_account_login_logs": [
            ("updated_cookie_names", "VARCHAR(500) DEFAULT NULL COMMENT '接口续期更新的Cookie字段名（逗号分隔）'", "error_message"),
        ],
    }

    async def init_all(self):
        """初始化所有数据库内容"""
        try:
            logger.info("=" * 50)
            logger.info("开始初始化数据库...")
            
            # 使用上下文管理器抑制初始化时的重复警告日志
            with suppress_db_warnings():
                # 1. 创建所有表
                await self.create_all_tables()
                
                # 2. 创建默认管理员用户
                await self.create_default_admin()
                
                # 3. 初始化系统设置
                await self.init_system_settings()
                
                # 4. 初始化定时任务配置
                await self.init_scheduled_tasks()

                # 5. 初始化随机地址默认数据
                await self.init_publish_addresses()
                
                # 6. 初始化Redis平台日
                await self.init_redis_platform_day()
                
                # 7. 迁移卡券商品关联数据（从 xy_cards.item_id 到关联表）
                await self.migrate_card_item_relations()

                # 8. 迁移旧禁止发货设置到规则配置表
                await self.migrate_delivery_block_rules()

                # 9. 为历史用户回填分销秘钥（secret_key 为空的存量用户）
                await self.backfill_user_secret_keys()
            
            logger.info("数据库初始化完成")
            logger.info("=" * 50)
            
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
            raise
    
    # 旧表名 → 新表名 的重命名映射（统一加 xy_ 前缀）
    TABLES_TO_RENAME = {
        "scheduled_redelivery_log": "xy_scheduled_redelivery_log",
        "scheduled_rate_log": "xy_scheduled_rate_log",
        "scheduled_polish_log": "xy_scheduled_polish_log",
    }

    async def create_all_tables(self):
        """创建所有数据表"""
        logger.info("开始创建数据表...")
        
        # 先重命名旧表（如果存在）
        await self.rename_legacy_tables()
        
        async with async_engine.begin() as conn:
            for table_name, ddl in self.TABLES_DDL.items():
                try:
                    await conn.execute(text(ddl))
                    logger.info(f"✓ 表 {table_name} 已就绪")
                except Exception as e:
                    logger.warning(f"✗ 表 {table_name} 创建失败: {e}")
        
        logger.info(f"数据表创建完成，共 {len(self.TABLES_DDL)} 张表")
        
        # 执行字段迁移
        await self.migrate_columns()
        
        # 执行索引迁移
        await self.migrate_indexes()
    
    async def rename_legacy_tables(self):
        """重命名旧表（统一加 xy_ 前缀）"""
        async with async_engine.begin() as conn:
            for old_name, new_name in self.TABLES_TO_RENAME.items():
                try:
                    # 检查旧表是否存在
                    check_sql = text(f"""
                        SELECT COUNT(*) FROM information_schema.TABLES
                        WHERE TABLE_SCHEMA = DATABASE()
                        AND TABLE_NAME = '{old_name}'
                    """)
                    result = await conn.execute(check_sql)
                    old_exists = result.scalar() > 0
                    if not old_exists:
                        continue
                    
                    # 检查新表是否已存在
                    check_new_sql = text(f"""
                        SELECT COUNT(*) FROM information_schema.TABLES
                        WHERE TABLE_SCHEMA = DATABASE()
                        AND TABLE_NAME = '{new_name}'
                    """)
                    result = await conn.execute(check_new_sql)
                    new_exists = result.scalar() > 0
                    if new_exists:
                        logger.debug(f"✓ 新表 {new_name} 已存在，跳过重命名")
                        continue
                    
                    # 执行重命名
                    rename_sql = text(f"RENAME TABLE `{old_name}` TO `{new_name}`")
                    await conn.execute(rename_sql)
                    logger.info(f"✓ 表 {old_name} 已重命名为 {new_name}")
                except Exception as e:
                    logger.warning(f"✗ 重命名表 {old_name} → {new_name} 失败: {e}")

    async def migrate_columns(self):
        """检查并添加/修改字段"""
        logger.info("检查字段迁移...")
        
        async with async_engine.begin() as conn:
            for table_name, columns in self.COLUMN_MIGRATIONS.items():
                for col_name, col_def, after_col in columns:
                    try:
                        # 检查字段是否存在
                        check_sql = text(f"""
                            SELECT COUNT(*) FROM information_schema.COLUMNS 
                            WHERE TABLE_SCHEMA = DATABASE() 
                            AND TABLE_NAME = '{table_name}' 
                            AND COLUMN_NAME = '{col_name}'
                        """)
                        result = await conn.execute(check_sql)
                        exists = result.scalar() > 0
                        
                        if not exists:
                            # 添加字段
                            try:
                                alter_sql = text(
                                    f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def} AFTER {after_col}"
                                )
                                await conn.execute(alter_sql)
                            except Exception:
                                # AFTER 失败则追加到表末尾
                                alter_sql = text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}")
                                await conn.execute(alter_sql)
                            logger.info(f"✓ 表 {table_name} 添加字段 {col_name}")
                        else:
                            logger.debug(f"✓ 表 {table_name} 已有字段 {col_name}")
                    except Exception as e:
                        logger.warning(f"✗ 表 {table_name} 字段 {col_name} 迁移失败: {e}")

            # xy_users: account_limit 字段允许为空且默认值为空
            try:
                check_account_limit = text("""
                    SELECT IS_NULLABLE, COLUMN_DEFAULT FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_users'
                    AND COLUMN_NAME = 'account_limit'
                """)
                result = await conn.execute(check_account_limit)
                account_limit_row = result.fetchone()
                if account_limit_row and (
                    account_limit_row.IS_NULLABLE != 'YES'
                    or account_limit_row.COLUMN_DEFAULT is not None
                ):
                    await conn.execute(text(
                        "ALTER TABLE xy_users MODIFY COLUMN account_limit INT DEFAULT NULL COMMENT '可添加账号数量'"
                    ))
                    logger.info("✓ xy_users: account_limit 字段已调整为允许为空且默认值为空")
            except Exception as e:
                logger.warning(f"✗ xy_users account_limit 字段迁移失败: {e}")

            # xy_advertisements: 将 status 枚举扩展为包含 'unpaid'
            try:
                check_enum = text("""
                    SELECT COLUMN_TYPE FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_advertisements'
                    AND COLUMN_NAME = 'status'
                """)
                result = await conn.execute(check_enum)
                col_type = result.scalar()
                if col_type and 'unpaid' not in col_type:
                    await conn.execute(text(
                        "ALTER TABLE xy_advertisements MODIFY COLUMN status ENUM('unpaid','pending','approved') DEFAULT 'unpaid' COMMENT '审核状态'"
                    ))
                    logger.info("✓ xy_advertisements: status 枚举已扩展（新增 unpaid）")
            except Exception as e:
                logger.warning(f"✗ xy_advertisements status 枚举迁移失败: {e}")

            # xy_token_cache: 将 user_id 字段从 VARCHAR(64) 扩展到 VARCHAR(128)
            try:
                check_len = text("""
                    SELECT CHARACTER_MAXIMUM_LENGTH FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_token_cache'
                    AND COLUMN_NAME = 'user_id'
                """)
                result = await conn.execute(check_len)
                max_len = result.scalar()
                if max_len and max_len < 128:
                    await conn.execute(text(
                        "ALTER TABLE xy_token_cache MODIFY COLUMN user_id VARCHAR(128) NOT NULL COMMENT '用户ID（myid）'"
                    ))
                    logger.info("✓ xy_token_cache: user_id 字段长度已扩展为 VARCHAR(128)")
            except Exception as e:
                logger.warning(f"✗ xy_token_cache user_id 字段迁移失败: {e}")

            # xy_scheduled_api_cookie_renew_log: status 字段长度扩展（20→30，支持 browser_renewed/need_password_login）
            try:
                check_status_len = text("""
                    SELECT CHARACTER_MAXIMUM_LENGTH FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_scheduled_api_cookie_renew_log'
                    AND COLUMN_NAME = 'status'
                """)
                result = await conn.execute(check_status_len)
                status_len = result.scalar()
                if status_len and status_len < 30:
                    await conn.execute(text(
                        "ALTER TABLE xy_scheduled_api_cookie_renew_log MODIFY COLUMN "
                        "`status` VARCHAR(30) NOT NULL "
                        "COMMENT '状态：success/cookie_updated/browser_renewed/need_password_login/failed'"
                    ))
                    logger.info("✓ xy_scheduled_api_cookie_renew_log: status 字段长度已扩展为 VARCHAR(30)")
            except Exception as e:
                logger.warning(f"✗ xy_scheduled_api_cookie_renew_log status 字段迁移失败: {e}")

            # xy_cards: 将 text_content / data_content 从 TEXT 升级为 LONGTEXT（支持超大卡券内容）
            for card_col in ("text_content", "data_content"):
                try:
                    check_card_col = text("""
                        SELECT DATA_TYPE FROM information_schema.COLUMNS
                        WHERE TABLE_SCHEMA = DATABASE()
                        AND TABLE_NAME = 'xy_cards'
                        AND COLUMN_NAME = :col_name
                    """)
                    result = await conn.execute(check_card_col, {"col_name": card_col})
                    data_type = result.scalar()
                    # DATA_TYPE 返回小写类型名（如 text/longtext），非 longtext 时升级
                    if data_type and data_type.lower() != 'longtext':
                        await conn.execute(text(
                            f"ALTER TABLE xy_cards MODIFY COLUMN {card_col} LONGTEXT NULL"
                        ))
                        logger.info(f"✓ xy_cards: {card_col} 字段已升级为 LONGTEXT")
                except Exception as e:
                    logger.warning(f"✗ xy_cards {card_col} 字段迁移失败: {e}")

    async def migrate_indexes(self):
        """检查并迁移索引（如更新 UNIQUE KEY 等）"""
        logger.info("检查索引迁移...")
        
        async with async_engine.begin() as conn:
            try:
                # xy_card_item_relations: 将旧的 uk_card_item(card_id, item_id) 替换为 uk_card_item_dock(card_id, item_id, dock_record_id)
                # 检查旧索引是否存在
                check_old = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_card_item_relations'
                    AND INDEX_NAME = 'uk_card_item'
                """)
                result = await conn.execute(check_old)
                old_exists = result.scalar() > 0
                
                if old_exists:
                    # 先修复历史数据：确保 source 字段有值
                    await conn.execute(text(
                        "UPDATE xy_card_item_relations SET source = 'own' WHERE source IS NULL"
                    ))
                    # 删除旧索引并创建新索引
                    await conn.execute(text("ALTER TABLE xy_card_item_relations DROP INDEX uk_card_item"))
                    await conn.execute(text(
                        "ALTER TABLE xy_card_item_relations ADD UNIQUE KEY uk_card_item_dock (card_id, item_id, dock_record_id)"
                    ))
                    logger.info("✓ xy_card_item_relations: uk_card_item → uk_card_item_dock 迁移完成（历史数据已修复）")
                else:
                    # 检查新索引是否已存在
                    check_new = text("""
                        SELECT COUNT(*) FROM information_schema.STATISTICS
                        WHERE TABLE_SCHEMA = DATABASE()
                        AND TABLE_NAME = 'xy_card_item_relations'
                        AND INDEX_NAME = 'uk_card_item_dock'
                    """)
                    result = await conn.execute(check_new)
                    new_exists = result.scalar() > 0
                    if new_exists:
                        logger.debug("✓ xy_card_item_relations: uk_card_item_dock 索引已存在")
                    else:
                        # 新表没有任何唯一索引，创建新的
                        await conn.execute(text(
                            "ALTER TABLE xy_card_item_relations ADD UNIQUE KEY uk_card_item_dock (card_id, item_id, dock_record_id)"
                        ))
                        logger.info("✓ xy_card_item_relations: 创建 uk_card_item_dock 索引")
            except Exception as e:
                logger.warning(f"✗ 索引迁移失败: {e}")

            # 为 xy_users 补建 created_at 索引
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_users'
                    AND INDEX_NAME = 'idx_user_created'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_users ADD INDEX idx_user_created (created_at)"
                    ))
                    logger.info("✓ xy_users: 创建 idx_user_created 索引")
            except Exception as e:
                logger.warning(f"✗ xy_users idx_user_created 创建失败: {e}")

            # 为 xy_accounts 补建 created_at 索引
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_accounts'
                    AND INDEX_NAME = 'idx_account_created'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_accounts ADD INDEX idx_account_created (created_at)"
                    ))
                    logger.info("✓ xy_accounts: 创建 idx_account_created 索引")
            except Exception as e:
                logger.warning(f"✗ xy_accounts idx_account_created 创建失败: {e}")

            # 为 xy_keyword_rules 补建 (account_id, item_id) 复合索引
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_keyword_rules'
                    AND INDEX_NAME = 'idx_kw_account_item'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_keyword_rules ADD INDEX idx_kw_account_item (account_id, item_id)"
                    ))
                    logger.info("✓ xy_keyword_rules: 创建 idx_kw_account_item 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_keyword_rules 复合索引创建失败: {e}")

            # 为 xy_keyword_rules 补建 (account_id, is_active) 复合索引
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_keyword_rules'
                    AND INDEX_NAME = 'idx_kw_account_active'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_keyword_rules ADD INDEX idx_kw_account_active (account_id, is_active)"
                    ))
                    logger.info("✓ xy_keyword_rules: 创建 idx_kw_account_active 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_keyword_rules idx_kw_account_active 创建失败: {e}")

            # 为 xy_catalog_items 补建 (account_id, item_id) 复合索引
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_catalog_items'
                    AND INDEX_NAME = 'idx_cat_account_item'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_catalog_items ADD INDEX idx_cat_account_item (account_id, item_id)"
                    ))
                    logger.info("✓ xy_catalog_items: 创建 idx_cat_account_item 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_catalog_items 复合索引创建失败: {e}")

            # 为 xy_cards 补建 (user_id, item_id) 复合索引
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_cards'
                    AND INDEX_NAME = 'idx_card_user_item'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_cards ADD INDEX idx_card_user_item (user_id, item_id)"
                    ))
                    logger.info("✓ xy_cards: 创建 idx_card_user_item 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_cards 复合索引创建失败: {e}")

            # 为 xy_dock_records 补建 parent_dock_id 索引和 (user_id, level) 复合索引
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_dock_records'
                    AND INDEX_NAME = 'idx_parent_dock_id'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_dock_records ADD INDEX idx_parent_dock_id (parent_dock_id)"
                    ))
                    logger.info("✓ xy_dock_records: 创建 idx_parent_dock_id 索引")
            except Exception as e:
                logger.warning(f"✗ xy_dock_records idx_parent_dock_id 创建失败: {e}")

            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_dock_records'
                    AND INDEX_NAME = 'idx_dock_user_level'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_dock_records ADD INDEX idx_dock_user_level (user_id, level)"
                    ))
                    logger.info("✓ xy_dock_records: 创建 idx_dock_user_level 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_dock_records idx_dock_user_level 创建失败: {e}")

            # 为 xy_catalog_items 补建 (owner_id, created_at) 复合索引 —— 加速商品管理列表分页（owner_id 过滤 + created_at 倒序）
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_catalog_items'
                    AND INDEX_NAME = 'idx_cat_owner_created'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_catalog_items ADD INDEX idx_cat_owner_created (owner_id, created_at)"
                    ))
                    logger.info("✓ xy_catalog_items: 创建 idx_cat_owner_created 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_catalog_items idx_cat_owner_created 创建失败: {e}")

            # 为 xy_catalog_items 补建 (account_id, item_id) 唯一约束 —— 防止「定时获取闲鱼商品任务」
            # 与「商品管理页手动触发同步」两个流程并发 upsert 时重复插入同一商品（兜底）。
            # 注意：项目硬性规范禁止删除数据，存在历史重复数据时不自动清理，
            # 仅打印警告并跳过创建，待人工合并后下次启动自检再补建。
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_catalog_items'
                    AND INDEX_NAME = 'uk_cat_account_item'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    # 先检测是否存在 (account_id, item_id) 重复数据
                    dup_check = text("""
                        SELECT COUNT(*) FROM (
                            SELECT account_id, item_id
                            FROM xy_catalog_items
                            GROUP BY account_id, item_id
                            HAVING COUNT(*) > 1
                        ) AS dup
                    """)
                    dup_result = await conn.execute(dup_check)
                    dup_groups = dup_result.scalar() or 0
                    if dup_groups > 0:
                        logger.warning(
                            f"✗ xy_catalog_items 存在 {dup_groups} 组 (account_id, item_id) 重复数据，"
                            f"为遵守禁止删除数据规范，暂不创建 uk_cat_account_item 唯一约束。"
                            f"请人工合并重复商品后，重启服务自动补建（当前由 Redis 账号锁兜底防并发）"
                        )
                    else:
                        await conn.execute(text(
                            "ALTER TABLE xy_catalog_items ADD UNIQUE KEY uk_cat_account_item (account_id, item_id)"
                        ))
                        logger.info("✓ xy_catalog_items: 创建 uk_cat_account_item 唯一约束")
            except Exception as e:
                logger.warning(f"✗ xy_catalog_items uk_cat_account_item 创建失败: {e}")

            # 为 xy_card_item_relations 补建 (user_id, item_id) 复合索引
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_card_item_relations'
                    AND INDEX_NAME = 'idx_cir_user_item'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_card_item_relations ADD INDEX idx_cir_user_item (user_id, item_id)"
                    ))
                    logger.info("✓ xy_card_item_relations: 创建 idx_cir_user_item 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_card_item_relations idx_cir_user_item 创建失败: {e}")

            # 为 xy_card_item_relations 补建 (item_id, card_id) 复合索引 —— 加速关联卡券弹窗 JOIN 查询
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_card_item_relations'
                    AND INDEX_NAME = 'idx_cir_item_card'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_card_item_relations ADD INDEX idx_cir_item_card (item_id, card_id)"
                    ))
                    logger.info("✓ xy_card_item_relations: 创建 idx_cir_item_card 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_card_item_relations idx_cir_item_card 创建失败: {e}")

            # 为 xy_cards 补建 (user_id, id) 复合索引 —— 加速按用户分页查询（ORDER BY id DESC）
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_cards'
                    AND INDEX_NAME = 'idx_cards_user_id_desc'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_cards ADD INDEX idx_cards_user_id_desc (user_id, id)"
                    ))
                    logger.info("✓ xy_cards: 创建 idx_cards_user_id_desc 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_cards idx_cards_user_id_desc 创建失败: {e}")

            # 为 xy_cards 补建 (user_id, enabled) 复合索引 —— 加速发货匹配时过滤启用卡券
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_cards'
                    AND INDEX_NAME = 'idx_cards_user_enabled'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_cards ADD INDEX idx_cards_user_enabled (user_id, enabled)"
                    ))
                    logger.info("✓ xy_cards: 创建 idx_cards_user_enabled 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_cards idx_cards_user_enabled 创建失败: {e}")

            # 为 xy_agent_orders 补建 (upstream_user_id, status) 复合索引
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_agent_orders'
                    AND INDEX_NAME = 'idx_ao_upstream_status'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_agent_orders ADD INDEX idx_ao_upstream_status (upstream_user_id, status)"
                    ))
                    logger.info("✓ xy_agent_orders: 创建 idx_ao_upstream_status 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_agent_orders 复合索引创建失败: {e}")

            # 为 xy_risk_control_logs 补建 (account_id, processing_status) 复合索引
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_risk_control_logs'
                    AND INDEX_NAME = 'idx_rcl_account_status'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_risk_control_logs ADD INDEX idx_rcl_account_status (account_id, processing_status)"
                    ))
                    logger.info("✓ xy_risk_control_logs: 创建 idx_rcl_account_status 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_risk_control_logs 复合索引创建失败: {e}")

            # 为 xy_risk_control_logs 补建 (account_identifier, processing_status, created_at) 复合索引
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_risk_control_logs'
                    AND INDEX_NAME = 'idx_rcl_identifier_status_created'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_risk_control_logs ADD INDEX idx_rcl_identifier_status_created (account_identifier, processing_status, created_at)"
                    ))
                    logger.info("✓ xy_risk_control_logs: 创建 idx_rcl_identifier_status_created 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_risk_control_logs idx_rcl_identifier_status_created 创建失败: {e}")

            # 为 xy_scheduled_redelivery_log 补建 (created_at, batch_id) 复合索引
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_scheduled_redelivery_log'
                    AND INDEX_NAME = 'idx_srl_created_batch'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_scheduled_redelivery_log ADD INDEX idx_srl_created_batch (created_at, batch_id)"
                    ))
                    logger.info("✓ xy_scheduled_redelivery_log: 创建 idx_srl_created_batch 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_scheduled_redelivery_log idx_srl_created_batch 创建失败: {e}")

            # 为 xy_scheduled_redelivery_log 补建 (batch_id, created_at, status) 复合索引
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_scheduled_redelivery_log'
                    AND INDEX_NAME = 'idx_srl_batch_created_status'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_scheduled_redelivery_log ADD INDEX idx_srl_batch_created_status (batch_id, created_at, status)"
                    ))
                    logger.info("✓ xy_scheduled_redelivery_log: 创建 idx_srl_batch_created_status 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_scheduled_redelivery_log idx_srl_batch_created_status 创建失败: {e}")

            # 为 xy_scheduled_rate_log 补建 (created_at, batch_id) 复合索引
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_scheduled_rate_log'
                    AND INDEX_NAME = 'idx_srate_created_batch'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_scheduled_rate_log ADD INDEX idx_srate_created_batch (created_at, batch_id)"
                    ))
                    logger.info("✓ xy_scheduled_rate_log: 创建 idx_srate_created_batch 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_scheduled_rate_log idx_srate_created_batch 创建失败: {e}")

            # 为 xy_scheduled_rate_log 补建 (batch_id, created_at, status) 复合索引
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_scheduled_rate_log'
                    AND INDEX_NAME = 'idx_srate_batch_created_status'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_scheduled_rate_log ADD INDEX idx_srate_batch_created_status (batch_id, created_at, status)"
                    ))
                    logger.info("✓ xy_scheduled_rate_log: 创建 idx_srate_batch_created_status 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_scheduled_rate_log idx_srate_batch_created_status 创建失败: {e}")

            # 为 xy_scheduled_polish_log 补建 (created_at, batch_id) 复合索引
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_scheduled_polish_log'
                    AND INDEX_NAME = 'idx_spol_created_batch'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_scheduled_polish_log ADD INDEX idx_spol_created_batch (created_at, batch_id)"
                    ))
                    logger.info("✓ xy_scheduled_polish_log: 创建 idx_spol_created_batch 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_scheduled_polish_log idx_spol_created_batch 创建失败: {e}")

            # 为 xy_scheduled_polish_log 补建 (batch_id, created_at, status) 复合索引
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_scheduled_polish_log'
                    AND INDEX_NAME = 'idx_spol_batch_created_status'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_scheduled_polish_log ADD INDEX idx_spol_batch_created_status (batch_id, created_at, status)"
                    ))
                    logger.info("✓ xy_scheduled_polish_log: 创建 idx_spol_batch_created_status 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_scheduled_polish_log idx_spol_batch_created_status 创建失败: {e}")

            # 为 xy_scheduled_red_flower_log 补建 (created_at, batch_id) 复合索引
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_scheduled_red_flower_log'
                    AND INDEX_NAME = 'idx_srf_created_batch'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_scheduled_red_flower_log ADD INDEX idx_srf_created_batch (created_at, batch_id)"
                    ))
                    logger.info("✓ xy_scheduled_red_flower_log: 创建 idx_srf_created_batch 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_scheduled_red_flower_log idx_srf_created_batch 创建失败: {e}")

            # 为 xy_scheduled_red_flower_log 补建 (batch_id, created_at, status) 复合索引
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_scheduled_red_flower_log'
                    AND INDEX_NAME = 'idx_srf_batch_created_status'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_scheduled_red_flower_log ADD INDEX idx_srf_batch_created_status (batch_id, created_at, status)"
                    ))
                    logger.info("✓ xy_scheduled_red_flower_log: 创建 idx_srf_batch_created_status 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_scheduled_red_flower_log idx_srf_batch_created_status 创建失败: {e}")

            # 为 xy_fund_flows 补建 (user_id, id) 复合索引
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_fund_flows'
                    AND INDEX_NAME = 'idx_ff_user_id_desc'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_fund_flows ADD INDEX idx_ff_user_id_desc (user_id, id)"
                    ))
                    logger.info("✓ xy_fund_flows: 创建 idx_ff_user_id_desc 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_fund_flows idx_ff_user_id_desc 创建失败: {e}")

            # 为 xy_fund_flows 补建 (user_id, type, id) 复合索引
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_fund_flows'
                    AND INDEX_NAME = 'idx_ff_user_type_id_desc'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_fund_flows ADD INDEX idx_ff_user_type_id_desc (user_id, type, id)"
                    ))
                    logger.info("✓ xy_fund_flows: 创建 idx_ff_user_type_id_desc 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_fund_flows idx_ff_user_type_id_desc 创建失败: {e}")

            # 为 xy_settlement_records 补建 (user_id, created_at, id) 复合索引
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_settlement_records'
                    AND INDEX_NAME = 'idx_sr_user_created_id'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_settlement_records ADD INDEX idx_sr_user_created_id (user_id, created_at, id)"
                    ))
                    logger.info("✓ xy_settlement_records: 创建 idx_sr_user_created_id 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_settlement_records idx_sr_user_created_id 创建失败: {e}")

            # 为 xy_orders 补建 (owner_id, account_id, placed_at) 复合索引
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_orders'
                    AND INDEX_NAME = 'idx_order_owner_account_placed'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_orders ADD INDEX idx_order_owner_account_placed (owner_id, account_id, placed_at)"
                    ))
                    logger.info("✓ xy_orders: 创建 idx_order_owner_account_placed 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_orders idx_order_owner_account_placed 创建失败: {e}")

            # 为 xy_orders 补建 (owner_id, placed_at) 复合索引
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_orders'
                    AND INDEX_NAME = 'idx_order_owner_placed'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_orders ADD INDEX idx_order_owner_placed (owner_id, placed_at)"
                    ))
                    logger.info("✓ xy_orders: 创建 idx_order_owner_placed 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_orders idx_order_owner_placed 创建失败: {e}")

            # 为 xy_orders 补建 (owner_id, account_id, buyer_id, created_at) 复合索引
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_orders'
                    AND INDEX_NAME = 'idx_order_owner_account_buyer_created'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_orders ADD INDEX idx_order_owner_account_buyer_created (owner_id, account_id, buyer_id, created_at)"
                    ))
                    logger.info("✓ xy_orders: 创建 idx_order_owner_account_buyer_created 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_orders idx_order_owner_account_buyer_created 创建失败: {e}")

            # 为 xy_orders 补建 created_at 索引
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_orders'
                    AND INDEX_NAME = 'idx_order_created_at'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_orders ADD INDEX idx_order_created_at (created_at)"
                    ))
                    logger.info("✓ xy_orders: 创建 idx_order_created_at 索引")
            except Exception as e:
                logger.warning(f"✗ xy_orders idx_order_created_at 创建失败: {e}")

            # 为 xy_orders 补建 (placed_at, status) 复合索引
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_orders'
                    AND INDEX_NAME = 'idx_order_placed_status'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_orders ADD INDEX idx_order_placed_status (placed_at, status)"
                    ))
                    logger.info("✓ xy_orders: 创建 idx_order_placed_status 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_orders idx_order_placed_status 创建失败: {e}")

            # 为 xy_orders 补建 (created_at, status) 复合索引
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_orders'
                    AND INDEX_NAME = 'idx_order_created_status'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_orders ADD INDEX idx_order_created_status (created_at, status)"
                    ))
                    logger.info("✓ xy_orders: 创建 idx_order_created_status 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_orders idx_order_created_status 创建失败: {e}")

            # 为 xy_orders 补建 (owner_id, created_at) 复合索引
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_orders'
                    AND INDEX_NAME = 'idx_order_owner_created'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_orders ADD INDEX idx_order_owner_created (owner_id, created_at)"
                    ))
                    logger.info("✓ xy_orders: 创建 idx_order_owner_created 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_orders idx_order_owner_created 创建失败: {e}")

            # 为 xy_agent_orders 补建 created_at 索引
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_agent_orders'
                    AND INDEX_NAME = 'idx_agent_order_created'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_agent_orders ADD INDEX idx_agent_order_created (created_at)"
                    ))
                    logger.info("✓ xy_agent_orders: 创建 idx_agent_order_created 索引")
            except Exception as e:
                logger.warning(f"✗ xy_agent_orders idx_agent_order_created 创建失败: {e}")

            # 为 xy_product_materials 补建 (user_id, created_at) 复合索引
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_product_materials'
                    AND INDEX_NAME = 'idx_pm_user_created'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_product_materials ADD INDEX idx_pm_user_created (user_id, created_at)"
                    ))
                    logger.info("✓ xy_product_materials: 创建 idx_pm_user_created 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_product_materials idx_pm_user_created 创建失败: {e}")

            # 为 xy_publish_logs 补建 (user_id, created_at) 复合索引
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_publish_logs'
                    AND INDEX_NAME = 'idx_publish_user_created'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_publish_logs ADD INDEX idx_publish_user_created (user_id, created_at)"
                    ))
                    logger.info("✓ xy_publish_logs: 创建 idx_publish_user_created 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_publish_logs idx_publish_user_created 创建失败: {e}")

            auto_reply_log_table_exists = False
            try:
                table_check = text("""
                    SELECT COUNT(*) FROM information_schema.TABLES
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_auto_reply_message_logs'
                """)
                table_result = await conn.execute(table_check)
                auto_reply_log_table_exists = table_result.scalar() > 0
            except Exception:
                auto_reply_log_table_exists = False

            if auto_reply_log_table_exists:
                try:
                    check = text("""
                        SELECT COUNT(*) FROM information_schema.STATISTICS
                        WHERE TABLE_SCHEMA = DATABASE()
                        AND TABLE_NAME = 'xy_auto_reply_message_logs'
                        AND INDEX_NAME = 'idx_arml_account_status_created'
                    """)
                    result = await conn.execute(check)
                    if result.scalar() == 0:
                        await conn.execute(text(
                            "ALTER TABLE xy_auto_reply_message_logs ADD INDEX idx_arml_account_status_created (account_id, process_status, created_at)"
                        ))
                        logger.info("✓ xy_auto_reply_message_logs: 创建 idx_arml_account_status_created 复合索引")
                except Exception as e:
                    logger.warning(f"✗ xy_auto_reply_message_logs idx_arml_account_status_created 创建失败: {e}")

                try:
                    check = text("""
                        SELECT COUNT(*) FROM information_schema.STATISTICS
                        WHERE TABLE_SCHEMA = DATABASE()
                        AND TABLE_NAME = 'xy_auto_reply_message_logs'
                        AND INDEX_NAME = 'idx_arml_owner_status_created'
                    """)
                    result = await conn.execute(check)
                    if result.scalar() == 0:
                        await conn.execute(text(
                            "ALTER TABLE xy_auto_reply_message_logs ADD INDEX idx_arml_owner_status_created (owner_id, process_status, created_at)"
                        ))
                        logger.info("✓ xy_auto_reply_message_logs: 创建 idx_arml_owner_status_created 复合索引")
                except Exception as e:
                    logger.warning(f"✗ xy_auto_reply_message_logs idx_arml_owner_status_created 创建失败: {e}")

                try:
                    check = text("""
                        SELECT COUNT(*) FROM information_schema.STATISTICS
                        WHERE TABLE_SCHEMA = DATABASE()
                        AND TABLE_NAME = 'xy_auto_reply_message_logs'
                        AND INDEX_NAME = 'idx_arml_status_strategy_created'
                    """)
                    result = await conn.execute(check)
                    if result.scalar() == 0:
                        await conn.execute(text(
                            "ALTER TABLE xy_auto_reply_message_logs ADD INDEX idx_arml_status_strategy_created (process_status, reply_strategy, created_at)"
                        ))
                        logger.info("✓ xy_auto_reply_message_logs: 创建 idx_arml_status_strategy_created 复合索引")
                except Exception as e:
                    logger.warning(f"✗ xy_auto_reply_message_logs idx_arml_status_strategy_created 创建失败: {e}")

                try:
                    check = text("""
                        SELECT COUNT(*) FROM information_schema.STATISTICS
                        WHERE TABLE_SCHEMA = DATABASE()
                        AND TABLE_NAME = 'xy_auto_reply_message_logs'
                        AND INDEX_NAME = 'idx_arml_status_created'
                    """)
                    result = await conn.execute(check)
                    if result.scalar() == 0:
                        await conn.execute(text(
                            "ALTER TABLE xy_auto_reply_message_logs ADD INDEX idx_arml_status_created (process_status, created_at)"
                        ))
                        logger.info("✓ xy_auto_reply_message_logs: 创建 idx_arml_status_created 复合索引")
                except Exception as e:
                    logger.warning(f"✗ xy_auto_reply_message_logs idx_arml_status_created 创建失败: {e}")

                try:
                    check = text("""
                        SELECT COUNT(*) FROM information_schema.STATISTICS
                        WHERE TABLE_SCHEMA = DATABASE()
                        AND TABLE_NAME = 'xy_auto_reply_message_logs'
                        AND INDEX_NAME = 'idx_order_no'
                    """)
                    result = await conn.execute(check)
                    if result.scalar() == 0:
                        await conn.execute(text(
                            "ALTER TABLE xy_auto_reply_message_logs ADD INDEX idx_order_no (order_no)"
                        ))
                        logger.info("✓ xy_auto_reply_message_logs: 创建 idx_order_no 索引")
                except Exception as e:
                    logger.warning(f"✗ xy_auto_reply_message_logs idx_order_no 创建失败: {e}")

                # 补建 (order_no, reply_strategy, id) 复合索引 —— 加速「按订单号+回复策略取最新一条日志」的查询
                # （订单列表关联自动发货发送状态：WHERE reply_strategy='auto_delivery' AND order_no IN (...) GROUP BY order_no, MAX(id)）
                try:
                    check = text("""
                        SELECT COUNT(*) FROM information_schema.STATISTICS
                        WHERE TABLE_SCHEMA = DATABASE()
                        AND TABLE_NAME = 'xy_auto_reply_message_logs'
                        AND INDEX_NAME = 'idx_arml_order_strategy_id'
                    """)
                    result = await conn.execute(check)
                    if result.scalar() == 0:
                        await conn.execute(text(
                            "ALTER TABLE xy_auto_reply_message_logs ADD INDEX idx_arml_order_strategy_id (order_no, reply_strategy, id)"
                        ))
                        logger.info("✓ xy_auto_reply_message_logs: 创建 idx_arml_order_strategy_id 复合索引")
                except Exception as e:
                    logger.warning(f"✗ xy_auto_reply_message_logs idx_arml_order_strategy_id 创建失败: {e}")

            # 为 xy_dock_records 补建 (source_user_id, level) 复合索引 —— 加速二级分销商列表查询
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_dock_records'
                    AND INDEX_NAME = 'idx_dock_source_level'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_dock_records ADD INDEX idx_dock_source_level (source_user_id, level)"
                    ))
                    logger.info("✓ xy_dock_records: 创建 idx_dock_source_level 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_dock_records idx_dock_source_level 创建失败: {e}")

            # 为 xy_cards 补建 (is_dockable, enabled) 复合索引 —— 加速可对接卡券列表主筛选
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_cards'
                    AND INDEX_NAME = 'idx_cards_dockable_enabled'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_cards ADD INDEX idx_cards_dockable_enabled (is_dockable, enabled)"
                    ))
                    logger.info("✓ xy_cards: 创建 idx_cards_dockable_enabled 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_cards idx_cards_dockable_enabled 创建失败: {e}")

            # 为 xy_personal_blacklist 补建 (owner_id, created_at) 复合索引 —— 加速个人黑名单列表分页排序
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_personal_blacklist'
                    AND INDEX_NAME = 'idx_pb_owner_created'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_personal_blacklist ADD INDEX idx_pb_owner_created (owner_id, created_at)"
                    ))
                    logger.info("✓ xy_personal_blacklist: 创建 idx_pb_owner_created 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_personal_blacklist idx_pb_owner_created 创建失败: {e}")

            # 为 xy_platform_blacklist 补建 created_at 索引 —— 加速闲鱼黑名单列表分页排序
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_platform_blacklist'
                    AND INDEX_NAME = 'idx_plb_created'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_platform_blacklist ADD INDEX idx_plb_created (created_at)"
                    ))
                    logger.info("✓ xy_platform_blacklist: 创建 idx_plb_created 索引")
            except Exception as e:
                logger.warning(f"✗ xy_platform_blacklist idx_plb_created 创建失败: {e}")

            # 为 xy_listing_monitor_items 补建 created_at 索引 —— 加速「卖家ID补全」等定时任务按当天采集入库时间过滤
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_listing_monitor_items'
                    AND INDEX_NAME = 'idx_lmi_created'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_listing_monitor_items ADD INDEX idx_lmi_created (created_at)"
                    ))
                    logger.info("✓ xy_listing_monitor_items: 创建 idx_lmi_created 索引")
            except Exception as e:
                logger.warning(f"✗ xy_listing_monitor_items idx_lmi_created 创建失败: {e}")

            # 为 xy_listing_monitor_items 补建查询索引 —— 原仅有 task/owner/publish_time/created_at 索引，
            # 未覆盖调度任务/去重/列表的高频过滤字段，表数据增大后会全表扫描导致查询很慢
            lmi_query_indexes = [
                # 「采集商品发送私信」定时任务：order_status='success' + is_dm_sent=0 + ordered_at>=cutoff
                ("idx_lmi_dm_send", "(order_status, is_dm_sent, ordered_at)"),
                # 「采集商品自动下单」定时任务：is_ordered=0 + order_attempts<上限
                ("idx_lmi_order_pending", "(is_ordered, order_attempts)"),
                # 下单去重 has_owner_ordered_item：item_id + is_ordered（item_id 原仅为联合唯一键非最左列）
                ("idx_lmi_item_ordered", "(item_id, is_ordered)"),
                # 前端列表分页：owner_id 过滤 + 按 publish_time 排序
                ("idx_lmi_owner_publish", "(owner_id, publish_time)"),
            ]
            for idx_name, idx_cols in lmi_query_indexes:
                try:
                    check = text("""
                        SELECT COUNT(*) FROM information_schema.STATISTICS
                        WHERE TABLE_SCHEMA = DATABASE()
                        AND TABLE_NAME = 'xy_listing_monitor_items'
                        AND INDEX_NAME = :idx_name
                    """)
                    result = await conn.execute(check, {"idx_name": idx_name})
                    if result.scalar() == 0:
                        await conn.execute(text(
                            f"ALTER TABLE xy_listing_monitor_items ADD INDEX {idx_name} {idx_cols}"
                        ))
                        logger.info(f"✓ xy_listing_monitor_items: 创建 {idx_name} 索引")
                except Exception as e:
                    logger.warning(f"✗ xy_listing_monitor_items {idx_name} 创建失败: {e}")

            # 为 xy_listing_monitor_tasks 补建 category_id 索引 —— 加速按分类筛选任务
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_listing_monitor_tasks'
                    AND INDEX_NAME = 'idx_lmt_category'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_listing_monitor_tasks ADD INDEX idx_lmt_category (category_id)"
                    ))
                    logger.info("✓ xy_listing_monitor_tasks: 创建 idx_lmt_category 索引")
            except Exception as e:
                logger.warning(f"✗ xy_listing_monitor_tasks idx_lmt_category 创建失败: {e}")

            # 为 xy_risk_control_logs 补建 (owner_id, created_at) 复合索引 —— 加速按用户筛选+时间倒序分页
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_risk_control_logs'
                    AND INDEX_NAME = 'idx_rcl_owner_created'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    await conn.execute(text(
                        "ALTER TABLE xy_risk_control_logs ADD INDEX idx_rcl_owner_created (owner_id, created_at)"
                    ))
                    logger.info("✓ xy_risk_control_logs: 创建 idx_rcl_owner_created 复合索引")
            except Exception as e:
                logger.warning(f"✗ xy_risk_control_logs idx_rcl_owner_created 创建失败: {e}")

            # 迁移兜底账号表唯一键：从 (owner_id) 改为 (owner_id, category_id)
            # xy_order_fallback_accounts
            try:
                check_old = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_order_fallback_accounts'
                    AND INDEX_NAME = 'uk_ofa_owner'
                """)
                result = await conn.execute(check_old)
                if result.scalar() > 0:
                    # 删除旧唯一键
                    await conn.execute(text(
                        "ALTER TABLE xy_order_fallback_accounts DROP INDEX uk_ofa_owner"
                    ))
                    logger.info("✓ xy_order_fallback_accounts: 删除旧唯一键 uk_ofa_owner")

                # 检查新唯一键是否存在
                check_new = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_order_fallback_accounts'
                    AND INDEX_NAME = 'uk_ofa_owner_category'
                """)
                result = await conn.execute(check_new)
                if result.scalar() == 0:
                    # 添加新唯一键
                    await conn.execute(text(
                        "ALTER TABLE xy_order_fallback_accounts ADD UNIQUE KEY uk_ofa_owner_category (owner_id, category_id)"
                    ))
                    logger.info("✓ xy_order_fallback_accounts: 创建新唯一键 uk_ofa_owner_category")
            except Exception as e:
                logger.warning(f"✗ xy_order_fallback_accounts 唯一键迁移失败: {e}")

            # xy_collect_fallback_accounts
            try:
                check_old = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_collect_fallback_accounts'
                    AND INDEX_NAME = 'uk_cfa_owner'
                """)
                result = await conn.execute(check_old)
                if result.scalar() > 0:
                    # 删除旧唯一键
                    await conn.execute(text(
                        "ALTER TABLE xy_collect_fallback_accounts DROP INDEX uk_cfa_owner"
                    ))
                    logger.info("✓ xy_collect_fallback_accounts: 删除旧唯一键 uk_cfa_owner")

                # 检查新唯一键是否存在
                check_new = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_collect_fallback_accounts'
                    AND INDEX_NAME = 'uk_cfa_owner_category'
                """)
                result = await conn.execute(check_new)
                if result.scalar() == 0:
                    # 添加新唯一键
                    await conn.execute(text(
                        "ALTER TABLE xy_collect_fallback_accounts ADD UNIQUE KEY uk_cfa_owner_category (owner_id, category_id)"
                    ))
                    logger.info("✓ xy_collect_fallback_accounts: 创建新唯一键 uk_cfa_owner_category")
            except Exception as e:
                logger.warning(f"✗ xy_collect_fallback_accounts 唯一键迁移失败: {e}")

            # 为 xy_orders 补建 (account_id, order_no) 唯一约束 —— 防止「定时获取闲鱼订单」
            # 与「获取待发货订单」两个任务并发 upsert 时重复插入同一订单（B方案兜底）。
            # 注意：项目硬性规范禁止删除数据，存在历史重复数据时不自动清理，
            # 仅打印警告并跳过创建，待人工合并后下次启动自检再补建。
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_orders'
                    AND INDEX_NAME = 'uk_order_account_no'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    # 先检测是否存在 (account_id, order_no) 重复数据
                    dup_check = text("""
                        SELECT COUNT(*) FROM (
                            SELECT account_id, order_no
                            FROM xy_orders
                            GROUP BY account_id, order_no
                            HAVING COUNT(*) > 1
                        ) AS dup
                    """)
                    dup_result = await conn.execute(dup_check)
                    dup_groups = dup_result.scalar() or 0
                    if dup_groups > 0:
                        logger.warning(
                            f"✗ xy_orders 存在 {dup_groups} 组 (account_id, order_no) 重复数据，"
                            f"为遵守禁止删除数据规范，暂不创建 uk_order_account_no 唯一约束。"
                            f"请人工合并重复订单后，重启服务自动补建（当前由 Redis 账号锁兜底防并发）"
                        )
                    else:
                        await conn.execute(text(
                            "ALTER TABLE xy_orders ADD UNIQUE KEY uk_order_account_no (account_id, order_no)"
                        ))
                        logger.info("✓ xy_orders: 创建 uk_order_account_no 唯一约束")
            except Exception as e:
                logger.warning(f"✗ xy_orders uk_order_account_no 创建失败: {e}")

            # 为 xy_accounts 补建 account_id 全局唯一约束 —— 闲鱼账号ID全局唯一，
            # 杜绝不同用户绑定同一账号、以及并发创建导致的重复（业务大量代码仅按
            # account_id 查询并取 first，依赖其全局唯一）。
            # 注意：项目硬性规范禁止删除数据，存在历史重复数据时不自动清理，
            # 仅打印警告并跳过创建，待人工合并后下次启动自检再补建。
            try:
                check = text("""
                    SELECT COUNT(*) FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                    AND TABLE_NAME = 'xy_accounts'
                    AND INDEX_NAME = 'uk_account_id'
                """)
                result = await conn.execute(check)
                if result.scalar() == 0:
                    # 先检测是否存在 account_id 重复数据（全局，不区分 owner_id）
                    dup_check = text("""
                        SELECT COUNT(*) FROM (
                            SELECT account_id
                            FROM xy_accounts
                            GROUP BY account_id
                            HAVING COUNT(*) > 1
                        ) AS dup
                    """)
                    dup_result = await conn.execute(dup_check)
                    dup_groups = dup_result.scalar() or 0
                    if dup_groups > 0:
                        logger.warning(
                            f"✗ xy_accounts 存在 {dup_groups} 组 account_id 重复数据，"
                            f"为遵守禁止删除数据规范，暂不创建 uk_account_id 唯一约束。"
                            f"请人工合并/处理重复账号后，重启服务自动补建"
                        )
                    else:
                        await conn.execute(text(
                            "ALTER TABLE xy_accounts ADD UNIQUE KEY uk_account_id (account_id)"
                        ))
                        logger.info("✓ xy_accounts: 创建 uk_account_id 全局唯一约束")
            except Exception as e:
                logger.warning(f"✗ xy_accounts uk_account_id 创建失败: {e}")


    async def create_default_admin(self):
        """创建默认管理员用户 (admin/admin123)"""
        logger.info("检查默认管理员用户...")
        
        try:
            async with async_session_maker() as session:
                # 检查是否已存在admin用户
                result = await session.execute(
                    text("SELECT id FROM xy_users WHERE username = 'admin' LIMIT 1")
                )
                existing = result.fetchone()
                
                if existing:
                    logger.info("✓ 管理员用户已存在，跳过创建")
                    return
                
                # 使用 passlib 创建密码哈希
                password_hash = get_password_hash("admin123")
                
                # 插入管理员用户
                await session.execute(
                    text("""
                        INSERT INTO xy_users (username, email, password_hash, status, role, created_at, updated_at)
                        VALUES ('admin', 'admin@example.com', :password_hash, 'ACTIVE', 'ADMIN', NOW(), NOW())
                    """),
                    {"password_hash": password_hash}
                )
                await session.commit()
                
                logger.info("✓ 默认管理员用户创建成功")
                logger.info("  用户名: admin")
                logger.info("  密码: admin123")
                
        except IntegrityError:
            logger.info("✓ 管理员用户已存在，跳过创建")
        except Exception as e:
            logger.error(f"✗ 创建管理员用户失败: {e}")
    
    async def init_system_settings(self):
        """初始化系统设置"""
        logger.info("初始化系统设置...")
        
        try:
            async with async_session_maker() as session:
                for key, value, description in self.DEFAULT_SETTINGS:
                    try:
                        await session.execute(
                            text("""
                                INSERT IGNORE INTO xy_system_settings (`key`, value, description, updated_at)
                                VALUES (:key, :value, :description, NOW())
                            """),
                            {"key": key, "value": value, "description": description}
                        )
                    except Exception as e:
                        logger.warning(f"设置 {key} 插入失败: {e}")
                
                await session.commit()
                logger.info(f"✓ 系统设置初始化完成，共 {len(self.DEFAULT_SETTINGS)} 项")
                
        except Exception as e:
            logger.error(f"✗ 初始化系统设置失败: {e}")

    async def init_scheduled_tasks(self):
        """初始化定时任务配置"""
        logger.info("初始化定时任务配置...")
        
        try:
            async with async_session_maker() as session:
                for task_code, task_name, interval_seconds, enabled, description in self.DEFAULT_SCHEDULED_TASKS:
                    try:
                        await session.execute(
                            text("""
                                INSERT IGNORE INTO xy_scheduled_tasks 
                                (task_code, task_name, interval_seconds, enabled, description, created_at, updated_at)
                                VALUES (:task_code, :task_name, :interval_seconds, :enabled, :description, NOW(), NOW())
                            """),
                            {
                                "task_code": task_code,
                                "task_name": task_name,
                                "interval_seconds": interval_seconds,
                                "enabled": enabled,
                                "description": description
                            }
                        )
                    except Exception as e:
                        logger.warning(f"定时任务 {task_code} 插入失败: {e}")
                
                await session.commit()
                logger.info(f"✓ 定时任务配置初始化完成，共 {len(self.DEFAULT_SCHEDULED_TASKS)} 项")
                
        except Exception as e:
            logger.error(f"✗ 初始化定时任务配置失败: {e}")

    async def init_publish_addresses(self):
        """初始化随机地址默认数据"""
        logger.info("初始化随机地址默认数据...")

        try:
            default_addresses = build_default_publish_addresses()
            async with async_session_maker() as session:
                removed_conditions = []
                removed_params: dict[str, str] = {}
                for index, prefix in enumerate(REMOVED_PUBLISH_ADDRESS_PREFIXES):
                    param_key = f"removed_prefix_{index}"
                    removed_conditions.append(f"search_keyword LIKE :{param_key}")
                    removed_params[param_key] = f"{prefix}%"

                if removed_conditions:
                    await session.execute(
                        text(
                            f"""
                                UPDATE xy_publish_addresses
                                SET is_enabled = 0,
                                    updated_at = NOW()
                                WHERE account_id IS NULL
                                  AND remark = '系统初始化默认地址'
                                  AND ({' OR '.join(removed_conditions)})
                            """
                        ),
                        removed_params,
                    )

                existing_result = await session.execute(
                    text("""
                        SELECT search_keyword
                        FROM xy_publish_addresses
                        WHERE account_id IS NULL
                    """)
                )
                existing_keywords = {
                    str(search_keyword).strip()
                    for search_keyword in existing_result.scalars().all()
                    if search_keyword and str(search_keyword).strip()
                }

                insert_rows = [
                    {
                        "name": address,
                        "search_keyword": address,
                        "sort_order": index,
                        "remark": "系统初始化默认地址",
                    }
                    for index, address in enumerate(default_addresses, start=1)
                    if address not in existing_keywords
                ]

                if insert_rows:
                    await session.execute(
                        text("""
                            INSERT INTO xy_publish_addresses (
                                name,
                                search_keyword,
                                expected_text,
                                account_id,
                                weight,
                                sort_order,
                                is_enabled,
                                use_count,
                                last_used_at,
                                created_by,
                                remark,
                                created_at,
                                updated_at
                            ) VALUES (
                                :name,
                                :search_keyword,
                                NULL,
                                NULL,
                                1,
                                :sort_order,
                                1,
                                0,
                                NULL,
                                NULL,
                                :remark,
                                NOW(),
                                NOW()
                            )
                        """),
                        insert_rows,
                    )
                    await session.commit()

                logger.info(
                    f"✓ 随机地址默认数据初始化完成，默认 {len(default_addresses)} 条，本次新增 {len(insert_rows)} 条"
                )

        except Exception as e:
            logger.warning(f"✗ 初始化随机地址默认数据失败（不影响系统运行）: {e}")

    async def init_redis_platform_day(self):
        """初始化Redis中的平台日"""
        logger.info("初始化Redis平台日...")
        
        try:
            from common.db.redis_client import get_redis_client
            
            redis_client = await get_redis_client()
            platform_day_key = "platform:day"
            
            # 检查Redis中是否已存在平台日
            existing_day = await redis_client.get(platform_day_key)
            
            if existing_day:
                logger.info(f"✓ Redis平台日已存在: {existing_day}")
            else:
                # 设置当前日期为平台日
                current_day = get_beijing_now_naive().strftime("%Y-%m-%d")
                await redis_client.set(platform_day_key, current_day)
                logger.info(f"✓ Redis平台日初始化完成: {current_day}")
                
        except Exception as e:
            logger.warning(f"✗ 初始化Redis平台日失败（不影响系统运行）: {e}")


    async def migrate_card_item_relations(self):
        """
        迁移卡券商品关联数据（仅在关联表为空时执行一次）
        
        将 xy_cards 表中 item_id 不为空的记录迁移到 xy_card_item_relations 关联表。
        关联表已有数据时跳过，避免重复迁移。
        """
        try:
            async with async_session_maker() as session:
                # 检查关联表中已有数据量
                existing_result = await session.execute(
                    text("SELECT COUNT(*) FROM xy_card_item_relations")
                )
                existing = existing_result.scalar()
                
                if existing > 0:
                    logger.debug(f"✓ 卡券商品关联表已有 {existing} 条数据，跳过迁移")
                    return
                
                # 统计需要迁移的数据量
                count_result = await session.execute(
                    text("""
                        SELECT COUNT(*) FROM xy_cards 
                        WHERE item_id IS NOT NULL AND item_id != ''
                    """)
                )
                total = count_result.scalar()
                
                if total == 0:
                    logger.info("✓ 无需迁移卡券商品关联数据")
                    return
                
                # 首次迁移：从 xy_cards 导入到关联表
                migrate_result = await session.execute(
                    text("""
                        INSERT IGNORE INTO xy_card_item_relations (user_id, card_id, item_id, dock_record_id, created_at, updated_at)
                        SELECT user_id, id, item_id, 0, NOW(), NOW()
                        FROM xy_cards
                        WHERE item_id IS NOT NULL AND item_id != ''
                    """)
                )
                await session.commit()
                
                migrated = migrate_result.rowcount
                logger.info(f"✓ 卡券商品关联数据首次迁移完成：源数据 {total} 条，本次迁移 {migrated} 条")
                
        except Exception as e:
            logger.warning(f"✗ 卡券商品关联数据迁移失败（不影响系统运行）: {e}")

    async def migrate_delivery_block_rules(self):
        """迁移旧禁止发货设置到规则配置表

        对于已开启 delivery_disabled=1 但 xy_delivery_block_rules 表中无记录的账号，
        自动将旧配置迁移为一条 buyer_credit_zero 规则。
        迁移后旧字段保留不删除，但不再使用。
        """
        try:
            async with async_session_maker() as session:
                # 查找已开启旧禁止发货开关的账号
                result = await session.execute(
                    text("""
                        SELECT a.account_id, a.delivery_disabled_reason,
                               a.auto_close_order, a.delivery_only_card_after_close,
                               a.delivery_disabled_excluded_items
                        FROM xy_accounts a
                        WHERE a.delivery_disabled = 1
                        AND NOT EXISTS (
                            SELECT 1 FROM xy_delivery_block_rules r
                            WHERE r.account_id = a.account_id
                        )
                    """)
                )
                rows = result.fetchall()

                if not rows:
                    logger.info("✓ 无需迁移禁止发货规则数据")
                    return

                migrated_count = 0
                for row in rows:
                    account_id = row[0]
                    reason = row[1]
                    auto_close = row[2]
                    only_card = row[3]
                    excluded_items = row[4]

                    # 归一化 excluded_items（可能是 JSON 字符串或 list）
                    excluded_json = None
                    if excluded_items:
                        if isinstance(excluded_items, str):
                            excluded_json = excluded_items  # 已经是 JSON 字符串
                        elif isinstance(excluded_items, list):
                            import json as _json
                            excluded_json = _json.dumps(excluded_items, ensure_ascii=False)

                    try:
                        await session.execute(
                            text("""
                                INSERT IGNORE INTO xy_delivery_block_rules
                                (account_id, rule_code, enabled, priority, block_reason,
                                 auto_close_order, only_card_after_close, excluded_item_ids, config)
                                VALUES
                                (:account_id, 'buyer_credit_zero', 1, 10, :block_reason,
                                 :auto_close, :only_card, :excluded_ids, '{"threshold": 0}')
                            """),
                            {
                                "account_id": account_id,
                                "block_reason": reason,
                                "auto_close": 1 if auto_close else 0,
                                "only_card": 1 if only_card else 0,
                                "excluded_ids": excluded_json,
                            },
                        )
                        migrated_count += 1
                    except Exception as row_err:
                        logger.warning(
                            f"✗ 迁移账号 {account_id} 禁止发货规则失败: {row_err}"
                        )

                await session.commit()
                logger.info(
                    f"✓ 禁止发货规则迁移完成：共 {len(rows)} 个账号，成功迁移 {migrated_count} 条"
                )

        except Exception as e:
            logger.warning(f"✗ 禁止发货规则迁移失败（不影响系统运行）: {e}")

    async def backfill_user_secret_keys(self):
        """为历史用户回填分销秘钥

        存量用户在新增 secret_key 列后值为 NULL，这里在服务启动自检时
        统一为它们生成 32 位随机秘钥（全局唯一），避免依赖用户访问页面才懒生成。
        逐个用户生成并校验唯一性，遇到唯一约束冲突时重试，最多 10 次。
        不影响已有秘钥的用户。
        """
        try:
            async with async_session_maker() as session:
                # 查询所有秘钥为空的用户ID
                result = await session.execute(
                    text("SELECT id FROM xy_users WHERE secret_key IS NULL OR secret_key = ''")
                )
                user_ids = [row[0] for row in result.fetchall()]

                if not user_ids:
                    logger.info("✓ 无需回填分销秘钥")
                    return

                # 预加载已有秘钥，减少唯一性冲突的数据库往返
                existing_result = await session.execute(
                    text("SELECT secret_key FROM xy_users WHERE secret_key IS NOT NULL AND secret_key != ''")
                )
                used_keys = {row[0] for row in existing_result.fetchall()}

                backfilled = 0
                for user_id in user_ids:
                    # 生成不与已知秘钥重复的新秘钥
                    new_key = None
                    for _ in range(10):
                        candidate = generate_secret_key()
                        if candidate not in used_keys:
                            new_key = candidate
                            break
                    if not new_key:
                        logger.warning(f"✗ 用户 {user_id} 分销秘钥生成失败（多次重复），跳过")
                        continue

                    try:
                        await session.execute(
                            text("UPDATE xy_users SET secret_key = :key WHERE id = :uid"),
                            {"key": new_key, "uid": user_id},
                        )
                        used_keys.add(new_key)
                        backfilled += 1
                    except Exception as row_err:
                        logger.warning(f"✗ 回填用户 {user_id} 分销秘钥失败: {row_err}")

                await session.commit()
                logger.info(
                    f"✓ 分销秘钥回填完成：共 {len(user_ids)} 个历史用户，成功回填 {backfilled} 个"
                )

        except Exception as e:
            logger.warning(f"✗ 分销秘钥回填失败（不影响系统运行）: {e}")


async def init_database():
    """初始化数据库（供外部调用）"""
    initializer = DatabaseInitializer()
    await initializer.init_all()


# 如果直接运行此脚本
if __name__ == "__main__":
    import asyncio
    asyncio.run(init_database())
