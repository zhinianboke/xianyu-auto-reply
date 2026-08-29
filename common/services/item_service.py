"""
商品服务

功能：
1. 商品目录CRUD操作
2. 商品信息更新（标题、价格、描述等）
3. 商品列表查询
4. 批量删除商品
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any, Dict, Optional, Set

from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from common.db.redis_client import distributed_lock
from common.models.xy_account import XYAccount
from common.models.xy_catalog_item import XYCatalogItem
from common.models.default_reply import DefaultReply
from common.models.card import Card


class ItemService:
    """Read/write operations for catalog items."""

    def __init__(self, session: AsyncSession):
        self.session = session
        # 账号是否鱼小铺的实例级缓存，避免同一请求内对同一账号重复调用 preget 检测
        self._fish_shop_cache: dict[str, bool] = {}

    async def _resolve_item_fetch_manager(self, account: XYAccount):
        """按账号类型选择商品抓取器：鱼小铺走卖家平台接口，普通账号走个人版接口。

        参照单品发布界面的能力检测（detect_publish_account_capability，优先调用鱼小铺卖家后台
        mtop.idle.pc.backend.idleitem.preget，不可用时回落个人版 mtop.idle.pc.idleitem.preget）
        判定是否开通鱼小铺；检测失败/无法识别时回退个人版接口。

        Args:
            account: 账号对象。
        Returns:
            与 ItemInfoManager 接口对齐的抓取器实例（ItemInfoManager 或 SellerItemInfoManager）。
        """
        from common.utils.item_info_manager import ItemInfoManager
        from common.services.xianyu_seller_item_client import SellerItemInfoManager

        is_fish_shop = self._fish_shop_cache.get(account.account_id)
        if is_fish_shop is None:
            is_fish_shop = await self._detect_is_fish_shop(account)
            self._fish_shop_cache[account.account_id] = is_fish_shop

        if is_fish_shop:
            logger.info(f"账号[{account.account_id}]为鱼小铺，使用卖家平台接口获取商品")
            return SellerItemInfoManager(
                account.account_id, account.cookie, owner_id=account.owner_id
            )

        logger.info(f"账号[{account.account_id}]为普通账号，使用个人版接口获取商品")
        return ItemInfoManager(account.account_id, account.cookie)

    async def _detect_is_fish_shop(self, account: XYAccount) -> bool:
        """检测账号是否开通鱼小铺；检测失败或无法识别时回退为普通账号（False）。

        注意：检测过程中 mtop 可能因令牌过期而刷新 _m_h5_tk，但 mtop_call 仅在调用成功时
        才把新 Cookie 写回数据库。因此这里无论成败都要把 cookies_str 回填到 account，
        否则紧随其后的商品抓取仍用旧令牌，会白跑一次「令牌过期→重试」。
        """
        from common.services.xianyu_publish_service import detect_publish_account_capability

        try:
            result = await detect_publish_account_capability(
                cookie=account.cookie,
                account_id=account.account_id,
                owner_id=account.owner_id,
            )
        except Exception as exc:
            logger.warning(
                f"账号[{account.account_id}]鱼小铺检测异常，回退个人版接口获取商品: {exc}"
            )
            return False

        self._sync_account_cookie(account, result.get("cookies_str"))

        if not result.get("success"):
            logger.warning(
                f"账号[{account.account_id}]鱼小铺检测失败，回退个人版接口获取商品: "
                f"{result.get('message') or '未知原因'}"
            )
            return False

        return bool(result.get("is_fish_shop"))

    @staticmethod
    def _sync_account_cookie(account: XYAccount, latest_cookie: Optional[str]) -> None:
        """把检测/请求过程中刷新出的最新 Cookie 回填到账号对象，供后续请求复用。

        Args:
            account: 账号对象（ORM 实例，随本次会话提交一并持久化）。
            latest_cookie: 最新 Cookie 字符串；为空或未变化时不处理。
        """
        latest = (latest_cookie or "").strip()
        if not latest or latest == (account.cookie or ""):
            return
        account.cookie = latest
        logger.info(f"账号[{account.account_id}]检测期间令牌已刷新，后续商品抓取改用新Cookie")

    def _resolve_account_fetch_user_id(self, account: XYAccount) -> str:
        from common.utils.xianyu_utils import extract_account_user_id_from_cookie

        cookie_user_id = extract_account_user_id_from_cookie(account.cookie)
        stored_user_id = str(account.unb or "").strip()
        fallback_user_id = str(account.account_id or "").strip()
        resolved_user_id = cookie_user_id or stored_user_id or fallback_user_id

        if cookie_user_id and cookie_user_id != stored_user_id:
            logger.warning(
                f"账号[{account.account_id}]库内unb[{stored_user_id or '-'}]与当前Cookie账号[{cookie_user_id}]不一致，本次同步将按Cookie账号抓取商品"
            )

        return resolved_user_id

    def _collect_valid_item_entries(self, items: list[dict]) -> tuple[list[tuple[str, dict]], int]:
        valid_items = []
        skipped_count = 0
        for item in items:
            item_id = str(item.get("id") or "").strip()
            if not item_id or item_id.startswith("auto_"):
                skipped_count += 1
                continue
            valid_items.append((item_id, item))
        return valid_items, skipped_count

    async def _get_existing_item_map(
        self,
        account: XYAccount,
        item_ids: list[str],
    ) -> dict[str, XYCatalogItem]:
        if not item_ids:
            return {}

        stmt = select(XYCatalogItem).where(
            XYCatalogItem.owner_id == account.owner_id,
            XYCatalogItem.account_pk == account.id,
            XYCatalogItem.item_id.in_(item_ids),
        )
        existing_rows = (await self.session.execute(stmt)).scalars().all()
        return {row.item_id: row for row in existing_rows}

    async def get_existing_item_ids_for_account(
        self,
        account: XYAccount,
        item_ids: list[str],
    ) -> set[str]:
        """返回指定账号本地商品库中实际存在的商品 ID 集合。

        Args:
            account: 已完成用户权限校验的账号对象。
            item_ids: 待校验的商品 ID 列表。
        Returns:
            同时属于该账号且存在于本地商品库的商品 ID 集合。
        """
        return set((await self._get_existing_item_map(account, item_ids)).keys())

    async def list_items(self, owner_id: int | None, account_id: str | None = None) -> list[dict]:
        """获取商品列表
        
        Args:
            owner_id: 用户ID，None表示查询所有用户（管理员）
            account_id: 账号ID（可选）
        """
        stmt = (
            select(XYCatalogItem, XYAccount.account_id)
            .outerjoin(XYAccount, XYCatalogItem.account_pk == XYAccount.id)
            .order_by(XYCatalogItem.created_at.desc())
        )
        if owner_id is not None:
            stmt = stmt.where(XYCatalogItem.owner_id == owner_id)
        if account_id:
            stmt = stmt.where(XYAccount.account_id == account_id)
        rows = await self.session.execute(stmt)
        items_data = rows.all()
        
        # 批量查询所有商品的默认回复状态和卡券状态
        default_reply_map = await self._get_default_reply_status_batch(items_data)
        card_set = await self._get_card_status_batch(items_data)
        
        return [self._serialize_item(item, acct_id, default_reply_map.get((acct_id, item.item_id)), item.item_id in card_set) for item, acct_id in items_data]

    async def list_items_paginated(
        self,
        owner_id: int | None,
        account_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
        is_polished: bool | None = None,
        is_multi_spec: bool | None = None,
        multi_quantity_delivery: bool | None = None,
    ) -> tuple[list[dict], int]:
        """获取商品列表（分页），支持多条件筛选
        
        Args:
            owner_id: 用户ID，None表示查询所有用户（管理员）
            account_id: 账号ID（可选）
            page: 页码
            page_size: 每页数量
            keyword: 关键字（支持商品ID、标题、详情）
            is_polished: 是否擦亮筛选
            is_multi_spec: 多规格筛选
            multi_quantity_delivery: 多数量发货筛选
            
        Returns:
            (商品列表, 总数)
        """
        from sqlalchemy import String, and_, cast, func, or_
        
        base_stmt = (
            select(XYCatalogItem, XYAccount.account_id)
            .outerjoin(XYAccount, XYCatalogItem.account_pk == XYAccount.id)
        )
        
        conditions = []
        if owner_id is not None:
            conditions.append(XYCatalogItem.owner_id == owner_id)
        if account_id:
            conditions.append(XYAccount.account_id == account_id)
        if keyword and keyword.strip():
            keyword_like = f"%{keyword.strip()}%"
            conditions.append(
                or_(
                    XYCatalogItem.item_id.like(keyword_like),
                    XYCatalogItem.title.like(keyword_like),
                    cast(XYCatalogItem.metadata_json, String).like(keyword_like),
                )
            )
        
        # 是否擦亮筛选（直接字段）
        if is_polished is not None:
            conditions.append(XYCatalogItem.is_polished == is_polished)
        
        # 多规格筛选（metadata_json字段）
        if is_multi_spec is not None:
            if is_multi_spec:
                conditions.append(
                    XYCatalogItem.metadata_json["is_multi_spec"].as_boolean() == True
                )
            else:
                conditions.append(
                    or_(
                        XYCatalogItem.metadata_json.is_(None),
                        XYCatalogItem.metadata_json["is_multi_spec"].as_boolean() == False,
                        XYCatalogItem.metadata_json["is_multi_spec"].is_(None)
                    )
                )
        
        # 多数量发货筛选（metadata_json字段）
        if multi_quantity_delivery is not None:
            if multi_quantity_delivery:
                conditions.append(
                    XYCatalogItem.metadata_json["multi_quantity_delivery"].as_boolean() == True
                )
            else:
                conditions.append(
                    or_(
                        XYCatalogItem.metadata_json.is_(None),
                        XYCatalogItem.metadata_json["multi_quantity_delivery"].as_boolean() == False,
                        XYCatalogItem.metadata_json["multi_quantity_delivery"].is_(None)
                    )
                )
        
        if conditions:
            base_stmt = base_stmt.where(and_(*conditions))
        
        # 查询总数：仅在按账号筛选时才需要 JOIN 账号表，否则直接基于商品表统计，避免无谓 JOIN
        count_stmt = select(func.count(XYCatalogItem.id)).select_from(XYCatalogItem)
        if account_id:
            count_stmt = count_stmt.outerjoin(XYAccount, XYCatalogItem.account_pk == XYAccount.id)
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar() or 0
        
        # 分页查询
        offset = (page - 1) * page_size
        stmt = base_stmt.order_by(XYCatalogItem.created_at.desc()).offset(offset).limit(page_size)
        rows = await self.session.execute(stmt)
        items_data = rows.all()
        
        # 批量查询所有商品的默认回复状态和卡券状态
        default_reply_map = await self._get_default_reply_status_batch(items_data)
        card_set = await self._get_card_status_batch(items_data)
        
        items = [self._serialize_item(item, acct_id, default_reply_map.get((acct_id, item.item_id)), item.item_id in card_set) for item, acct_id in items_data]
        return items, total

    async def fetch_items_page_from_account(
        self,
        account: XYAccount,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """从指定账号抓取单页商品并入库"""
        myid = self._resolve_account_fetch_user_id(account)

        manager = await self._resolve_item_fetch_manager(account)
        try:
            result = await manager.get_item_list_info(page, page_size, myid=myid)
        except Exception as exc:
            return {"success": False, "message": f"获取商品失败: {exc}"}
        finally:
            await manager.close()

        if not result or not result.get("success"):
            message = ""
            if isinstance(result, dict):
                message = result.get("message") or result.get("error") or ""
            return {"success": False, "message": message or "获取商品失败"}

        items = result.get("items") or []
        count = result.get("current_count") or len(items)

        try:
            saved_count, _ = await self.save_fetched_items(account, items)
        except Exception as exc:
            await self.session.rollback()
            return {"success": False, "message": f"保存商品失败: {exc}"}

        return {
            "success": True,
            "message": f"获取到第 {page} 页商品，共 {count} 件",
            "items": items,
            "page": page,
            "page_number": page,
            "page_size": page_size,
            "count": count,
            "current_count": count,
            "has_more": len(items) >= page_size,
            "saved_count": saved_count,
        }

    async def fetch_all_items_from_account(
        self,
        account: XYAccount,
        page_size: int = 20,
        max_pages: int | None = None,
        stop_when_page_all_existing: bool = False,
        required_title_keyword: str | None = None,
    ) -> dict[str, Any]:
        """抓取指定账号全部商品并入库（账号级加锁入口）

        通过 Redis 账号级互斥锁，保证同一账号同一时刻只有一个商品同步流程在
        拉取 + 落库，避免「定时获取闲鱼商品任务」与「商品管理页手动触发同步」
        并发 upsert 同一商品。Redis 不可用时降级为无锁执行，由 xy_catalog_items
        的 (account_id, item_id) 唯一约束 + 保存时的冲突重试做最终兜底。
        """
        lock_name = f"item_sync:{account.account_id}"
        try:
            async with distributed_lock(
                lock_name, expire=300, blocking=True, timeout=8
            ) as lock:
                if not lock.is_locked:
                    logger.info(
                        f"账号[{account.account_id}]商品同步锁被占用，跳过本次"
                        f"（避免与其他同步任务并发）"
                    )
                    return {
                        "success": True,
                        "skipped": True,
                        "message": "账号商品同步锁被占用，已跳过",
                        "items": [],
                        "total_count": 0,
                        "total_pages": 0,
                        "page_size": page_size,
                        "saved_count": 0,
                    }
                return await self._fetch_all_items_from_account_impl(
                    account=account,
                    page_size=page_size,
                    max_pages=max_pages,
                    stop_when_page_all_existing=stop_when_page_all_existing,
                    required_title_keyword=required_title_keyword,
                )
        except Exception as exc:
            # Redis 不可用等异常时降级为无锁执行，靠唯一约束兜底防止重复入库
            logger.warning(
                f"账号[{account.account_id}]商品同步获取锁异常，降级无锁执行"
                f"（依赖唯一约束兜底）: {exc}"
            )
            return await self._fetch_all_items_from_account_impl(
                account=account,
                page_size=page_size,
                max_pages=max_pages,
                stop_when_page_all_existing=stop_when_page_all_existing,
                required_title_keyword=required_title_keyword,
            )

    async def _fetch_all_items_from_account_impl(
        self,
        account: XYAccount,
        page_size: int = 20,
        max_pages: int | None = None,
        stop_when_page_all_existing: bool = False,
        required_title_keyword: str | None = None,
    ) -> dict[str, Any]:
        """抓取指定账号全部商品并入库（实际实现，调用方需已持有账号锁）"""
        myid = self._resolve_account_fetch_user_id(account)
        normalized_required_title_keyword = str(required_title_keyword or "").strip()

        manager = await self._resolve_item_fetch_manager(account)
        fetched_items: list[dict] = []
        total_saved_count = 0
        fetched_pages = 0
        matched_required_title_keyword = False
        try:
            page_number = 1
            while True:
                if max_pages and page_number > max_pages:
                    logger.info(f"账号[{account.account_id}]商品同步达到最大页数限制 {max_pages}，停止获取")
                    break

                logger.info(f"账号[{account.account_id}]商品同步正在获取第 {page_number} 页")
                result = await manager.get_item_list_info(page_number, page_size, myid=myid)

                if not result or not result.get("success"):
                    message = ""
                    if isinstance(result, dict):
                        message = result.get("message") or result.get("error") or ""
                    logger.error(f"账号[{account.account_id}]商品同步获取第 {page_number} 页失败: {result}")
                    return {"success": False, "message": message or f"获取第 {page_number} 页商品失败"}

                items = result.get("items") or []
                if not items:
                    logger.info(f"账号[{account.account_id}]商品同步第 {page_number} 页无数据，结束获取")
                    break

                valid_items, skipped_count = self._collect_valid_item_entries(items)
                unique_item_ids = list(dict.fromkeys(item_id for item_id, _ in valid_items))
                existing_map = await self._get_existing_item_map(account, unique_item_ids)
                page_matches_required_title = (
                    bool(normalized_required_title_keyword)
                    and any(
                        normalized_required_title_keyword in str(item.get("title") or "")
                        for _, item in valid_items
                    )
                )
                if page_matches_required_title:
                    matched_required_title_keyword = True
                page_all_existing = (
                    skipped_count == 0
                    and bool(unique_item_ids)
                    and len(existing_map) == len(unique_item_ids)
                )

                try:
                    saved_count, page_changed_count = await self.save_fetched_items(
                        account,
                        items,
                    )
                except Exception as exc:
                    await self.session.rollback()
                    return {"success": False, "message": f"保存商品失败: {exc}"}
                fetched_items.extend(items)
                total_saved_count += saved_count
                fetched_pages = page_number

                logger.info(
                    f"账号[{account.account_id}]商品同步第{page_number}页完成，本页{len(items)}件，"
                    f"累计抓取{len(fetched_items)}件，整页已存在={page_all_existing}，"
                    f"命中目标商品={page_matches_required_title}"
                )

                # 仅当本页全部商品已存在且无实际字段变更（如价格/标题变化）时才停止翻页；
                # 若有商品被更新（如卖家在闲鱼改价），需继续翻页以免遗漏更早商品的变更。
                if (
                    stop_when_page_all_existing
                    and page_all_existing
                    and page_changed_count == 0
                    and (
                        not normalized_required_title_keyword
                        or matched_required_title_keyword
                    )
                ):
                    logger.info(f"账号[{account.account_id}]商品同步命中整页已存在且无字段变更，停止继续获取后续页面")
                    break

                if len(items) < page_size:
                    logger.info(f"账号[{account.account_id}]商品同步第 {page_number} 页数量少于页大小，结束获取")
                    break

                page_number += 1
                await asyncio.sleep(1)
        except Exception as exc:
            return {"success": False, "message": f"获取商品失败: {exc}"}
        finally:
            await manager.close()

        return {
            "success": True,
            "message": f"获取到 {len(fetched_items)} 个商品",
            "items": fetched_items,
            "total_count": len(fetched_items),
            "total_pages": fetched_pages,
            "page_size": page_size,
            "saved_count": total_saved_count,
        }

    async def fetch_all_items_from_accounts(
        self,
        accounts: list[XYAccount],
        page_size: int = 20,
        max_pages: int | None = None,
    ) -> dict[str, Any]:
        """按账号列表批量抓取全部商品并汇总结果"""
        if not accounts:
            return {
                "success": False,
                "message": "当前范围内没有可获取商品的账号",
                "account_count": 0,
                "success_account_count": 0,
                "failed_account_count": 0,
                "total_count": 0,
                "saved_count": 0,
                "failed_accounts": [],
                "results": [],
            }

        account_results: list[dict[str, Any]] = []
        failed_accounts: list[str] = []
        total_count = 0
        saved_count = 0
        success_account_count = 0

        for account in accounts:
            try:
                result = await self.fetch_all_items_from_account(
                    account=account,
                    page_size=page_size,
                    max_pages=max_pages,
                )
                account_success = bool(result.get("success"))
                account_total_count = int(result.get("total_count") or 0)
                account_saved_count = int(result.get("saved_count") or 0)
                account_message = str(result.get("message") or "")
            except Exception as exc:
                await self.session.rollback()
                account_success = False
                account_total_count = 0
                account_saved_count = 0
                account_message = f"获取商品失败: {exc}"

            if account_success:
                success_account_count += 1
                total_count += account_total_count
                saved_count += account_saved_count
            else:
                failed_accounts.append(f"{account.account_id}: {account_message or '获取商品失败'}")

            account_results.append(
                {
                    "cookie_id": account.account_id,
                    "success": account_success,
                    "message": account_message,
                    "total_count": account_total_count,
                    "saved_count": account_saved_count,
                }
            )

        failed_account_count = len(accounts) - success_account_count
        if success_account_count == 0:
            message = f"获取所有账号商品失败，共 {failed_account_count} 个账号执行失败"
            success = False
        elif failed_account_count == 0:
            message = f"成功获取 {success_account_count} 个账号商品，共 {total_count} 件，保存 {saved_count} 件"
            success = True
        else:
            message = f"已获取 {success_account_count} 个账号商品，共 {total_count} 件，保存 {saved_count} 件；失败 {failed_account_count} 个账号"
            success = True

        return {
            "success": success,
            "message": message,
            "account_count": len(accounts),
            "success_account_count": success_account_count,
            "failed_account_count": failed_account_count,
            "total_count": total_count,
            "saved_count": saved_count,
            "failed_accounts": failed_accounts,
            "results": account_results,
        }

    async def save_fetched_items(
        self,
        account: XYAccount,
        items: list[dict],
    ) -> tuple[int, int]:
        """保存抓取到的商品数据到本地库（逐个商品独立提交）

        返回 (保存成功的商品数, 有实际字段变更的商品数)。
        """
        valid_items, _ = self._collect_valid_item_entries(items)
        if not valid_items:
            return 0, 0

        saved_count = 0
        changed_count = 0
        for item_id, item in valid_items:
            success, has_changes = await self._save_single_item(account, item_id, item)
            if success:
                saved_count += 1
            if has_changes:
                changed_count += 1

        return saved_count, changed_count

    async def _save_single_item(
        self,
        account: XYAccount,
        item_id: str,
        item: dict,
    ) -> tuple[bool, bool]:
        """保存单个商品并独立提交（更新或新增）。

        返回 (是否保存成功, 是否有实际字段变更)；
        单个商品失败只回滚自身，不抛出异常，由调用方继续处理其余商品。
        """
        try:
            has_changes = await self._apply_single_item(account, item_id, item)
            if has_changes:
                await self.session.commit()
            return True, has_changes
        except IntegrityError:
            await self.session.rollback()
            logger.info(
                f"账号[{account.account_id}]商品 {item_id} 保存命中唯一约束，转为更新已存在记录后重试"
            )
            try:
                has_changes = await self._apply_single_item(account, item_id, item)
                if has_changes:
                    await self.session.commit()
                return True, has_changes
            except Exception as exc:
                await self.session.rollback()
                logger.warning(
                    f"账号[{account.account_id}]商品 {item_id} 重试更新仍失败，跳过该商品: {exc}"
                )
                return False, False
        except Exception as exc:
            await self.session.rollback()
            logger.warning(
                f"账号[{account.account_id}]商品 {item_id} 保存失败，跳过该商品: {exc}"
            )
            return False, False

    async def _apply_single_item(
        self,
        account: XYAccount,
        item_id: str,
        item: dict,
    ) -> bool:
        """将单个商品写入会话（更新或新增），不提交。

        每次都在当前事务内实时查询已存在记录，保证拿到的是当前事务可用的对象。
        返回 True 表示有实际变更（新增或字段值变化），False 表示无需更新。
        """
        category = str(item.get("category_id", ""))
        # 多规格商品（卖家平台 idleItemSkuList 多于一项）同步时自动开启「多规格」开关
        sku_list = item.get("idle_item_sku_list")
        is_multi_spec = isinstance(sku_list, list) and len(sku_list) > 1

        stmt = select(XYCatalogItem).where(
            XYCatalogItem.owner_id == account.owner_id,
            XYCatalogItem.account_pk == account.id,
            XYCatalogItem.item_id == item_id,
        )
        existing_item = (await self.session.execute(stmt)).scalars().first()

        if existing_item:
            new_title = item.get("title", "")
            new_price = item.get("price_text", "")
            changed = False
            if existing_item.title != new_title:
                existing_item.title = new_title
                changed = True
            if existing_item.price != new_price:
                existing_item.price = new_price
                changed = True
            metadata_json = existing_item.metadata_json or {}
            if metadata_json.get("category") != category:
                metadata_json["category"] = category
                existing_item.metadata_json = metadata_json
                flag_modified(existing_item, "metadata_json")
                changed = True
            # 刷新整块 detail：让库存、上架时间、状态等随每次同步更新，而非停留在首次抓取值
            new_detail = json.dumps(item, ensure_ascii=False)
            if metadata_json.get("detail") != new_detail:
                metadata_json["detail"] = new_detail
                existing_item.metadata_json = metadata_json
                flag_modified(existing_item, "metadata_json")
                changed = True
            # 多规格商品自动开启开关；仅在识别到多规格时置 True，不覆盖用户手动设置
            if is_multi_spec and metadata_json.get("is_multi_spec") is not True:
                metadata_json["is_multi_spec"] = True
                existing_item.metadata_json = metadata_json
                flag_modified(existing_item, "metadata_json")
                changed = True
            return changed

        new_metadata = {
            "description": "",
            "category": category,
            "detail": json.dumps(item, ensure_ascii=False),
        }
        # 新增即为多规格商品时，同步自动开启「多规格」开关
        if is_multi_spec:
            new_metadata["is_multi_spec"] = True
        new_item = XYCatalogItem(
            owner_id=account.owner_id,
            account_pk=account.id,
            item_id=item_id,
            title=item.get("title", ""),
            price=item.get("price_text", ""),
            is_polished=False,
            metadata_json=new_metadata,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(new_item)
        return True

    @staticmethod
    def _normalize_price_yuan(value: Any) -> Decimal:
        """把「元」金额规整为最多两位小数的 Decimal（四舍五入），非法输入抛 ValueError。"""
        try:
            return Decimal(str(value)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("价格格式不正确")

    @staticmethod
    def _price_to_num(price_yuan: Decimal):
        """把「元」Decimal 转为 JSON 数字：整数金额用 int，含小数用 float。

        卖家平台改价接口 price 字段单位为元；抓包中整数金额提交为整型（如 111111），
        故整数金额发 int、带小数金额发 float，尽量与平台请求保持一致。
        """
        if price_yuan == price_yuan.to_integral_value():
            return int(price_yuan)
        return float(price_yuan)

    async def update_item_price(
        self,
        account: XYAccount,
        item_id: str,
        single: dict | None = None,
        skus: list[dict] | None = None,
    ) -> dict:
        """鱼小铺商品改价（价格与库存一并提交）。仅鱼小铺账号可用。

        Args:
            account: 账号对象。
            item_id: 商品ID。
            single: 单规格 {"price": 元, "quantity": int}。
            skus: 多规格 [{"sku_id": str, "price": 元, "quantity": int}, ...]。
        Returns:
            dict: {success, message}
        """
        from common.services.xianyu_seller_item_client import update_seller_item_price

        # 改价功能仅支持鱼小铺账号
        if not await self._detect_is_fish_shop(account):
            return {"success": False, "message": "改价功能仅支持鱼小铺账号"}

        try:
            single_payload = None
            sku_payload = None
            # 卖家平台改价接口 price 字段单位为「元」（平台内部再 ×100 存为分），上限 99999999.99 元
            max_price_yuan = Decimal("99999999.99")
            if single is not None:
                price_yuan = self._normalize_price_yuan(single.get("price"))
                quantity = int(single.get("quantity"))
                if price_yuan <= 0 or quantity < 0:
                    return {"success": False, "message": "价格需大于0、库存不能为负数"}
                if price_yuan > max_price_yuan:
                    return {"success": False, "message": "价格不能超过99999999.99元"}
                single_payload = {"price": self._price_to_num(price_yuan), "quantity": quantity}
            elif skus:
                sku_payload = []
                for sku in skus:
                    sku_id = str(sku.get("sku_id") or "").strip()
                    price_yuan = self._normalize_price_yuan(sku.get("price"))
                    quantity = int(sku.get("quantity"))
                    if not sku_id or price_yuan <= 0 or quantity < 0:
                        return {
                            "success": False,
                            "message": "每个规格需填写规格ID、价格大于0、库存不能为负数",
                        }
                    if price_yuan > max_price_yuan:
                        return {"success": False, "message": "规格价格不能超过99999999.99元"}
                    sku_payload.append(
                        {"sku_id": sku_id, "price": self._price_to_num(price_yuan), "quantity": quantity}
                    )
            else:
                return {"success": False, "message": "缺少改价参数"}
        except (TypeError, ValueError):
            return {"success": False, "message": "价格或库存格式不正确"}

        result = await update_seller_item_price(
            account_id=account.account_id,
            cookie=account.cookie,
            item_id=item_id,
            single=single_payload,
            sku_list=sku_payload,
            owner_id=account.owner_id,
        )
        if not result.get("success"):
            return result

        # 远程改价成功后同步更新本地价格/库存，界面立即反映（真实数据，非模拟）
        await self._apply_local_price_change(account, item_id, single_payload, sku_payload)
        return {"success": True, "message": "改价成功"}

    async def _apply_local_price_change(
        self,
        account: XYAccount,
        item_id: str,
        single_payload: dict | None,
        sku_payload: list[dict] | None,
    ) -> None:
        """远程改价成功后，把新价格/库存回写本地商品记录（含 detail 内规格明细）。"""
        stmt = select(XYCatalogItem).where(
            XYCatalogItem.owner_id == account.owner_id,
            XYCatalogItem.account_pk == account.id,
            XYCatalogItem.item_id == item_id,
        )
        item = (await self.session.execute(stmt)).scalars().first()
        if not item:
            return

        metadata = item.metadata_json or {}
        detail: dict = {}
        detail_raw = metadata.get("detail")
        if isinstance(detail_raw, str) and detail_raw:
            try:
                parsed = json.loads(detail_raw)
                detail = parsed if isinstance(parsed, dict) else {}
            except (ValueError, TypeError):
                detail = {}

        if single_payload:
            yuan = f"{float(single_payload['price']):.2f}"
            item.price = yuan
            detail["price"] = yuan
            detail["price_text"] = yuan
            detail["reservePrice"] = yuan
            detail["quantity"] = single_payload["quantity"]
        else:
            sku_map = {s["sku_id"]: s for s in (sku_payload or [])}
            total_qty = 0
            prices: list[float] = []
            for sku in detail.get("idle_item_sku_list") or []:
                sid = str(sku.get("sku_id") or "")
                if sid in sku_map:
                    sku["price"] = f"{float(sku_map[sid]['price']):.2f}"
                    sku["quantity"] = sku_map[sid]["quantity"]
                try:
                    total_qty += int(sku.get("quantity") or 0)
                except (TypeError, ValueError):
                    pass
                try:
                    prices.append(float(sku.get("price") or 0))
                except (TypeError, ValueError):
                    pass
            if prices:
                lo, hi = min(prices), max(prices)
                price_str = f"{lo:.2f}" if lo == hi else f"{lo:.2f}~{hi:.2f}"
                item.price = price_str
                detail["reservePrice"] = price_str
                detail["price"] = price_str
                detail["price_text"] = price_str
            detail["quantity"] = total_qty

        metadata["detail"] = json.dumps(detail, ensure_ascii=False)
        item.metadata_json = metadata
        flag_modified(item, "metadata_json")
        await self.session.commit()

    async def _get_default_reply_status_batch(self, items_data: list) -> Dict[tuple, dict]:
        """批量获取商品默认回复状态
        
        Args:
            items_data: [(item, account_id), ...] 商品数据列表
            
        Returns:
            {(account_id, item_id): {'enabled': bool, 'has_config': bool}, ...}
        """
        if not items_data:
            return {}
        
        # 收集所有需要查询的 (account_id, item_id) 组合
        item_keys = [(acct_id, item.item_id) for item, acct_id in items_data]
        account_ids = list(set(acct_id for acct_id, _ in item_keys))
        item_ids = list(set(item_id for _, item_id in item_keys))
        
        # 查询所有相关的默认回复配置
        stmt = select(DefaultReply).where(
            DefaultReply.account_id.in_(account_ids),
            DefaultReply.item_id.in_(item_ids)
        )
        result = await self.session.execute(stmt)
        replies = result.scalars().all()
        
        # 构建映射
        reply_map = {}
        for reply in replies:
            key = (reply.account_id, reply.item_id)
            reply_map[key] = {
                'enabled': reply.enabled,
                'has_config': True
            }
        
        return reply_map

    async def _get_card_status_batch(self, items_data: list) -> Set[str]:
        """批量获取商品卡券配置状态（通过关联表+旧字段兼容，不区分用户）
        
        Args:
            items_data: [(item, account_id), ...] 商品数据列表
            
        Returns:
            {item_id, ...} 已配置卡券的商品ID集合
        """
        if not items_data:
            return set()
        
        # 收集所有需要查询的 item_id
        item_ids = list(set(item.item_id for item, _ in items_data))
        
        from common.services.card_matcher import CardMatcher
        matcher = CardMatcher(self.session)
        
        # 按 item_id 查询卡券状态（不区分用户，与发货配置弹窗逻辑一致）
        status_map = await matcher.get_items_with_card_status(item_ids)
        configured_items: Set[str] = set()
        for item_id, has_card in status_map.items():
            if has_card:
                configured_items.add(item_id)
        
        return configured_items

    async def get_item(self, owner_id: int | None, account_id: str, item_id: str) -> dict | None:
        stmt = (
            select(XYCatalogItem)
            .join(XYAccount, XYCatalogItem.account_pk == XYAccount.id)
            .where(
                XYAccount.account_id == account_id,
                XYCatalogItem.item_id == item_id,
            )
        )
        # 管理员 owner_id 为 None，不限制所有者
        if owner_id is not None:
            stmt = stmt.where(XYCatalogItem.owner_id == owner_id)
        result = await self.session.execute(stmt)
        item = result.scalars().first()
        if not item:
            return None
        return self._serialize_item(item, account_id)

    async def update_item(self, account: XYAccount, item_id: str, data: dict) -> bool:
        """更新商品信息"""
        from sqlalchemy.orm.attributes import flag_modified
        from loguru import logger
        
        logger.info(f"ItemService.update_item: item_id={item_id}, data={data}")
        
        stmt = (
            select(XYCatalogItem)
            .where(
                XYCatalogItem.owner_id == account.owner_id,
                XYCatalogItem.account_pk == account.id,
                XYCatalogItem.item_id == item_id,
            )
        )
        result = await self.session.execute(stmt)
        item = result.scalars().first()
        if not item:
            logger.warning(f"商品不存在: item_id={item_id}")
            return False
        
        logger.info(f"找到商品: id={item.id}, title={item.title}, metadata={item.metadata_json}")
        
        # 字段名映射（前端使用item_前缀，数据库metadata中不使用前缀）
        field_mapping = {
            'item_detail': 'detail',
            'item_description': 'description',
            'item_category': 'category',
            'item_title': 'title',
            'item_price': 'price',
        }
        
        # 更新字段
        metadata_modified = False
        for key, value in data.items():
            # 检查是否是直接字段（title, price, ai_prompt等）
            if key in ['title', 'price', 'ai_prompt'] and hasattr(item, key):
                logger.info(f"更新字段 {key}: {getattr(item, key)} -> {value}")
                setattr(item, key, value)
            # 检查是否需要映射到metadata
            elif key in field_mapping:
                mapped_key = field_mapping[key]
                if item.metadata_json is None:
                    item.metadata_json = {}
                logger.info(f"更新metadata字段 {key} -> {mapped_key}: {item.metadata_json.get(mapped_key)} -> {value}")
                item.metadata_json[mapped_key] = value
                metadata_modified = True
            # 其他字段直接存储到metadata
            elif item.metadata_json is not None:
                logger.info(f"更新metadata字段 {key}: {item.metadata_json.get(key)} -> {value}")
                item.metadata_json[key] = value
                metadata_modified = True
        
        # 标记metadata_json已修改（SQLAlchemy不会自动检测JSON字段的变化）
        if metadata_modified:
            logger.info("标记metadata_json已修改")
            flag_modified(item, 'metadata_json')
        
        await self.session.commit()
        logger.info(f"商品更新已提交: item_id={item_id}")
        return True

    async def delete_item(self, account: XYAccount, item_id: str) -> bool:
        """删除商品（同时删除关联表记录）"""
        from loguru import logger
        from common.services.card_matcher import CardMatcher
        
        stmt = (
            select(XYCatalogItem)
            .where(
                XYCatalogItem.owner_id == account.owner_id,
                XYCatalogItem.account_pk == account.id,
                XYCatalogItem.item_id == item_id,
            )
        )
        result = await self.session.execute(stmt)
        item = result.scalars().first()
        if not item:
            return False
        
        # 级联删除关联表记录
        matcher = CardMatcher(self.session)
        rel_count = await matcher.delete_relations_by_item_id(item_id)
        if rel_count > 0:
            logger.info(f"删除商品 {item_id} 的 {rel_count} 条卡券关联记录")
        
        await self.session.delete(item)
        await self.session.commit()
        return True

    async def delete_item_smart(
        self, owner_id: int | None, item_id: str, account: XYAccount | None = None
    ) -> str:
        """统一删除商品，兼容账号已被删除的孤儿商品。

        删除规则（与前端约定一致）：
        - 传入 account（调用方已校验账号归属）：按 (owner_id, account.id, item_id) 精确删除；
        - 未传 account：在 owner 范围内按 item_id 定位商品，
            * 若其所属账号仍存在 → 返回 'account_required'，要求调用方指定账号后再删；
            * 若所属账号已不存在（孤儿商品）→ 直接按 item_id 删除并清理卡券关联。

        Args:
            owner_id: 用户ID（管理员场景可为 None，表示不限制归属）
            item_id: 商品ID
            account: 已校验的账号对象（可选）

        Returns:
            'ok'：删除成功；'not_found'：商品不存在；'account_required'：商品所属账号仍存在，需指定账号
        """
        # CardMatcher 采用局部导入，避免与 card_matcher 模块产生循环依赖（与 delete_item 保持一致）
        from common.services.card_matcher import CardMatcher

        # 情况一：调用方已指定并校验账号 → 复用原有按账号删除逻辑
        if account is not None:
            ok = await self.delete_item(account, item_id)
            return "ok" if ok else "not_found"

        # 情况二：未指定账号 → 按 owner + item_id 定位商品记录
        stmt = select(XYCatalogItem).where(XYCatalogItem.item_id == item_id)
        if owner_id is not None:
            stmt = stmt.where(XYCatalogItem.owner_id == owner_id)
        items = (await self.session.execute(stmt)).scalars().all()
        if not items:
            return "not_found"

        # 校验这些商品所属账号是否仍然存在
        account_pks = {it.account_pk for it in items}
        existing_rows = await self.session.execute(
            select(XYAccount.id).where(XYAccount.id.in_(account_pks))
        )
        existing_pks = {row[0] for row in existing_rows.all()}
        if existing_pks:
            # 商品所属账号仍存在 → 不允许脱离账号删除，要求指定账号
            return "account_required"

        # 全部为孤儿商品（账号已删除）→ 按 item_id 删除，并清理卡券关联
        matcher = CardMatcher(self.session)
        rel_count = await matcher.delete_relations_by_item_id(item_id)
        if rel_count > 0:
            logger.info(f"删除孤儿商品 {item_id} 的 {rel_count} 条卡券关联记录")
        for it in items:
            await self.session.delete(it)
        await self.session.commit()
        logger.info(f"已删除孤儿商品 {item_id}（所属账号已不存在），共 {len(items)} 条记录")
        return "ok"

    async def delete_many(self, account: XYAccount, item_ids: list[str]) -> int:
        deleted = 0
        for item_id in item_ids:
            success = await self.delete_item(account, item_id)
            if success:
                deleted += 1
        return deleted

    def _serialize_item(self, item: XYCatalogItem, account_id: str, default_reply_info: dict | None = None, has_card: bool = False) -> dict:
        metadata = item.metadata_json or {}
        # 从 detail(整块商品JSON) 解析鱼小铺特有字段供界面展示；普通账号无此字段时返回空
        detail_raw = metadata.get("detail")
        detail_obj: dict = {}
        if isinstance(detail_raw, str) and detail_raw:
            try:
                parsed = json.loads(detail_raw)
                if isinstance(parsed, dict):
                    detail_obj = parsed
            except (ValueError, TypeError):
                detail_obj = {}
        return {
            "id": item.id,
            "cookie_id": account_id,
            "item_id": item.item_id,
            "title": item.title,
            "item_title": item.title,
            "item_description": metadata.get("description"),
            "item_detail": detail_raw,
            "item_category": metadata.get("category"),
            "item_price": item.price,
            # 鱼小铺特有：库存、上架时间、商品状态（普通账号为空，前端显示 -）
            "item_quantity": detail_obj.get("quantity", ""),
            "item_shelf_time": detail_obj.get("gmt_shelf", ""),
            "item_status_desc": detail_obj.get("item_status_desc", ""),
            # 多规格明细：供前端「规格数」列与规格详情弹窗展示
            "item_sku_list": detail_obj.get("idle_item_sku_list") or [],
            "item_sku_count": len(detail_obj.get("idle_item_sku_list") or []),
            # 是否鱼小铺商品：仅鱼小铺商品可改价
            "is_seller_item": detail_obj.get("source") == "seller",
            "ai_prompt": item.ai_prompt or "",
            "has_ai_prompt": bool(item.ai_prompt),
            "is_polished": item.is_polished or False,
            "is_multi_spec": metadata.get("is_multi_spec", False),
            "multi_quantity_delivery": metadata.get("multi_quantity_delivery", False),
            "default_reply_enabled": default_reply_info.get("enabled", False) if default_reply_info else False,
            "has_default_reply": default_reply_info.get("has_config", False) if default_reply_info else False,
            "has_card": has_card,
            "created_at": self._format_dt(item.created_at),
            "updated_at": self._format_dt(item.updated_at),
        }

    @staticmethod
    def _format_dt(value: datetime | str | None) -> str | None:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, str):
            return value
        return None
