"""
AI 铺货任务服务

功能：
1. 任务与明细的建、查（分页/详情），进度全部落库，服务重启后仍可回查
2. 逐条推进进度（明细状态 + 主表成功/失败计数），失败原因入库便于排查
3. 任务取消、并发闸门计数、服务重启后残留任务的清理
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.session import async_session_maker
from common.models.ai_listing_config import AiListingConfig
from common.models.ai_listing_task import (
    ITEM_STATUS_FAILED,
    ITEM_STATUS_PENDING,
    ITEM_STATUS_RUNNING,
    ITEM_STATUS_SUCCESS,
    TASK_ACTIVE_STATUSES,
    TASK_STATUS_CANCELED,
    TASK_STATUS_FAILED,
    TASK_STATUS_PARTIAL,
    TASK_STATUS_PENDING,
    TASK_STATUS_RUNNING,
    TASK_STATUS_SUCCESS,
    AiListingTask,
    AiListingTaskItem,
    truncate_error_message,
)
from common.models.user import User
from common.utils.time_utils import get_beijing_now_naive, safe_isoformat

# 分页大小白名单，与素材库列表保持一致
ALLOWED_PAGE_SIZES = (10, 20, 50, 100)

# 任务详情最多返回的明细条数
MAX_DETAIL_ITEMS = 200

# 单用户同时进行中的任务上限（防止 AI 费用与并发失控）
MAX_ACTIVE_TASKS_PER_USER = 2


def task_to_dict(task: AiListingTask) -> Dict[str, Any]:
    """把任务 ORM 对象转成接口返回的字典"""
    total = task.total_count or 0
    done = (task.success_count or 0) + (task.failed_count or 0)
    return {
        "task_id": task.task_id,
        "config_id": task.config_id,
        "config_name": task.config_name or "",
        "keyword": task.keyword,
        "total": total,
        "success": task.success_count or 0,
        "failed": task.failed_count or 0,
        "status": task.status,
        "finished": task.status not in TASK_ACTIVE_STATUSES,
        "progress_percent": int(done * 100 / total) if total else 0,
        "error_message": task.error_message or "",
        "started_at": safe_isoformat(task.started_at),
        "finished_at": safe_isoformat(task.finished_at),
        "created_at": safe_isoformat(task.created_at),
    }


def item_to_dict(item: AiListingTaskItem) -> Dict[str, Any]:
    """把任务明细 ORM 对象转成接口返回的字典"""
    return {
        "seq": item.seq,
        "status": item.status,
        "title": item.title or "",
        "material_id": item.material_id,
        "image_count": item.image_count or 0,
        "error_message": item.error_message or "",
    }


class AiListingTaskService:
    """AI 铺货任务与明细的数据库操作"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def count_active_tasks(self, owner_id: int) -> int:
        """统计该用户未结束的任务数（并发闸门，按库计数而非内存）"""
        return await self.session.scalar(
            select(func.count())
            .select_from(AiListingTask)
            .where(
                AiListingTask.owner_id == owner_id,
                AiListingTask.is_deleted.is_(False),
                AiListingTask.status.in_(TASK_ACTIVE_STATUSES),
            )
        ) or 0

    async def create_task(
        self,
        *,
        owner_id: int,
        task_id: str,
        config: AiListingConfig,
        keyword: str,
        total_count: int,
        params: Dict[str, Any],
        max_active_tasks: int | None = None,
    ) -> Optional[AiListingTask]:
        """创建任务主表与全部明细行（初始都是 pending）

        Args:
            owner_id: 归属用户ID。
            task_id: 任务ID（UUID）。
            config: 使用的配置对象。
            keyword: 生成主题。
            total_count: 计划生成条数。
            params: 提交参数快照（不含密钥）。
        Returns:
            新建的任务对象。
        """
        # 锁定用户行后再检查并发数，避免“先查询数量、再创建任务”的竞态。
        # 用户行是稳定且唯一的锁目标，可跨多个 Web 进程生效。
        if max_active_tasks is not None:
            user_exists = await self.session.scalar(
                select(User.id).where(User.id == owner_id).with_for_update()
            )
            if user_exists is None:
                raise ValueError("任务所属用户不存在")
            active_count = await self.count_active_tasks(owner_id)
            if active_count >= max_active_tasks:
                await self.session.rollback()
                return None

        task = AiListingTask(
            owner_id=owner_id,
            task_id=task_id,
            config_id=config.id,
            config_name=config.name,
            keyword=keyword,
            total_count=total_count,
            params=params,
        )
        self.session.add(task)
        self.session.add_all([
            AiListingTaskItem(
                task_id=task_id,
                owner_id=owner_id,
                seq=seq,
                status=ITEM_STATUS_PENDING,
            )
            for seq in range(1, total_count + 1)
        ])
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def get_task(self, task_id: str, owner_id: Optional[int] = None) -> Optional[AiListingTask]:
        """按任务ID查询任务

        Args:
            task_id: 任务ID。
            owner_id: 归属用户ID；为 None 时不做用户过滤（后台任务自身调用）。
        Returns:
            任务对象，不存在时返回 None。
        """
        conditions = [AiListingTask.task_id == task_id, AiListingTask.is_deleted.is_(False)]
        if owner_id is not None:
            conditions.append(AiListingTask.owner_id == owner_id)
        result = await self.session.execute(select(AiListingTask).where(*conditions))
        return result.scalar_one_or_none()

    async def list_tasks(
        self, owner_id: int, page: int = 1, page_size: int = 20, status: Optional[str] = None
    ) -> Dict[str, Any]:
        """分页查询任务历史

        Args:
            owner_id: 归属用户ID。
            page: 页码。
            page_size: 每页条数，不在白名单内时回落 20。
            status: 按状态过滤。
        Returns:
            ``{"list", "total", "page", "page_size", "total_pages"}``
        """
        page = max(page, 1)
        if page_size not in ALLOWED_PAGE_SIZES:
            page_size = 20

        conditions = [
            AiListingTask.owner_id == owner_id,
            AiListingTask.is_deleted.is_(False),
        ]
        if status:
            conditions.append(AiListingTask.status == status)

        total = await self.session.scalar(
            select(func.count()).select_from(AiListingTask).where(*conditions)
        ) or 0

        result = await self.session.execute(
            select(AiListingTask)
            .where(*conditions)
            .order_by(desc(AiListingTask.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        tasks = result.scalars().all()

        return {
            "list": [task_to_dict(item) for item in tasks],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
        }

    async def list_items(self, task_id: str, limit: int = MAX_DETAIL_ITEMS) -> List[AiListingTaskItem]:
        """查询任务明细（按序号升序，最多 limit 条）"""
        result = await self.session.execute(
            select(AiListingTaskItem)
            .where(AiListingTaskItem.task_id == task_id)
            .order_by(AiListingTaskItem.seq)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_task_running(self, task_id: str) -> bool:
        """把等待中的任务标记为执行中并记录开始时间。

        仅允许 ``pending`` 状态转换，避免用户在后台任务真正启动前点击取消后，
        执行器又把已取消任务覆盖回 ``running``。

        Returns:
            是否成功完成状态转换。
        """
        result = await self.session.execute(
            update(AiListingTask)
            .where(
                AiListingTask.task_id == task_id,
                AiListingTask.status == TASK_STATUS_PENDING,
                AiListingTask.is_deleted.is_(False),
            )
            .values(status=TASK_STATUS_RUNNING, started_at=get_beijing_now_naive())
        )
        await self.session.commit()
        return bool(result.rowcount)

    async def mark_item_running(self, task_id: str, seq: int) -> None:
        """把某条明细标记为执行中"""
        await self.session.execute(
            update(AiListingTaskItem)
            .where(AiListingTaskItem.task_id == task_id, AiListingTaskItem.seq == seq)
            .values(status=ITEM_STATUS_RUNNING)
        )
        await self.session.commit()

    async def mark_item_success(
        self, task_id: str, seq: int, *, title: str, material_id: int, image_count: int
    ) -> None:
        """明细成功：写回素材ID与标题，同时累加主表成功数"""
        await self.session.execute(
            update(AiListingTaskItem)
            .where(AiListingTaskItem.task_id == task_id, AiListingTaskItem.seq == seq)
            .values(
                status=ITEM_STATUS_SUCCESS,
                title=title[:200],
                material_id=material_id,
                image_count=image_count,
                error_message=None,
            )
        )
        await self.session.execute(
            update(AiListingTask)
            .where(AiListingTask.task_id == task_id)
            .values(success_count=AiListingTask.success_count + 1)
        )
        await self.session.commit()

    async def mark_item_failed(self, task_id: str, seq: int, error: object) -> None:
        """明细失败：记录失败原因，同时累加主表失败数"""
        await self.session.execute(
            update(AiListingTaskItem)
            .where(AiListingTaskItem.task_id == task_id, AiListingTaskItem.seq == seq)
            .values(status=ITEM_STATUS_FAILED, error_message=truncate_error_message(error))
        )
        await self.session.execute(
            update(AiListingTask)
            .where(AiListingTask.task_id == task_id)
            .values(failed_count=AiListingTask.failed_count + 1)
        )
        await self.session.commit()

    async def mark_remaining_items_failed(self, task_id: str, error: object) -> int:
        """将任务尚未完成的明细统一标记为失败，并同步失败计数。"""
        result = await self.session.execute(
            update(AiListingTaskItem)
            .where(
                AiListingTaskItem.task_id == task_id,
                AiListingTaskItem.status.in_((ITEM_STATUS_PENDING, ITEM_STATUS_RUNNING)),
            )
            .values(status=ITEM_STATUS_FAILED, error_message=truncate_error_message(error))
        )
        affected = int(result.rowcount or 0)
        if affected:
            await self.session.execute(
                update(AiListingTask)
                .where(AiListingTask.task_id == task_id)
                .values(failed_count=AiListingTask.failed_count + affected)
            )
        await self.session.commit()
        return affected

    async def mark_pending_items_canceled(self, task_id: str) -> int:
        """取消请求落库后，先把尚未开始的明细记为失败。

        正在执行中的明细不在这里处理，允许当前正在进行的单条操作自然收尾；
        执行器下一轮会再统一收尾剩余的 pending/running 明细。

        Args:
            task_id: 任务ID。
        Returns:
            被收尾的 pending 明细条数。
        """
        result = await self.session.execute(
            update(AiListingTaskItem)
            .where(
                AiListingTaskItem.task_id == task_id,
                AiListingTaskItem.status == ITEM_STATUS_PENDING,
            )
            .values(
                status=ITEM_STATUS_FAILED,
                error_message=truncate_error_message("任务已取消，该条未生成"),
            )
        )
        affected = int(result.rowcount or 0)
        if affected:
            await self.session.execute(
                update(AiListingTask)
                .where(AiListingTask.task_id == task_id)
                .values(failed_count=AiListingTask.failed_count + affected)
            )
        await self.session.commit()
        return affected

    async def mark_remaining_items_canceled(self, task_id: str) -> int:
        """把未完成的明细按"任务已取消"记为失败

        任务被取消后，还没执行到的明细会停在 pending/running，
        这里统一收尾并同步累加主表失败数，保证进度与明细一致。

        Args:
            task_id: 任务ID。
        Returns:
            被收尾的明细条数。
        """
        return await self.mark_remaining_items_failed(task_id, "任务已取消，该条未生成")

    async def finish_task(self, task_id: str, error_message: Optional[str] = None) -> None:
        """结束任务：按成功/失败条数决定最终状态

        已取消的任务保持 canceled，不被覆盖成其它状态。

        注意：这里必须用标量查询读取计数，不能用 ORM 实例。
        进度是通过 UPDATE 语句累加的，而 session 配置了 expire_on_commit=False，
        identity map 里的旧实例不会刷新，读它会拿到创建时的 0。

        Args:
            task_id: 任务ID。
            error_message: 整体失败原因（如配置缺失、AI 接口整体不可用）。
        """
        row = (
            await self.session.execute(
                select(
                    AiListingTask.status,
                    AiListingTask.success_count,
                    AiListingTask.failed_count,
                ).where(AiListingTask.task_id == task_id)
            )
        ).one_or_none()
        if row is None:
            return

        current_status, success, failed = row
        if current_status == TASK_STATUS_CANCELED:
            await self.session.execute(
                update(AiListingTask)
                .where(AiListingTask.task_id == task_id)
                .values(finished_at=get_beijing_now_naive())
            )
            await self.session.commit()
            return

        if (success or 0) and (failed or 0):
            status = TASK_STATUS_PARTIAL
        elif success or 0:
            status = TASK_STATUS_SUCCESS
        else:
            status = TASK_STATUS_FAILED

        values: dict = {"status": status, "finished_at": get_beijing_now_naive()}
        if error_message:
            values["error_message"] = truncate_error_message(error_message)

        await self.session.execute(
            update(AiListingTask).where(AiListingTask.task_id == task_id).values(**values)
        )
        await self.session.commit()

    async def cancel_task(self, task_id: str, owner_id: int) -> bool:
        """取消任务（软取消：置状态，执行器在下一条开始前自行停止）

        同样用标量查询读状态，避免 identity map 里的旧实例导致误判。

        Args:
            task_id: 任务ID。
            owner_id: 归属用户ID。
        Returns:
            是否成功取消；任务不存在或已结束时返回 False。
        """
        status = await self.session.scalar(
            select(AiListingTask.status).where(
                AiListingTask.task_id == task_id,
                AiListingTask.owner_id == owner_id,
                AiListingTask.is_deleted.is_(False),
            )
        )
        if status is None or status not in TASK_ACTIVE_STATUSES:
            return False
        await self.session.execute(
            update(AiListingTask)
            .where(AiListingTask.task_id == task_id)
            .values(status=TASK_STATUS_CANCELED, error_message="用户已取消任务")
        )
        await self.session.commit()
        await self.mark_pending_items_canceled(task_id)
        return True

    async def is_canceled(self, task_id: str) -> bool:
        """查询任务是否已被取消（执行器每条开始前调用）"""
        status = await self.session.scalar(
            select(AiListingTask.status).where(AiListingTask.task_id == task_id)
        )
        return status == TASK_STATUS_CANCELED


async def mark_stale_running_failed() -> int:
    """把服务重启前遗留的未结束任务标记为失败

    进程被重启/停机时，正在执行的任务不会自己收尾，状态会永远停在 pending/running。
    启动时清理一次，只影响这两个状态，可重复执行（幂等）。

    Returns:
        被标记的任务条数。
    """
    try:
        async with async_session_maker() as session:
            active_rows = (
                await session.execute(
                    select(AiListingTask.task_id, AiListingTask.failed_count).where(
                        AiListingTask.is_deleted.is_(False),
                        AiListingTask.status.in_(TASK_ACTIVE_STATUSES),
                    )
                )
            ).all()
            affected = 0
            for task_id, existing_failed_count in active_rows:
                item_result = await session.execute(
                    update(AiListingTaskItem)
                    .where(
                        AiListingTaskItem.task_id == task_id,
                        AiListingTaskItem.status.in_((ITEM_STATUS_PENDING, ITEM_STATUS_RUNNING)),
                    )
                    .values(status=ITEM_STATUS_FAILED, error_message="服务重启，任务已中断")
                )
                item_count = int(item_result.rowcount or 0)
                await session.execute(
                    update(AiListingTask)
                    .where(
                        AiListingTask.task_id == task_id,
                        AiListingTask.is_deleted.is_(False),
                        AiListingTask.status.in_(TASK_ACTIVE_STATUSES),
                    )
                    .values(
                        status=TASK_STATUS_FAILED,
                        failed_count=(existing_failed_count or 0) + item_count,
                        error_message="服务重启，任务已中断",
                        finished_at=get_beijing_now_naive(),
                    )
                )
                affected += 1
            await session.commit()
            if affected:
                logger.info(f"【AI铺货】启动自检：已把 {affected} 个中断任务标记为失败")
            return affected
    except Exception as exc:
        # 清理失败不能影响服务启动
        logger.warning(f"【AI铺货】启动自检清理遗留任务失败：{exc}")
        return 0


__all__ = [
    "MAX_ACTIVE_TASKS_PER_USER",
    "MAX_DETAIL_ITEMS",
    "AiListingTaskService",
    "item_to_dict",
    "mark_stale_running_failed",
    "task_to_dict",
]
