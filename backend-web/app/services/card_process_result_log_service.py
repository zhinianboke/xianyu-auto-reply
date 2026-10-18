from __future__ import annotations
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from common.models.card_process_result_log import XYCardProcessResultLog

class CardProcessResultLogService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_logs(self, page: int = 1, page_size: int = 20,
                        order_no: str | None = None,
                        trigger_scene: str | None = None,
                        success: bool | None = None):
        q = select(XYCardProcessResultLog).order_by(XYCardProcessResultLog.id.desc())
        count = select(func.count()).select_from(XYCardProcessResultLog)
        if order_no:
            condition = XYCardProcessResultLog.order_no.like(f"%{order_no}%")
            q = q.where(condition); count = count.where(condition)
        if trigger_scene:
            q = q.where(XYCardProcessResultLog.trigger_scene == trigger_scene)
            count = count.where(XYCardProcessResultLog.trigger_scene == trigger_scene)
        if success is not None:
            q = q.where(XYCardProcessResultLog.success == success)
            count = count.where(XYCardProcessResultLog.success == success)
        total = int((await self.session.execute(count)).scalar() or 0)
        rows = (await self.session.execute(q.offset((page-1)*page_size).limit(page_size))).scalars().all()
        items = [{
            "id": r.id, "owner_id": r.owner_id, "order_no": r.order_no,
            "request_body": r.request_body, "response_body": r.response_body,
            "trigger_scene": r.trigger_scene, "success": r.success,
            "result_message": r.result_message,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in rows]
        return {"list": items, "total": total, "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size}
