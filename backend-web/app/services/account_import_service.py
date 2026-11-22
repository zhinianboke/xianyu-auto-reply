"""
账号数据导入服务

功能：
1. 解析导出的Excel文件（openpyxl）
2. 按 Sheet 导入数据并统一提交；权限或数据库失败时回滚本次写入
3. 支持两种模式：保存（按Excel状态）/ 保存并全部启用
4. 返回导入统计结果
"""
from __future__ import annotations

from io import BytesIO

from loguru import logger
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.xy_account import XYAccount
from common.models.xy_keyword_rule import XYKeywordRule
from common.models.xy_catalog_item import XYCatalogItem
from app.services.account_import_cards import AccountCardImportMixin
from app.services.account_import_settings import AccountSettingsImportMixin
from app.services.account_import_parsing import _parse_bool, _parse_int, _parse_json, _parse_str, _read_sheet_rows
from app.services.websocket_client import websocket_client
from common.services.card_access import CardAccessError
from common.utils.time_utils import get_beijing_now_naive


class AccountImportService(AccountCardImportMixin, AccountSettingsImportMixin):
    """账号数据导入服务"""

    def __init__(self, session: AsyncSession, owner_id: int):
        self.session = session
        self.owner_id = owner_id
        self.inserted = 0
        self.updated = 0
        self.started = 0
        self.failed = 0
        self.errors: list[str] = []
        # 导入过程中的映射缓存
        self._account_id_to_pk: dict[str, int] = {}
        self._card_name_spec_to_id: dict[str, int] = {}

    async def import_accounts(
        self,
        file_content: bytes,
        enable_all: bool = False,
    ) -> dict:
        """导入账号数据

        Args:
            file_content: Excel文件内容
            enable_all: 是否全部启用

        Returns:
            导入结果统计
        """
        try:
            wb = load_workbook(BytesIO(file_content), read_only=True, data_only=True)
        except Exception as e:
            return {
                "success": False,
                "code": 40001,
                "message": f"Excel文件解析失败: {str(e)}",
                "data": None,
            }

        committing = False
        try:
            # 各 Sheet 只 flush，关联校验完成前不得提交前面的账号或卡券。
            await self._import_accounts_basic(wb, enable_all)
            await self._import_account_switches(wb)
            await self._import_ai_settings(wb)
            await self._import_catalog_items(wb)
            await self._import_cards(wb)
            await self._import_card_item_relations(wb)
            await self._import_keyword_rules(wb)
            await self._import_default_replies(wb)
            await self._import_message_filters(wb)
            await self._import_confirm_receipt(wb)
            await self._import_auto_rate(wb)

            # 先获取本次账号列表，提交成功后才允许请求消息服务启动账号。
            accounts_to_start = await self._get_accounts_to_start(enable_all)
            committing = True
            await self.session.commit()

        except CardAccessError as e:
            logger.exception("卡券关联导入被拒绝：owner_id={}，原因={}", self.owner_id, e)
            rollback_error = await self._rollback_failed_import()
            message = (
                f"导入已停止，回滚未能完成，请人工核实，勿重复导入：{e}；{rollback_error}"
                if rollback_error else f"导入已取消，本次数据未保存：{e}"
            )
            return {"success": False, "code": 40001, "message": message, "data": None}
        except Exception as e:
            logger.exception("账号导入失败：owner_id={}，提交阶段={}，原因={}", self.owner_id, committing, e)
            rollback_error = await self._rollback_failed_import()
            message = (
                f"导入提交失败，结果不确定，请人工核实，勿重复导入：{e}"
                if committing else f"导入已取消，本次数据未保存：{e}"
            )
            if rollback_error:
                message = f"导入已停止，结果需人工核实，勿重复导入：{e}；{rollback_error}" if not committing else f"{message}；{rollback_error}"
            return {"success": False, "code": 40001, "message": message, "data": None}
        finally:
            wb.close()

        # 数据提交和外部启动分开；启动失败明确说明数据已保存，不伪称回滚成功。
        for account_id, cookie in accounts_to_start:
            try:
                await self._start_account(account_id, cookie)
                self.started += 1
            except Exception as e:
                logger.exception("导入数据已保存，但账号启动失败：owner_id={}，account_id={}", self.owner_id, account_id)
                self.errors.append(f"账号 {account_id} 启动失败（导入数据已保存）: {e}")

        message = (
            f"导入完成：新增 {self.inserted} 个，更新 {self.updated} 个，"
            f"启动 {self.started} 个，失败 {self.failed} 个"
        )
        return {
            "success": True,
            "code": 200,
            "message": message,
            "data": {
                "inserted": self.inserted,
                "updated": self.updated,
                "started": self.started,
                "failed": self.failed,
                "errors": self.errors[:20],  # 最多返回20条错误
            },
        }

    # ==================== 各Sheet导入逻辑 ====================

    async def _rollback_failed_import(self) -> str | None:
        """回滚失败导入；回滚异常保留原始错误并关闭失效会话，返回需展示的收尾错误。"""
        try:
            await self.session.rollback()
            return None
        except Exception as error:
            logger.exception("导入回滚失败：owner_id={}", self.owner_id)
            message = f"回滚失败：{error}"
            try:
                await self.session.close()
            except Exception as close_error:
                logger.exception("失效导入会话关闭失败：owner_id={}", self.owner_id)
                message += f"；会话关闭失败：{close_error}"
            return message

    async def _import_accounts_basic(self, wb, enable_all: bool) -> None:
        """导入账号基本信息"""
        rows = _read_sheet_rows(wb, "账号基本信息")
        for row in rows:
            account_id = _parse_str(row.get("账号ID"))
            if not account_id:
                continue

            cookie = _parse_str(row.get("Cookie"))
            if not cookie:
                self.errors.append(f"账号 {account_id}: Cookie为空，跳过")
                self.failed += 1
                continue

            # 确定状态
            status = _parse_str(row.get("状态")) or "active"
            if enable_all:
                status = "active"

            # 查询是否已存在
            stmt = select(XYAccount).where(
                XYAccount.account_id == account_id,
                XYAccount.owner_id == self.owner_id,
            )
            result = await self.session.execute(stmt)
            existing = result.scalars().first()

            if existing:
                # 更新
                existing.cookie = cookie
                existing.status = status
                existing.remark = _parse_str(row.get("备注")) or existing.remark
                existing.username = _parse_str(row.get("用户名")) or existing.username
                existing.login_password = _parse_str(row.get("登录密码")) or existing.login_password
                existing.pause_duration = _parse_int(row.get("暂停时长(秒)"), existing.pause_duration)
                existing.message_expire_time = _parse_int(row.get("相同消息等待时间(秒)"), existing.message_expire_time)
                existing.show_browser = _parse_bool(row.get("显示浏览器"))
                existing.proxy_type = _parse_str(row.get("代理类型")) or existing.proxy_type
                existing.proxy_host = _parse_str(row.get("代理地址")) or existing.proxy_host
                existing.proxy_port = _parse_int(row.get("代理端口"), existing.proxy_port or 0) or None
                existing.proxy_user = _parse_str(row.get("代理用户名")) or existing.proxy_user
                existing.proxy_pass = _parse_str(row.get("代理密码")) or existing.proxy_pass
                if enable_all:
                    existing.disable_reason = None
                self.session.add(existing)
                self._account_id_to_pk[account_id] = existing.id
                self.updated += 1
            else:
                # 全局唯一校验：account_id 若已被其他用户占用，跳过并记录错误（不插入，避免触发唯一约束）
                dup_stmt = select(XYAccount.id).where(XYAccount.account_id == account_id)
                dup_result = await self.session.execute(dup_stmt)
                if dup_result.scalars().first() is not None:
                    self.errors.append(f"账号 {account_id}: 账号ID已被其他用户占用，跳过")
                    self.failed += 1
                    continue
                # 新增
                account = XYAccount(
                    owner_id=self.owner_id,
                    account_id=account_id,
                    cookie=cookie,
                    login_method="import",
                    status=status,
                    remark=_parse_str(row.get("备注")),
                    username=_parse_str(row.get("用户名")),
                    login_password=_parse_str(row.get("登录密码")),
                    pause_duration=_parse_int(row.get("暂停时长(秒)"), 10),
                    message_expire_time=_parse_int(row.get("相同消息等待时间(秒)"), 3600),
                    show_browser=_parse_bool(row.get("显示浏览器")),
                    proxy_type=_parse_str(row.get("代理类型")) or "none",
                    proxy_host=_parse_str(row.get("代理地址")) or None,
                    proxy_port=_parse_int(row.get("代理端口"), 0) or None,
                    proxy_user=_parse_str(row.get("代理用户名")) or None,
                    proxy_pass=_parse_str(row.get("代理密码")) or None,
                )
                self.session.add(account)
                self.inserted += 1

            await self.session.flush()

            # 刷新后获取PK
            if account_id not in self._account_id_to_pk:
                stmt2 = select(XYAccount.id).where(
                    XYAccount.account_id == account_id,
                    XYAccount.owner_id == self.owner_id,
                )
                r = await self.session.execute(stmt2)
                pk = r.scalar_one_or_none()
                if pk:
                    self._account_id_to_pk[account_id] = pk

        await self.session.flush()

    async def _import_account_switches(self, wb) -> None:
        """导入账号开关配置"""
        rows = _read_sheet_rows(wb, "账号开关配置")
        for row in rows:
            account_id = _parse_str(row.get("账号ID"))
            if not account_id:
                continue
            stmt = select(XYAccount).where(
                XYAccount.account_id == account_id,
                XYAccount.owner_id == self.owner_id,
            )
            result = await self.session.execute(stmt)
            account = result.scalars().first()
            if not account:
                continue

            account.auto_confirm = _parse_bool(row.get("自动确认收货"))
            account.scheduled_redelivery = _parse_bool(row.get("定时补发货"))
            account.scheduled_rate = _parse_bool(row.get("定时补评价"))
            account.auto_polish = _parse_bool(row.get("商品擦亮"))
            account.confirm_before_send = _parse_bool(row.get("发货成功再发卡券"))
            account.send_before_confirm = _parse_bool(row.get("卡券发送成功再确认发货"))
            account.only_send_card = _parse_bool(row.get("只发卡券不确认发货"))
            # 只发卡券与自动确认、两种确认顺序互斥，兼容手工编辑导致的冲突配置。
            # 只发卡券优先；否则保留“发货成功再发卡券”优先级，清掉冲突的后置确认。
            if account.only_send_card:
                account.auto_confirm = False
                account.confirm_before_send = False
                account.send_before_confirm = False
            elif account.confirm_before_send:
                account.send_before_confirm = False
            account.auto_red_flower = _parse_bool(row.get("自动求小红花"))
            account.delivery_disabled = _parse_bool(row.get("禁止发货"))
            account.delivery_disabled_reason = _parse_str(row.get("禁止发货原因")) or None
            account.auto_close_order = _parse_bool(row.get("主动关闭订单"))
            account.delivery_only_card_after_close = _parse_bool(row.get("关闭后发卡券"))
            excluded = _parse_json(row.get("禁止发货排除商品"))
            if isinstance(excluded, list):
                account.delivery_disabled_excluded_items = excluded
            self.session.add(account)

        await self.session.flush()

    async def _import_ai_settings(self, wb) -> None:
        """导入AI回复设置"""
        rows = _read_sheet_rows(wb, "AI回复设置")
        for row in rows:
            account_id = _parse_str(row.get("账号ID"))
            if not account_id:
                continue
            ai_json = _parse_json(row.get("AI回复设置JSON"))
            if not ai_json:
                continue
            stmt = select(XYAccount).where(
                XYAccount.account_id == account_id,
                XYAccount.owner_id == self.owner_id,
            )
            result = await self.session.execute(stmt)
            account = result.scalars().first()
            if not account:
                continue

            metadata = account.metadata_json or {}
            metadata["ai_reply_settings"] = ai_json
            account.metadata_json = metadata
            self.session.add(account)

        await self.session.flush()

    async def _import_catalog_items(self, wb) -> None:
        """导入商品目录"""
        rows = _read_sheet_rows(wb, "商品目录")
        for row in rows:
            account_id = _parse_str(row.get("账号ID"))
            item_id = _parse_str(row.get("商品ID"))
            if not account_id or not item_id:
                continue
            account_pk = self._account_id_to_pk.get(account_id)
            if not account_pk:
                continue

            stmt = select(XYCatalogItem).where(
                XYCatalogItem.account_pk == account_pk,
                XYCatalogItem.item_id == item_id,
            )
            result = await self.session.execute(stmt)
            existing = result.scalars().first()

            if existing:
                existing.title = _parse_str(row.get("标题")) or existing.title
                existing.price = _parse_str(row.get("价格")) or existing.price
                existing.ai_prompt = _parse_str(row.get("AI提示词")) or existing.ai_prompt
            else:
                item = XYCatalogItem(
                    owner_id=self.owner_id,
                    account_pk=account_pk,
                    item_id=item_id,
                    title=_parse_str(row.get("标题")),
                    price=_parse_str(row.get("价格")),
                    ai_prompt=_parse_str(row.get("AI提示词")) or None,
                    created_at=get_beijing_now_naive(),
                )
                self.session.add(item)

        await self.session.flush()

    async def _import_keyword_rules(self, wb) -> None:
        """导入关键词规则"""
        rows = _read_sheet_rows(wb, "关键词规则")
        for row in rows:
            account_id = _parse_str(row.get("账号ID"))
            keyword = _parse_str(row.get("关键词"))
            if not account_id or not keyword:
                continue
            account_pk = self._account_id_to_pk.get(account_id)
            if not account_pk:
                continue

            item_id = _parse_str(row.get("商品ID")) or None

            stmt = select(XYKeywordRule).where(
                XYKeywordRule.account_pk == account_pk,
                XYKeywordRule.keyword == keyword,
            )
            if item_id:
                stmt = stmt.where(XYKeywordRule.item_id == item_id)
            else:
                stmt = stmt.where((XYKeywordRule.item_id.is_(None)) | (XYKeywordRule.item_id == ""))

            result = await self.session.execute(stmt)
            existing = result.scalars().first()

            if existing:
                existing.reply_content = _parse_str(row.get("回复内容")) or existing.reply_content
                existing.reply_type = _parse_str(row.get("回复类型")) or existing.reply_type
                existing.image_url = _parse_str(row.get("图片URL")) or existing.image_url
                existing.location_name = _parse_str(row.get("定位名称")) or existing.location_name
                existing.location_longitude = _parse_str(row.get("经度")) or existing.location_longitude
                existing.location_latitude = _parse_str(row.get("纬度")) or existing.location_latitude
                existing.location_title = _parse_str(row.get("位置标题")) or existing.location_title
                existing.location_subtitle = _parse_str(row.get("位置副标题")) or existing.location_subtitle
                existing.priority = _parse_int(row.get("优先级"), existing.priority)
                existing.is_active = _parse_bool(row.get("启用"))
            else:
                rule = XYKeywordRule(
                    owner_id=self.owner_id,
                    account_pk=account_pk,
                    keyword=keyword,
                    reply_content=_parse_str(row.get("回复内容")) or None,
                    reply_type=_parse_str(row.get("回复类型")) or "text",
                    image_url=_parse_str(row.get("图片URL")) or None,
                    location_name=_parse_str(row.get("定位名称")) or None,
                    location_longitude=_parse_str(row.get("经度")) or None,
                    location_latitude=_parse_str(row.get("纬度")) or None,
                    location_title=_parse_str(row.get("位置标题")) or None,
                    location_subtitle=_parse_str(row.get("位置副标题")) or None,
                    item_id=item_id,
                    priority=_parse_int(row.get("优先级"), 100),
                    is_active=_parse_bool(row.get("启用")),
                )
                self.session.add(rule)

        await self.session.flush()

    # ==================== 启动逻辑 ====================

    async def _get_accounts_to_start(self, enable_all: bool) -> list[tuple[str, str]]:
        """获取需要启动的账号列表 [(account_id, cookie)]"""
        stmt = select(XYAccount.account_id, XYAccount.cookie, XYAccount.status).where(
            XYAccount.owner_id == self.owner_id,
            XYAccount.account_id.in_(list(self._account_id_to_pk.keys())),
        )
        result = await self.session.execute(stmt)
        accounts_to_start = []
        for account_id, cookie, status in result.all():
            if not cookie or not cookie.strip():
                continue
            if enable_all or status == "active":
                accounts_to_start.append((account_id, cookie))
        return accounts_to_start

    async def _start_account(self, account_id: str, cookie: str) -> None:
        """启动单个账号的WebSocket任务"""
        result = await websocket_client.start_account(account_id, cookie, self.owner_id)
        if isinstance(result, dict) and not result.get("success", True):
            raise Exception(result.get("message", "启动失败"))
