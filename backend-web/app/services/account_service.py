"""
账号服务

功能：
1. 账号CRUD操作
2. 账号状态管理
3. Cookie更新
4. 扫码登录账号创建/更新
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from common.services.account_limit_service import AccountLimitService
from common.models.xy_account import XYAccount
from common.utils.cookie_refresh import clear_cookie_refresh_snapshot

# UTC时区常量
UTC = timezone.utc


class AccountService:
    """Provides access to legacy cookie account records."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_account_options(self, owner_id: int | None = None) -> list[dict]:
        stmt = select(
            XYAccount.id,
            XYAccount.account_id,
            XYAccount.remark,
            XYAccount.status,
            XYAccount.show_browser,
        ).order_by(XYAccount.account_id)
        if owner_id is not None:
            stmt = stmt.where(XYAccount.owner_id == owner_id)
        result = await self.session.execute(stmt)
        return [
            {
                "pk": row.id,
                "id": row.account_id,
                "remark": row.remark or "",
                "enabled": (row.status or "active").strip().lower() not in {"inactive", "disabled", "suspended", "deleted"},
                "show_browser": bool(row.show_browser),
            }
            for row in result.all()
        ]

    async def list_account_ids(self, owner_id: int | None = None) -> list[str]:
        """获取账号ID列表，owner_id为None时返回所有账号（管理员）"""
        stmt = select(XYAccount.account_id).order_by(XYAccount.account_id)
        if owner_id is not None:
            stmt = stmt.where(XYAccount.owner_id == owner_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_accounts(self, owner_id: int | None = None) -> list[XYAccount]:
        """获取账号列表，owner_id为None时返回所有账号（管理员）"""
        stmt = select(XYAccount).order_by(XYAccount.account_id)
        if owner_id is not None:
            stmt = stmt.where(XYAccount.owner_id == owner_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_accounts_paginated(
        self,
        owner_id: int | None = None,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        ai_reply: bool | None = None,
        scheduled_redelivery: bool | None = None,
        scheduled_rate: bool | None = None,
        auto_polish: bool | None = None,
        auto_confirm: bool | None = None,
        has_password: bool | None = None,
        disable_reason: str | None = None,
        account_id: str | None = None,
    ) -> tuple[list[XYAccount], int]:
        """获取账号列表（分页），支持多条件筛选
        
        Args:
            owner_id: 用户ID，None表示查询所有用户（管理员）
            page: 页码
            page_size: 每页数量
            status: 状态筛选（active/inactive）
            ai_reply: AI回复开关筛选
            scheduled_redelivery: 定时补发货筛选
            scheduled_rate: 定时补评价筛选
            auto_polish: 商品擦亮筛选
            auto_confirm: 自动确认收货筛选
            has_password: 是否配置密码筛选
            disable_reason: 禁用原因模糊搜索关键词（LIKE %keyword%）
            account_id: 账号ID模糊搜索关键词（LIKE %keyword%）
            
        Returns:
            (账号列表, 总数)
        """
        from sqlalchemy import func, and_, or_
        
        base_stmt = select(XYAccount)
        conditions = []
        
        # 用户ID筛选
        if owner_id is not None:
            conditions.append(XYAccount.owner_id == owner_id)
        
        # 状态筛选 - 与 _status_to_enabled 函数保持一致
        # inactive/disabled/suspended/deleted 视为禁用，其他视为启用
        if status is not None:
            inactive_statuses = ["inactive", "disabled", "suspended", "deleted"]
            if status == "active":
                # 启用：status 不在禁用列表中
                conditions.append(~XYAccount.status.in_(inactive_statuses))
            elif status == "inactive":
                # 禁用：status 在禁用列表中
                conditions.append(XYAccount.status.in_(inactive_statuses))
        
        # AI回复筛选（从metadata_json中获取）
        if ai_reply is not None:
            if ai_reply:
                # AI回复开启：兼容 ai_enabled 与历史 enabled 字段
                conditions.append(
                    or_(
                        XYAccount.metadata_json["ai_reply_settings"]["ai_enabled"].as_boolean() == True,
                        XYAccount.metadata_json["ai_reply_settings"]["enabled"].as_boolean() == True,
                    )
                )
            else:
                # AI回复关闭：metadata_json为空，或 ai_enabled/enabled 都未开启
                conditions.append(
                    or_(
                        XYAccount.metadata_json.is_(None),
                        XYAccount.metadata_json["ai_reply_settings"]["ai_enabled"].as_boolean() == False,
                        XYAccount.metadata_json["ai_reply_settings"]["enabled"].as_boolean() == False,
                        and_(
                            XYAccount.metadata_json["ai_reply_settings"]["ai_enabled"].is_(None),
                            XYAccount.metadata_json["ai_reply_settings"]["enabled"].is_(None),
                        )
                    )
                )
        
        # 定时补发货筛选
        if scheduled_redelivery is not None:
            conditions.append(XYAccount.scheduled_redelivery == scheduled_redelivery)
        
        # 定时补评价筛选
        if scheduled_rate is not None:
            conditions.append(XYAccount.scheduled_rate == scheduled_rate)
        
        # 商品擦亮筛选
        if auto_polish is not None:
            conditions.append(XYAccount.auto_polish == auto_polish)
        
        # 自动确认收货筛选
        if auto_confirm is not None:
            conditions.append(XYAccount.auto_confirm == auto_confirm)
        
        # 禁用原因模糊搜索（忽略空白字符串；ilike 大小写不敏感，自动参数化避免 SQL 注入；与项目其它筛选保持风格一致）
        if disable_reason is not None:
            keyword = disable_reason.strip()
            if keyword:
                conditions.append(XYAccount.disable_reason.ilike(f"%{keyword}%"))
        
        # 账号ID模糊搜索（忽略空白字符串；ilike 自动参数化避免 SQL 注入；与禁用原因模糊搜索保持风格一致）
        if account_id is not None:
            account_id_keyword = account_id.strip()
            if account_id_keyword:
                conditions.append(XYAccount.account_id.ilike(f"%{account_id_keyword}%"))
        
        # 是否配置密码筛选（账号和密码都配置了才算已配置）
        if has_password is not None:
            if has_password:
                # 已配置：username和login_password都不为空
                conditions.append(
                    and_(
                        XYAccount.username.isnot(None),
                        XYAccount.username != '',
                        XYAccount.login_password.isnot(None),
                        XYAccount.login_password != ''
                    )
                )
            else:
                # 未配置：username或login_password为空
                conditions.append(
                    or_(
                        XYAccount.username.is_(None),
                        XYAccount.username == '',
                        XYAccount.login_password.is_(None),
                        XYAccount.login_password == ''
                    )
                )
        
        # 应用所有条件
        if conditions:
            base_stmt = base_stmt.where(and_(*conditions))
        
        # 查询总数：直接基于条件统计，避免把整表 SELECT 包进子查询
        count_stmt = select(func.count(XYAccount.id))
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar() or 0
        
        # 分页查询：启用账号排在前面，再按创建时间倒序
        from sqlalchemy import case
        inactive_statuses_list = ["inactive", "disabled", "suspended", "deleted"]
        status_order = case(
            (XYAccount.status.in_(inactive_statuses_list), 1),
            else_=0
        )
        offset = (page - 1) * page_size
        stmt = base_stmt.order_by(status_order, XYAccount.created_at.desc()).offset(offset).limit(page_size)
        result = await self.session.execute(stmt)
        
        return list(result.scalars().all()), total

    async def list_all_accounts(self) -> list[XYAccount]:
        """获取所有账号（用于启动时加载）"""
        stmt = select(XYAccount).order_by(XYAccount.account_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_enabled_accounts(self) -> list[XYAccount]:
        """获取所有启用的账号
        
        Returns:
            启用状态的账号列表
        """
        stmt = (
            select(XYAccount)
            .where(XYAccount.status == "active")
            .order_by(XYAccount.account_id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_account_for_user(self, owner_id: int | None, account_identifier: str) -> XYAccount | None:
        """
        获取指定用户的账号
        
        Args:
            owner_id: 用户ID，如果为 None 则不限制用户（管理员模式）
            account_identifier: 账号标识（支持 account_id 或 unb）
            
        Returns:
            账号对象，如果不存在则返回 None
        """
        # 先按 account_id 精确查询（走 idx_account_id 索引），避免 OR 导致索引失效
        stmt = select(XYAccount).where(XYAccount.account_id == account_identifier)
        if owner_id is not None:
            stmt = stmt.where(XYAccount.owner_id == owner_id)
        result = await self.session.execute(stmt)
        account = result.scalars().first()

        # account_id 未命中时，再按 unb 查询（兼容历史数据）
        if account is None:
            stmt2 = select(XYAccount).where(XYAccount.unb == account_identifier)
            if owner_id is not None:
                stmt2 = stmt2.where(XYAccount.owner_id == owner_id)
            result2 = await self.session.execute(stmt2)
            account = result2.scalars().first()

        return account

    async def get_accounts_for_user(self, owner_id: int | None, account_ids: list[str]) -> list[XYAccount]:
        if not account_ids:
            return []
        stmt = select(XYAccount).where(XYAccount.account_id.in_(account_ids))
        if owner_id is not None:
            stmt = stmt.where(XYAccount.owner_id == owner_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_account_by_identifier(self, account_identifier: str) -> XYAccount | None:
        """根据账号标识获取账号（不限制用户，管理员使用）"""
        stmt = select(XYAccount).where(XYAccount.account_id == account_identifier)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def create_account(
        self,
        owner_id: int,
        account_id: str,
        cookie_value: str,
        *,
        unb: str | None = None,
        login_method: str = "manual",
    ) -> XYAccount:
        existing = await self.get_account_for_user(owner_id, account_id)
        if existing:
            raise ValueError("账户已存在")

        await AccountLimitService(self.session).ensure_can_add_account(owner_id)

        account = XYAccount(
            owner_id=owner_id,
            account_id=account_id,
            cookie=cookie_value,
            login_method=login_method,
            status="active",
            auto_confirm=False,
            pause_duration=10,
            show_browser=False,
            unb=unb,
            last_login_at=datetime.now(tz=UTC),
        )
        self.session.add(account)
        await self.session.commit()
        await self.session.refresh(account)
        return account

    async def update_cookie(self, account: XYAccount, value: str) -> None:
        account.cookie = value
        account.metadata_json = clear_cookie_refresh_snapshot(account.metadata_json)
        self.session.add(account)
        await self.session.commit()

    async def update_status(self, account: XYAccount, enabled: bool, disable_reason: str | None = None) -> None:
        """更新账号状态
        
        Args:
            account: 账号对象
            enabled: 是否启用
            disable_reason: 禁用原因（仅在禁用时有效，启用时会清空）
        """
        account.status = "active" if enabled else "disabled"
        # 启用时清空禁用原因，禁用时设置禁用原因
        account.disable_reason = None if enabled else disable_reason
        self.session.add(account)
        await self.session.commit()

    async def update_remark(self, account: XYAccount, remark: str) -> None:
        account.remark = remark
        self.session.add(account)
        await self.session.commit()

    async def update_auto_confirm(self, account: XYAccount, auto_confirm: bool) -> None:
        account.auto_confirm = auto_confirm
        self.session.add(account)
        await self.session.commit()

    async def update_pause_duration(self, account: XYAccount, duration: int) -> None:
        account.pause_duration = duration
        self.session.add(account)
        await self.session.commit()

    async def update_message_expire_time(self, account: XYAccount, expire_time: int) -> None:
        """更新相同消息等待时间"""
        account.message_expire_time = expire_time
        self.session.add(account)
        await self.session.commit()

    async def update_reply_delay(self, account: XYAccount, delay_seconds: int) -> None:
        """更新自动回复延迟时间(秒)"""
        account.reply_delay_seconds = delay_seconds
        self.session.add(account)
        await self.session.commit()

    async def update_login_info(
        self,
        account: XYAccount,
        username: str | None = None,
        login_password: str | None = None,
        show_browser: bool | None = None,
    ) -> None:
        """更新账号登录信息（用户名、密码、是否显示浏览器）"""
        if username is not None:
            account.username = username
        if login_password is not None:
            account.login_password = login_password
        if show_browser is not None:
            account.show_browser = show_browser
        self.session.add(account)
        await self.session.commit()

    async def update_scheduled_redelivery(self, account: XYAccount, scheduled_redelivery: bool) -> None:
        """更新定时补发货开关"""
        account.scheduled_redelivery = scheduled_redelivery
        self.session.add(account)
        await self.session.commit()

    async def update_scheduled_rate(self, account: XYAccount, scheduled_rate: bool) -> None:
        """更新定时补评价开关"""
        account.scheduled_rate = scheduled_rate
        self.session.add(account)
        await self.session.commit()

    async def delete_account(self, account: XYAccount) -> None:
        await self.session.delete(account)
        await self.session.commit()

    async def get_account_by_unb(self, owner_id: int, unb: str) -> XYAccount | None:
        stmt = select(XYAccount).where(
            XYAccount.owner_id == owner_id,
            XYAccount.unb == unb,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def _generate_unique_account_id(self, owner_id: int, base: str) -> str:
        normalized = base or f"qr_{int(datetime.utcnow().timestamp())}"
        stmt = select(XYAccount.account_id).where(XYAccount.owner_id == owner_id)
        result = await self.session.execute(stmt)
        existing_ids = set(result.scalars().all())
        candidate = normalized
        counter = 1
        while candidate in existing_ids:
            candidate = f"{normalized}_{counter}"
            counter += 1
        return candidate

    async def upsert_account_from_qr(
        self,
        owner_id: int,
        cookies: str,
        unb: str | None,
        *,
        login_method: str = "qr_scan",
    ) -> tuple[XYAccount, bool]:
        account: XYAccount | None = None
        if unb:
            account = await self.get_account_by_unb(owner_id, unb)

        created = False
        if account:
            account.cookie = cookies
            account.metadata_json = clear_cookie_refresh_snapshot(account.metadata_json)
            account.status = "active"
            account.disable_reason = None  # 清空禁用原因
            account.login_method = login_method
            account.unb = unb
            account.last_login_at = datetime.now(tz=UTC)
            if hasattr(account, "updated_at"):
                account.updated_at = datetime.now(tz=UTC)
        else:
            await AccountLimitService(self.session).ensure_can_add_account(owner_id)
            base_id = unb or f"qr_{int(datetime.utcnow().timestamp())}"
            new_id = await self._generate_unique_account_id(owner_id, base_id)
            account = XYAccount(
                owner_id=owner_id,
                account_id=new_id,
                cookie=cookies,
                login_method=login_method,
                status="active",
                auto_confirm=False,
                pause_duration=10,
                show_browser=False,
                unb=unb,
                last_login_at=datetime.now(tz=UTC),
                created_at=datetime.now(tz=UTC),
                updated_at=datetime.now(tz=UTC),
            )
            self.session.add(account)
            created = True

        self.session.add(account)
        await self.session.commit()
        if created:
            await self.session.refresh(account)
        return account, created

    async def update_auto_polish(self, account: XYAccount, auto_polish: bool) -> None:
        """更新商品自动擦亮开关"""
        account.auto_polish = auto_polish
        self.session.add(account)
        await self.session.commit()

    async def update_confirm_before_send(self, account: XYAccount, confirm_before_send: bool) -> None:
        """更新发货成功再发卡券开关（与send_before_confirm互斥）"""
        account.confirm_before_send = confirm_before_send
        if confirm_before_send:
            account.send_before_confirm = False
        self.session.add(account)
        await self.session.commit()

    async def update_send_before_confirm(self, account: XYAccount, send_before_confirm: bool) -> None:
        """更新卡券发送成功再确认发货开关（与confirm_before_send互斥）"""
        account.send_before_confirm = send_before_confirm
        if send_before_confirm:
            account.confirm_before_send = False
        self.session.add(account)
        await self.session.commit()

    async def update_auto_red_flower(self, account: XYAccount, auto_red_flower: bool) -> None:
        """更新自动求小红花开关
        
        使用显式 UPDATE SQL 写入，避开 ORM 脏状态追踪可能的陷阱，
        确保操作一定会发送 UPDATE 语句到数据库。
        """
        stmt = (
            update(XYAccount)
            .where(XYAccount.id == account.id)
            .values(auto_red_flower=auto_red_flower)
        )
        await self.session.execute(stmt)
        await self.session.commit()
        # 同步内存对象属性（expire_on_commit=False 下对象属性不会自动刷新）
        account.auto_red_flower = auto_red_flower

    async def update_ai_reply_block_ordered_users(self, account: XYAccount, ai_reply_block_ordered_users: bool) -> None:
        """更新已下单用户禁止AI回复开关
        
        使用显式 UPDATE SQL 写入，确保操作一定会发送 UPDATE 语句到数据库。
        
        Args:
            account: 账号对象
            ai_reply_block_ordered_users: 是否禁止对已下单用户进行AI回复
        """
        stmt = (
            update(XYAccount)
            .where(XYAccount.id == account.id)
            .values(ai_reply_block_ordered_users=ai_reply_block_ordered_users)
        )
        await self.session.execute(stmt)
        await self.session.commit()
        # 同步内存对象属性（expire_on_commit=False 下对象属性不会自动刷新）
        account.ai_reply_block_ordered_users = ai_reply_block_ordered_users

    async def update_delivery_disabled(
        self,
        account: XYAccount,
        delivery_disabled: bool,
        delivery_disabled_reason: str | None,
        auto_close_order: bool = False,
        delivery_only_card_after_close: bool = False,
        excluded_item_ids: list[str] | None = None,
    ) -> None:
        """更新禁止发货设置（开关 + 原因 + 主动关闭订单 + 关闭后只发卡券 + 排除商品列表）

        使用显式 UPDATE SQL 写入，避免 ORM 脏状态追踪可能导致字段未落库。

        联动规则（与前端 UI 一致）：
          - 禁止发货关闭：reason / auto_close_order / delivery_only_card_after_close
            全部强制 False；排除商品列表强制清空
          - auto_close_order 关闭：delivery_only_card_after_close 强制 False
            （"关闭订单后继续发货"以"先关闭订单"为前置）

        Args:
            account: 账号实例
            delivery_disabled: 禁止发货开关
            delivery_disabled_reason: 禁止发货原因（开关关闭时会被清空）
            auto_close_order: 主动关闭订单开关
            delivery_only_card_after_close: 关闭订单后继续发货（仅发卡券）
            excluded_item_ids: 排除商品 item_id 列表（开关关闭时会被清空；列表内自动
                去重、去除空白、保留输入顺序）
        """
        normalized_reason: str | None
        # 排除列表归一化：去空白 + 去重 + 保持顺序；上限 500 个，避免 JSON 过大
        normalized_excluded: list[str] = []
        if excluded_item_ids:
            seen: set[str] = set()
            for raw in excluded_item_ids:
                if raw is None:
                    continue
                item_id = str(raw).strip()
                if not item_id or item_id in seen:
                    continue
                seen.add(item_id)
                normalized_excluded.append(item_id)
                if len(normalized_excluded) >= 500:
                    break

        if not delivery_disabled:
            normalized_reason = None
            normalized_auto_close = False
            normalized_only_card = False
            # 禁止发货关闭时，排除商品列表也强制清空，避免遗留无效配置
            normalized_excluded = []
        else:
            reason = (delivery_disabled_reason or "").strip()
            normalized_reason = reason or None
            normalized_auto_close = bool(auto_close_order)
            # 主动关闭订单关闭时，"关闭后只发卡券"必须强制关闭
            normalized_only_card = bool(delivery_only_card_after_close) if normalized_auto_close else False

        # JSON 字段写入：MySQL 接受 None 表示 NULL；空列表用 None 存以节省空间
        normalized_excluded_for_db: list[str] | None = normalized_excluded if normalized_excluded else None

        stmt = (
            update(XYAccount)
            .where(XYAccount.id == account.id)
            .values(
                delivery_disabled=delivery_disabled,
                delivery_disabled_reason=normalized_reason,
                auto_close_order=normalized_auto_close,
                delivery_only_card_after_close=normalized_only_card,
                delivery_disabled_excluded_items=normalized_excluded_for_db,
            )
        )
        await self.session.execute(stmt)

        # 同步写入新规则表（buyer_credit_zero 规则）
        from common.models.xy_delivery_block_rule import XYDeliveryBlockRule
        from sqlalchemy import and_

        rule_stmt = select(XYDeliveryBlockRule).where(
            and_(
                XYDeliveryBlockRule.account_id == account.account_id,
                XYDeliveryBlockRule.rule_code == "buyer_credit_zero",
            )
        )
        result = await self.session.execute(rule_stmt)
        existing_rule = result.scalars().first()

        if existing_rule:
            existing_rule.enabled = delivery_disabled
            existing_rule.block_reason = normalized_reason
            existing_rule.auto_close_order = normalized_auto_close
            existing_rule.only_card_after_close = normalized_only_card
            existing_rule.excluded_item_ids = normalized_excluded_for_db
        else:
            new_rule = XYDeliveryBlockRule(
                account_id=account.account_id,
                rule_code="buyer_credit_zero",
                enabled=delivery_disabled,
                priority=10,
                block_reason=normalized_reason,
                auto_close_order=normalized_auto_close,
                only_card_after_close=normalized_only_card,
                excluded_item_ids=normalized_excluded_for_db,
                config={"threshold": 0},
            )
            self.session.add(new_rule)

        await self.session.commit()
        # 同步内存对象属性
        account.delivery_disabled = delivery_disabled
        account.delivery_disabled_reason = normalized_reason
        account.auto_close_order = normalized_auto_close
        account.delivery_only_card_after_close = normalized_only_card
        account.delivery_disabled_excluded_items = normalized_excluded_for_db

    async def get_delivery_block_rules(self, account_id: str) -> list[dict]:
        """获取账号的禁止发货规则列表

        返回该账号所有规则配置（包括未启用的），按 priority 排序。
        如果账号在 xy_delivery_block_rules 表中没有记录，返回所有可用规则的默认配置。

        Args:
            account_id: 账号标识（xy_accounts.account_id）

        Returns:
            规则配置列表
        """
        from common.models.xy_delivery_block_rule import XYDeliveryBlockRule
        from common.services.delivery_block_rule_meta import get_all_rule_metadata

        # 查询已有规则
        stmt = (
            select(XYDeliveryBlockRule)
            .where(XYDeliveryBlockRule.account_id == account_id)
            .order_by(XYDeliveryBlockRule.priority.asc())
        )
        result = await self.session.execute(stmt)
        existing_rules = result.scalars().all()

        # 构建已有规则的 code 集合
        existing_codes = {r.rule_code for r in existing_rules}

        # 获取所有可用规则元信息
        all_metadata = get_all_rule_metadata()

        # 合并：已有规则 + 未配置的规则（用默认值填充）
        rule_list = []
        for rule in existing_rules:
            # 归一化 excluded_item_ids
            excluded = []
            if rule.excluded_item_ids:
                raw = rule.excluded_item_ids
                if isinstance(raw, str):
                    try:
                        import json
                        raw = json.loads(raw)
                    except Exception:
                        raw = []
                if isinstance(raw, list):
                    excluded = [str(x).strip() for x in raw if x is not None and str(x).strip()]

            rule_list.append({
                "rule_code": rule.rule_code,
                "rule_name": next(
                    (m["rule_name"] for m in all_metadata if m["rule_code"] == rule.rule_code),
                    rule.rule_code,
                ),
                "rule_description": next(
                    (m["rule_description"] for m in all_metadata if m["rule_code"] == rule.rule_code),
                    "",
                ),
                "enabled": rule.enabled,
                "priority": rule.priority,
                "block_reason": rule.block_reason or "",
                "auto_close_order": bool(rule.auto_close_order),
                "only_card_after_close": bool(rule.only_card_after_close),
                "excluded_item_ids": excluded,
                "config": rule.config or {},
                "default_config": next(
                    (m["default_config"] for m in all_metadata if m["rule_code"] == rule.rule_code),
                    {},
                ),
            })

        # 补充未配置的规则（默认关闭）
        for meta in all_metadata:
            if meta["rule_code"] not in existing_codes:
                rule_list.append({
                    "rule_code": meta["rule_code"],
                    "rule_name": meta["rule_name"],
                    "rule_description": meta["rule_description"],
                    "enabled": False,
                    "priority": meta["default_priority"],
                    "block_reason": "",
                    "auto_close_order": False,
                    "only_card_after_close": False,
                    "excluded_item_ids": [],
                    "config": meta["default_config"],
                    "default_config": meta["default_config"],
                })

        # 按 priority 排序
        rule_list.sort(key=lambda x: x["priority"])
        return rule_list

    async def update_delivery_block_rules(
        self,
        account_id: str,
        rules: list,
    ) -> None:
        """批量更新账号的禁止发货规则配置

        使用 UPSERT 逻辑：存在则更新，不存在则插入。

        Args:
            account_id: 账号标识（xy_accounts.account_id）
            rules: 规则配置列表（DeliveryBlockRuleItem 实例列表）
        """
        from common.models.xy_delivery_block_rule import XYDeliveryBlockRule
        from sqlalchemy import and_

        for rule_item in rules:
            rule_code = rule_item.rule_code
            enabled = rule_item.enabled
            priority = rule_item.priority
            block_reason = (rule_item.block_reason or "").strip() or None
            auto_close = rule_item.auto_close_order
            only_card = rule_item.only_card_after_close if auto_close else False

            # 归一化排除商品列表
            excluded_list: list[str] = []
            if rule_item.excluded_item_ids:
                seen: set[str] = set()
                for raw in rule_item.excluded_item_ids:
                    if raw is None:
                        continue
                    item_id = str(raw).strip()
                    if not item_id or item_id in seen:
                        continue
                    seen.add(item_id)
                    excluded_list.append(item_id)
                    if len(excluded_list) >= 500:
                        break
            excluded_for_db = excluded_list if excluded_list else None

            # 规则参数
            config = rule_item.config if rule_item.config else None

            # 查询是否已存在
            stmt = select(XYDeliveryBlockRule).where(
                and_(
                    XYDeliveryBlockRule.account_id == account_id,
                    XYDeliveryBlockRule.rule_code == rule_code,
                )
            )
            result = await self.session.execute(stmt)
            existing = result.scalars().first()

            if existing:
                # 更新
                existing.enabled = enabled
                existing.priority = priority
                existing.block_reason = block_reason
                existing.auto_close_order = auto_close
                existing.only_card_after_close = only_card
                existing.excluded_item_ids = excluded_for_db
                existing.config = config
            else:
                # 插入
                new_rule = XYDeliveryBlockRule(
                    account_id=account_id,
                    rule_code=rule_code,
                    enabled=enabled,
                    priority=priority,
                    block_reason=block_reason,
                    auto_close_order=auto_close,
                    only_card_after_close=only_card,
                    excluded_item_ids=excluded_for_db,
                    config=config,
                )
                self.session.add(new_rule)

        # 同步更新旧字段 delivery_disabled（用于前端图标显示兼容）
        # 只要有任何一条规则 enabled=True，旧字段就标记为 True
        has_any_enabled = any(r.enabled for r in rules)
        sync_stmt = (
            update(XYAccount)
            .where(XYAccount.account_id == account_id)
            .values(delivery_disabled=has_any_enabled)
        )
        await self.session.execute(sync_stmt)

        await self.session.commit()
