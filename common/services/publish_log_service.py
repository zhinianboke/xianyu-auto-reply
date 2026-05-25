"""
公共发布日志服务

功能：
1. 创建和更新商品发布日志
2. 提供发布日志分页查询能力
"""
from __future__ import annotations

from typing import Any, Dict

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.publish_log import PublishLog


from common.utils.time_utils import safe_isoformat
class PublishLogService:
    """发布日志 CRUD 服务。"""

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
        """创建发布日志条目。"""
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
        """更新发布日志状态。"""
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
        """分页查询发布日志。"""
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


def _log_to_dict(log: PublishLog) -> dict:
    """将发布日志模型转为字典。"""
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
