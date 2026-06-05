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
from typing import Any, Dict, Set

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
        from common.utils.item_info_manager import ItemInfoManager

        myid = self._resolve_account_fetch_user_id(account)

        manager = ItemInfoManager(account.account_id, account.cookie)
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
            saved_count = await self.save_fetched_items(account, items)
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
        from common.utils.item_info_manager import ItemInfoManager

        myid = self._resolve_account_fetch_user_id(account)
        normalized_required_title_keyword = str(required_title_keyword or "").strip()

        manager = ItemInfoManager(account.account_id, account.cookie)
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
                    saved_count = await self.save_fetched_items(
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

                if (
                    stop_when_page_all_existing
                    and page_all_existing
                    and (
                        not normalized_required_title_keyword
                        or matched_required_title_keyword
                    )
                ):
                    logger.info(f"账号[{account.account_id}]商品同步命中整页已存在，停止继续获取后续页面")
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
    ) -> int:
        """保存抓取到的商品数据到本地库（逐个商品独立提交）

        采用"一个商品一次提交"的方式：每个商品单独 commit，单个商品保存失败只
        回滚并跳过它自己，不影响同一页其他商品入库。

        并发兜底：当 Redis 锁不可用、多个同步流程同时为同一账号入库时，依赖
        xy_catalog_items 的 (account_id, item_id) 唯一约束防止重复插入；若插入
        命中唯一约束（IntegrityError），回滚后改为"更新已存在记录"重试一次，
        确保该商品数据不丢失也不重复。
        """
        valid_items, _ = self._collect_valid_item_entries(items)
        if not valid_items:
            return 0

        saved_count = 0
        for item_id, item in valid_items:
            if await self._save_single_item(account, item_id, item):
                saved_count += 1

        return saved_count

    async def _save_single_item(
        self,
        account: XYAccount,
        item_id: str,
        item: dict,
    ) -> bool:
        """保存单个商品并独立提交（更新或新增）。

        返回是否保存成功；单个商品失败只回滚自身，不抛出异常，由调用方继续处理
        其余商品。命中唯一约束时回滚并转为更新重试一次。

        说明：每个商品在自己的事务内先实时查询是否已存在，再决定更新或新增，
        避免跨事务复用可能被 rollback 失效（expired）的 ORM 对象引发异步懒加载问题。
        """
        try:
            await self._apply_single_item(account, item_id, item)
            await self.session.commit()
            return True
        except IntegrityError:
            # 并发兜底：另一个同步流程已抢先插入同一商品，回滚后重查并转为更新
            await self.session.rollback()
            logger.info(
                f"账号[{account.account_id}]商品 {item_id} 保存命中唯一约束，转为更新已存在记录后重试"
            )
            try:
                await self._apply_single_item(account, item_id, item)
                await self.session.commit()
                return True
            except Exception as exc:
                await self.session.rollback()
                logger.warning(
                    f"账号[{account.account_id}]商品 {item_id} 重试更新仍失败，跳过该商品: {exc}"
                )
                return False
        except Exception as exc:
            await self.session.rollback()
            logger.warning(
                f"账号[{account.account_id}]商品 {item_id} 保存失败，跳过该商品: {exc}"
            )
            return False

    async def _apply_single_item(
        self,
        account: XYAccount,
        item_id: str,
        item: dict,
    ) -> None:
        """将单个商品写入会话（更新或新增），不提交。

        每次都在当前事务内实时查询已存在记录，保证拿到的是当前事务可用的对象。
        """
        category = str(item.get("category_id", ""))

        stmt = select(XYCatalogItem).where(
            XYCatalogItem.owner_id == account.owner_id,
            XYCatalogItem.account_pk == account.id,
            XYCatalogItem.item_id == item_id,
        )
        existing_item = (await self.session.execute(stmt)).scalars().first()

        if existing_item:
            existing_item.title = item.get("title", "")
            existing_item.price = item.get("price_text", "")
            metadata_json = existing_item.metadata_json or {}
            metadata_json["category"] = category
            existing_item.metadata_json = metadata_json
            flag_modified(existing_item, "metadata_json")
            return

        new_item = XYCatalogItem(
            owner_id=account.owner_id,
            account_pk=account.id,
            item_id=item_id,
            title=item.get("title", ""),
            price=item.get("price_text", ""),
            is_polished=False,
            metadata_json={
                "description": "",
                "category": category,
                "detail": json.dumps(item, ensure_ascii=False),
            },
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(new_item)
    
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

    async def delete_many(self, account: XYAccount, item_ids: list[str]) -> int:
        deleted = 0
        for item_id in item_ids:
            success = await self.delete_item(account, item_id)
            if success:
                deleted += 1
        return deleted

    def _serialize_item(self, item: XYCatalogItem, account_id: str, default_reply_info: dict | None = None, has_card: bool = False) -> dict:
        metadata = item.metadata_json or {}
        return {
            "id": item.id,
            "cookie_id": account_id,
            "item_id": item.item_id,
            "title": item.title,
            "item_title": item.title,
            "item_description": metadata.get("description"),
            "item_detail": metadata.get("detail"),
            "item_category": metadata.get("category"),
            "item_price": item.price,
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
