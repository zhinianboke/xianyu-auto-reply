"""
商品发布执行与日志服务

功能：
1. 提供商品发布日志的创建、更新、分页查询
2. 提供单品发布与批量发布执行能力
3. 在发布前解析随机地址池，并记录地址来源到日志
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.paths import STATIC_ROOT
from app.services.publish_address_service import PublishAddressService
from app.services.publish_batch_status_service import PublishBatchStatusService
from app.services.item_service import ItemService
from common.models.publish_log import PublishLog
from common.models.xy_account import XYAccount
from common.services.publish_execution_service import execute_single_publish
from common.services.xianyu_publish_service import create_xianyu_publisher


from common.utils.time_utils import safe_isoformat
class PublishLogService:
    """发布日志 CRUD 服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_log(
        self,
        user_id: int,
        account_id: str,
        title: str,
        description: str = None,
        price: str = None,
        material_id: int = None,
        batch_id: str = None,
        status: str = "pending",
        error_message: str = None,
        resolved_address_id: int = None,
        resolved_address_text: str = None,
        address_source: str = None,
    ) -> PublishLog:
        """创建发布日志条目"""
        log = PublishLog(
            user_id=user_id,
            account_id=account_id,
            title=title,
            description=description,
            price=price,
            material_id=material_id,
            batch_id=batch_id,
            status=status,
            error_message=str(error_message)[:1000] if error_message is not None else None,
            resolved_address_id=resolved_address_id,
            resolved_address_text=resolved_address_text,
            address_source=address_source,
        )
        self.session.add(log)
        await self.session.commit()
        await self.session.refresh(log)
        return log

    async def update_log(
        self,
        log_id: int,
        status: str,
        item_url: str = None,
        item_id: str = None,
        error_message: str = None,
    ) -> None:
        """更新发布日志状态"""
        stmt = select(PublishLog).where(PublishLog.id == log_id)
        log = (await self.session.execute(stmt)).scalar_one_or_none()
        if log:
            log.status = status
            if item_url is not None:
                log.item_url = item_url
            if item_id is not None:
                log.item_id = item_id
            if error_message is not None:
                log.error_message = str(error_message)[:1000]
            await self.session.commit()

    async def list_logs(
        self,
        user_id: int = None,
        page: int = 1,
        page_size: int = 20,
        account_id: str = None,
        status: str = None,
    ) -> Dict[str, Any]:
        """分页查询发布日志
        
        Args:
            user_id: 用户ID，为None时查询全部（管理员场景）
        """
        page = max(page, 1)
        page_size = page_size if page_size in (10, 20, 50, 100) else 20

        base_cond = []
        if user_id is not None:
            base_cond.append(PublishLog.user_id == user_id)
        if account_id:
            base_cond.append(PublishLog.account_id == account_id)
        if status:
            base_cond.append(PublishLog.status == status)

        count_stmt = select(func.count()).select_from(PublishLog).where(*base_cond)
        total = (await self.session.execute(count_stmt)).scalar() or 0

        stmt = (
            select(PublishLog)
            .where(*base_cond)
            .order_by(desc(PublishLog.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await self.session.execute(stmt)).scalars().all()

        return {
            "list": [_log_to_dict(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
        }


class PublishExecutorService:
    """商品发布执行服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def _get_account(self, account_id: str, user_id: int) -> Optional[XYAccount]:
        stmt = select(XYAccount).where(
            XYAccount.account_id == account_id,
            XYAccount.owner_id == user_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def _get_account_cookie(self, account_id: str, user_id: int) -> Optional[str]:
        """获取账号 Cookie 字符串（验证归属）"""
        account = await self._get_account(account_id, user_id)
        if not account:
            return None
        return account.cookie

    async def _get_account_map(self, account_ids: List[str], user_id: int) -> Dict[str, XYAccount]:
        """批量获取账号对象映射"""
        if not account_ids:
            return {}
        unique_ids = list(dict.fromkeys(account_ids))
        stmt = (
            select(XYAccount)
            .where(
                XYAccount.owner_id == user_id,
                XYAccount.account_id.in_(unique_ids),
            )
            .order_by(desc(XYAccount.id))
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        account_map: Dict[str, XYAccount] = {}
        for row in rows:
            if row.account_id not in account_map:
                account_map[row.account_id] = row
        return account_map

    async def _sync_account_items_after_publish(self, account_id: str, account: XYAccount) -> Dict[str, Any]:
        item_svc = ItemService(self.session)
        try:
            sync_result = await item_svc.fetch_all_items_from_account(account=account)
            sync_status = "success" if sync_result.get("success") else "failed"
            sync_total_count = int(sync_result.get("total_count") or 0)
            sync_saved_count = int(sync_result.get("saved_count") or 0)
            if sync_status == "success":
                sync_message = f"已自动获取 {sync_total_count} 个商品，入库 {sync_saved_count} 个商品"
                logger.info(
                    f"账号 {account_id} 发布后自动获取商品完成：共 {sync_total_count} 件，保存 {sync_saved_count} 件"
                )
            else:
                sync_message = f"自动获取商品失败：{sync_result.get('message') or '未知错误'}"
                logger.warning(
                    f"账号 {account_id} 发布后自动获取商品失败，不影响后续发布：{sync_result.get('message', '未知错误')}"
                )
            return {
                "sync_status": sync_status,
                "sync_message": sync_message,
                "sync_total_count": sync_total_count,
                "sync_saved_count": sync_saved_count,
            }
        except Exception as sync_exc:
            logger.warning(
                f"账号 {account_id} 发布后自动获取商品异常，不影响后续发布：{sync_exc}"
            )
            return {
                "sync_status": "failed",
                "sync_message": f"自动获取商品异常：{sync_exc}",
                "sync_total_count": 0,
                "sync_saved_count": 0,
            }

    async def publish_single(
        self,
        user_id: int,
        account_id: str,
        item_data: dict,
    ) -> Dict[str, Any]:
        """单品发布"""
        return await execute_single_publish(
            session=self.session,
            user_id=user_id,
            account_id=account_id,
            item_data=item_data,
            static_root=STATIC_ROOT,
        )

    async def batch_publish(
        self,
        user_id: int,
        account_ids: List[str],
        materials: List[dict],
        batch_id: str = None,
    ) -> Dict[str, Any]:
        """批量发布（多账号×多商品，每账号复用同一浏览器实例）"""
        if not batch_id:
            batch_id = str(uuid.uuid4())
        log_svc = PublishLogService(self.session)
        address_svc = PublishAddressService(self.session)

        total = len(account_ids) * len(materials)
        success_count = 0
        failed_count = 0
        log_ids: List[int] = []

        logger.info(f"批量发布开始: batch_id={batch_id}, 账号数={len(account_ids)}, 商品数={len(materials)}")

        account_map = await self._get_account_map(account_ids, user_id)

        for account_id in account_ids:
            account = account_map.get(account_id)
            cookies_str = account.cookie if account and account.cookie else ""
            if not cookies_str:
                await PublishBatchStatusService.mark_account_sync_skipped(
                    batch_id=batch_id,
                    account_id=account_id,
                    message="账号不存在或无权使用，未触发自动获取商品",
                )
                logger.warning(f"账号 {account_id} 不存在或无权使用，跳过")
                for material in materials:
                    log = await log_svc.create_log(
                        user_id=user_id,
                        account_id=account_id,
                        title=material.get("title", ""),
                        description=material.get("description", ""),
                        price=str(material.get("price", "")),
                        material_id=material.get("id"),
                        batch_id=batch_id,
                        status="failed",
                        error_message="账号不存在或无权使用",
                    )
                    log_ids.append(log.id)
                failed_count += len(materials)
                continue

            account_success_count = 0
            queue_state = await address_svc.build_queue_state(account_id)
            publisher = create_xianyu_publisher(static_root=STATIC_ROOT)
            try:
                for idx, material in enumerate(materials):
                    try:
                        resolved_address = await address_svc.resolve_publish_address(account_id, material, queue_state)
                    except ValueError as address_error:
                        failed_count += 1
                        log = await log_svc.create_log(
                            user_id=user_id,
                            account_id=account_id,
                            title=material.get("title", ""),
                            description=material.get("description", ""),
                            price=str(material.get("price", "")),
                            material_id=material.get("id"),
                            batch_id=batch_id,
                            status="failed",
                            error_message=str(address_error),
                        )
                        log_ids.append(log.id)
                        continue

                    publish_material = resolved_address.apply_to_item_data(material)
                    log = await log_svc.create_log(
                        user_id=user_id,
                        account_id=account_id,
                        title=material.get("title", ""),
                        description=material.get("description", ""),
                        price=str(material.get("price", "")),
                        material_id=material.get("id"),
                        batch_id=batch_id,
                        status="publishing",
                        **resolved_address.to_log_fields(),
                    )
                    log_ids.append(log.id)

                    try:
                        reuse = idx > 0
                        result = await publisher.publish_item(
                            item_data=publish_material,
                            cookie_data={"cookie": cookies_str},
                            reuse_browser=reuse,
                            should_close=False,
                        )

                        if result.get("success"):
                            success_count += 1
                            account_success_count += 1
                            await log_svc.update_log(
                                log_id=log.id,
                                status="success",
                                item_url=result.get("item_url"),
                                item_id=result.get("item_id"),
                            )
                        else:
                            failed_count += 1
                            await log_svc.update_log(
                                log_id=log.id,
                                status="failed",
                                error_message=result.get("message"),
                            )

                        if idx < len(materials) - 1:
                            await asyncio.sleep(3)

                    except Exception as exc:
                        failed_count += 1
                        logger.error(f"批量发布单品异常: account={account_id}, title={material.get('title')}: {exc}")
                        await log_svc.update_log(log_id=log.id, status="failed", error_message=str(exc))

            finally:
                await publisher.close()

            if account_success_count > 0 and account is not None:
                try:
                    await PublishBatchStatusService.mark_account_sync_running(
                        batch_id=batch_id,
                        account_id=account_id,
                    )
                    sync_info = await self._sync_account_items_after_publish(account_id=account_id, account=account)
                    await PublishBatchStatusService.mark_account_sync_result(
                        batch_id=batch_id,
                        account_id=account_id,
                        status=sync_info.get("sync_status", "failed"),
                        message=sync_info.get("sync_message") or "自动获取商品失败",
                        total_count=int(sync_info.get("sync_total_count") or 0),
                        saved_count=int(sync_info.get("sync_saved_count") or 0),
                    )
                except Exception as sync_exc:
                    await PublishBatchStatusService.mark_account_sync_result(
                        batch_id=batch_id,
                        account_id=account_id,
                        status="failed",
                        message=f"自动获取商品异常：{sync_exc}",
                    )
            else:
                await PublishBatchStatusService.mark_account_sync_skipped(
                    batch_id=batch_id,
                    account_id=account_id,
                    message="该账号没有发布成功的商品，未触发自动获取商品",
                )

        logger.info(f"批量发布结束: batch_id={batch_id}, 成功={success_count}, 失败={failed_count}")

        return {
            "success": True,
            "batch_id": batch_id,
            "total": total,
            "success_count": success_count,
            "failed_count": failed_count,
            "log_ids": log_ids,
        }


def _log_to_dict(log: PublishLog) -> dict:
    """将发布日志模型转为字典"""
    return {
        "id": log.id,
        "user_id": log.user_id,
        "account_id": log.account_id,
        "title": log.title,
        "description": log.description,
        "price": log.price,
        "material_id": log.material_id,
        "batch_id": log.batch_id,
        "status": log.status,
        "item_url": log.item_url,
        "item_id": log.item_id,
        "error_message": log.error_message,
        "resolved_address_id": log.resolved_address_id,
        "resolved_address_text": log.resolved_address_text,
        "address_source": log.address_source,
        "created_at": safe_isoformat(log.created_at),
        "updated_at": safe_isoformat(log.updated_at),
    }
