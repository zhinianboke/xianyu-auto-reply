"""
AI铺货任务状态缓存服务

后台生成素材时维护进度，供前端轮询展示。
"""
from __future__ import annotations

import asyncio
import time
from copy import deepcopy
from typing import Any


class AiListingTaskStatusService:
    """AI铺货任务的内存状态缓存"""

    _lock = asyncio.Lock()
    _cache: dict[str, dict[str, Any]] = {}
    _ttl_seconds = 24 * 60 * 60
    _STAGE_WEIGHTS = {
        "text": 0.25,
        "image_polish": 0.25,
        "image_generate": 0.40,
        "material_create": 0.10,
    }

    @classmethod
    async def init_task(cls, task_id: str, user_id: int, config_id: int, total: int, config_name: str = "") -> None:
        async with cls._lock:
            cls._cleanup_locked()
            cls._cache[task_id] = {
                "task_id": task_id,
                "user_id": user_id,
                "config_id": config_id,
                "config_name": str(config_name or "").strip(),
                "total": total,
                "current": 0,
                "success": 0,
                "failed": 0,
                "status": "pending",
                "message": "等待开始",
                "progress_percent": 0.0,
                "active_stage": "pending",
                "stage_label": "等待开始",
                "stage_detail": "",
                "step_counts": {
                    "text": {"done": 0, "total": total},
                    "image_polish": {"done": 0, "total": total},
                    "image_generate": {"done": 0, "total": total},
                    "material_create": {"done": 0, "total": total},
                },
                "created_material_ids": [],
                "errors": [],
                "finished": False,
                "last_access": time.time(),
            }

    @classmethod
    async def mark_running(cls, task_id: str, message: str = "正在生成素材") -> None:
        await cls.update_task(
            task_id,
            status="running",
            message=message,
            active_stage="running",
            stage_label=message,
            finished=False,
        )

    @classmethod
    async def update_stage(
        cls,
        task_id: str,
        stage: str,
        label: str,
        detail: str = "",
        increment: bool = False,
    ) -> None:
        async with cls._lock:
            record = cls._cache.get(task_id)
            if not record:
                return
            step_counts = record.setdefault("step_counts", {})
            if stage not in step_counts:
                total = int(record.get("total") or 0)
                step_counts[stage] = {"done": 0, "total": total}
            if increment:
                stage_item = step_counts[stage]
                stage_item["done"] = min(
                    int(stage_item.get("done") or 0) + 1,
                    int(stage_item.get("total") or 0),
                )
            record["active_stage"] = stage
            record["stage_label"] = label
            record["stage_detail"] = detail
            record["message"] = detail or label
            record["status"] = "running"
            record["progress_percent"] = cls._compute_progress_percent(record)
            record["last_access"] = time.time()

    @classmethod
    async def add_success(cls, task_id: str, material_id: int, message: str = "素材创建成功") -> None:
        async with cls._lock:
            record = cls._cache.get(task_id)
            if not record:
                return
            record["current"] = int(record.get("current") or 0) + 1
            record["success"] = int(record.get("success") or 0) + 1
            step_counts = record.setdefault("step_counts", {})
            material_stage = step_counts.setdefault(
                "material_create",
                {"done": 0, "total": int(record.get("total") or 0)},
            )
            material_stage["done"] = min(
                int(material_stage.get("done") or 0) + 1,
                int(material_stage.get("total") or 0),
            )
            record.setdefault("created_material_ids", []).append(material_id)
            record["message"] = message
            record["status"] = "running"
            record["active_stage"] = "material_create"
            record["stage_label"] = "素材入库完成"
            record["stage_detail"] = message
            record["progress_percent"] = cls._compute_progress_percent(record)
            record["last_access"] = time.time()

    @classmethod
    async def add_failed(cls, task_id: str, error: str) -> None:
        async with cls._lock:
            record = cls._cache.get(task_id)
            if not record:
                return
            record["current"] = int(record.get("current") or 0) + 1
            record["failed"] = int(record.get("failed") or 0) + 1
            errors = record.setdefault("errors", [])
            errors.append(str(error)[:500])
            record["message"] = str(error)[:200]
            record["status"] = "running"
            record["stage_detail"] = str(error)[:200]
            record["progress_percent"] = cls._compute_progress_percent(record)
            record["last_access"] = time.time()

    @classmethod
    async def finish(cls, task_id: str, status: str, message: str) -> None:
        await cls.update_task(
            task_id,
            status=status,
            message=message,
            active_stage="finished",
            stage_label="任务完成",
            stage_detail=message,
            progress_percent=100.0,
            finished=True,
        )

    @classmethod
    async def update_task(cls, task_id: str, **kwargs: Any) -> None:
        async with cls._lock:
            record = cls._cache.get(task_id)
            if not record:
                return
            record.update(kwargs)
            if "progress_percent" not in kwargs:
                record["progress_percent"] = cls._compute_progress_percent(record)
            record["last_access"] = time.time()

    @classmethod
    async def get_task_snapshot(cls, task_id: str) -> dict[str, Any] | None:
        async with cls._lock:
            cls._cleanup_locked()
            record = cls._cache.get(task_id)
            if not record:
                return None
            record["last_access"] = time.time()
            snapshot = deepcopy(record)
            snapshot.pop("last_access", None)
            return snapshot

    @classmethod
    async def list_user_tasks(cls, user_id: int) -> list[dict[str, Any]]:
        async with cls._lock:
            cls._cleanup_locked()
            tasks: list[dict[str, Any]] = []
            for record in cls._cache.values():
                if int(record.get("user_id") or 0) != int(user_id):
                    continue
                record["last_access"] = time.time()
                snapshot = deepcopy(record)
                snapshot.pop("last_access", None)
                tasks.append(snapshot)
            tasks.sort(key=lambda item: (bool(item.get("finished")), item.get("task_id", "")))
            return tasks

    @classmethod
    def _cleanup_locked(cls) -> None:
        now = time.time()
        expired_ids = [
            task_id
            for task_id, record in cls._cache.items()
            if now - float(record.get("last_access") or 0) > cls._ttl_seconds
        ]
        for task_id in expired_ids:
            cls._cache.pop(task_id, None)

    @classmethod
    def _compute_progress_percent(cls, record: dict[str, Any]) -> float:
        step_counts = record.get("step_counts") or {}
        progress = 0.0
        for stage, weight in cls._STAGE_WEIGHTS.items():
            stage_item = step_counts.get(stage) or {}
            total = max(1, int(stage_item.get("total") or record.get("total") or 1))
            done = min(int(stage_item.get("done") or 0), total)
            progress += (done / total) * weight
        return round(min(progress, 1.0) * 100, 2)
