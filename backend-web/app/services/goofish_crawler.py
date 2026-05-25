"""
Goofish 定时采集任务管理器

管理 Goofish 商品采集任务的创建、启动、停止和执行
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.session import async_session_maker
from common.models.goofish_crawl_item import GoofishCrawlItem
from common.models.goofish_crawl_job import GoofishCrawlJob
from common.models.xy_account import XYAccount


@dataclass(frozen=True)
class GoofishRunOnceResult:
    """采集执行结果"""
    success: bool
    upserted: int = 0
    total: int = 0
    error: str | None = None


class GoofishCrawlManager:
    """
    Goofish 采集任务管理器
    
    负责管理定时采集任务的生命周期，支持：
    - 启动/停止单个任务
    - 批量停止所有任务
    - 立即执行一次采集
    """
    
    _instance: Optional["GoofishCrawlManager"] = None
    
    def __init__(self, loop: asyncio.AbstractEventLoop | None = None):
        self.loop = loop
        self.tasks: Dict[int, asyncio.Task] = {}
        self._task_locks: Dict[int, asyncio.Lock] = {}
        self._lock = asyncio.Lock()
        self._run_semaphore = asyncio.Semaphore(1)
    
    @classmethod
    def get_instance(cls, loop: asyncio.AbstractEventLoop | None = None) -> "GoofishCrawlManager":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = GoofishCrawlManager(loop=loop)
        elif loop and cls._instance.loop is None:
            cls._instance.loop = loop
        return cls._instance
    
    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """设置事件循环"""
        self.loop = loop
    
    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """获取事件循环"""
        if self.loop:
            return self.loop
        return asyncio.get_running_loop()
    
    def _get_task_lock(self, job_id: int) -> asyncio.Lock:
        """获取任务锁"""
        lock = self._task_locks.get(job_id)
        if lock is None:
            lock = asyncio.Lock()
            self._task_locks[job_id] = lock
        return lock
    
    def is_running(self, job_id: int) -> bool:
        """检查任务是否正在运行"""
        task = self.tasks.get(job_id)
        return bool(task and not task.done())
    
    def start_job(self, *, job_id: int) -> None:
        """启动采集任务"""
        loop = self._get_loop()
        loop.create_task(self._start_job_async(job_id=job_id))
    
    async def _start_job_async(self, *, job_id: int) -> None:
        """异步启动采集任务"""
        lock = self._get_task_lock(job_id)
        async with lock:
            # 如果任务已存在，先停止
            existing = self.tasks.get(job_id)
            if existing and not existing.done():
                existing.cancel()
                try:
                    await existing
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass
            
            # 创建新任务
            loop = self._get_loop()
            self.tasks[job_id] = loop.create_task(self._job_loop(job_id=job_id))
    
    async def stop_job(self, *, job_id: int) -> None:
        """停止采集任务"""
        lock = self._get_task_lock(job_id)
        async with lock:
            existing = self.tasks.get(job_id)
            if not existing:
                return
            if not existing.done():
                existing.cancel()
                try:
                    await existing
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass
            self.tasks.pop(job_id, None)
    
    async def stop_all(self) -> None:
        """停止所有采集任务"""
        async with self._lock:
            job_ids = list(self.tasks.keys())
        for job_id in job_ids:
            await self.stop_job(job_id=job_id)
    
    async def _job_loop(self, *, job_id: int) -> None:
        """任务执行循环"""
        try:
            while True:
                async with async_session_maker() as session:
                    row = await session.execute(
                        select(GoofishCrawlJob).where(GoofishCrawlJob.id == job_id)
                    )
                    job = row.scalars().first()
                    if not job or not bool(job.enabled):
                        return
                    interval = max(60, int(job.interval_seconds or 900))
                    owner_id = int(job.owner_id)
                
                await self.run_once(job_id=job_id, owner_id=owner_id)
                await asyncio.sleep(interval)
                
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.warning(f"Goofish 采集任务循环异常 job_id={job_id}: {exc}")
    
    async def run_once(self, *, job_id: int, owner_id: int) -> Dict[str, Any]:
        """立即执行一次采集"""
        lock = self._get_task_lock(job_id)
        async with lock:
            async with async_session_maker() as session:
                # 查询任务
                job_result = await session.execute(
                    select(GoofishCrawlJob).where(
                        GoofishCrawlJob.id == job_id,
                        GoofishCrawlJob.owner_id == owner_id,
                    )
                )
                job = job_result.scalars().first()
                
                if not job:
                    return GoofishRunOnceResult(success=False, error="job_not_found").__dict__
                if not bool(job.enabled):
                    return GoofishRunOnceResult(success=False, error="job_disabled").__dict__
                
                # 查询账号
                account_result = await session.execute(
                    select(XYAccount).where(XYAccount.account_id == job.cookie_id)
                )
                account = account_result.scalars().first()
                
                if not account or not account.cookie:
                    await self._record_run(session, job_id, success=False, error="account_cookie_missing")
                    return GoofishRunOnceResult(success=False, error="account_cookie_missing").__dict__
                
                # 执行采集
                try:
                    from app.services.compass.goofish_compass import (
                        GoofishCompassConfig,
                        GoofishCompassService,
                    )
                    
                    config = GoofishCompassConfig(
                        headless=not bool(getattr(account, "show_browser", False)),
                        detail_concurrency=3,
                        navigation_timeout_ms=30000,
                        network_idle_timeout_ms=15000,
                        detail_response_timeout_ms=7000,
                    )
                    
                    async def _do_search() -> Dict[str, Any]:
                        service = GoofishCompassService(
                            user_id=str(owner_id),
                            cookie_value=account.cookie,
                            config=config,
                        )
                        return await service.search(
                            keyword=job.keyword,
                            start_page=job.start_page,
                            pages=job.pages,
                            page_size=job.page_size,
                            fetch_detail=bool(job.fetch_detail),
                            detail_limit=job.detail_limit,
                        )
                    
                    async with self._run_semaphore:
                        result = await _do_search()
                        
                except Exception as exc:
                    await self._record_run(session, job_id, success=False, error=str(exc))
                    return GoofishRunOnceResult(success=False, error=str(exc)).__dict__
                
                error = result.get("error")
                items = result.get("items") or []
                total = int(result.get("total") or len(items) or 0)
                
                if error:
                    await self._record_run(session, job_id, success=False, error=str(error))
                    return GoofishRunOnceResult(success=False, total=total, error=str(error)).__dict__
                
                # 保存采集结果
                upserted = await self._upsert_items(session, job_id, items)
                await self._record_run(session, job_id, success=True, error=None)
                
                return GoofishRunOnceResult(success=True, upserted=upserted, total=total).__dict__
    
    async def _record_run(
        self,
        session: AsyncSession,
        job_id: int,
        success: bool,
        error: str | None = None,
    ) -> None:
        """记录执行结果"""
        from sqlalchemy import update
        
        now = datetime.now(timezone.utc)
        await session.execute(
            update(GoofishCrawlJob)
            .where(GoofishCrawlJob.id == job_id)
            .values(last_run_at=now, last_error=None if success else (error or "unknown_error"))
        )
        await session.commit()
    
    async def _upsert_items(
        self,
        session: AsyncSession,
        job_id: int,
        items: list[Dict[str, Any]],
    ) -> int:
        """保存采集结果"""
        from sqlalchemy.dialects.mysql import insert as mysql_insert
        
        now = datetime.now(timezone.utc)
        values: list[Dict[str, Any]] = []
        
        for item in items:
            item_id = str(item.get("item_id") or "").strip()
            if not item_id:
                continue
            values.append({
                "job_id": job_id,
                "item_id": item_id,
                "title": item.get("title"),
                "price": item.get("price"),
                "area": item.get("area"),
                "seller_name": item.get("seller_name"),
                "item_url": item.get("item_url"),
                "main_image": item.get("main_image"),
                "publish_time": item.get("publish_time"),
                "want_count": item.get("want_count"),
                "view_count": item.get("view_count"),
                "description": item.get("description"),
                "detail_error": item.get("detail_error"),
                "fetched_at": now,
            })
        
        if not values:
            return 0
        
        stmt = mysql_insert(GoofishCrawlItem).values(values)
        stmt = stmt.on_duplicate_key_update(
            title=stmt.inserted.title,
            price=stmt.inserted.price,
            area=stmt.inserted.area,
            seller_name=stmt.inserted.seller_name,
            item_url=stmt.inserted.item_url,
            main_image=stmt.inserted.main_image,
            publish_time=stmt.inserted.publish_time,
            want_count=stmt.inserted.want_count,
            view_count=stmt.inserted.view_count,
            description=stmt.inserted.description,
            detail_error=stmt.inserted.detail_error,
            fetched_at=stmt.inserted.fetched_at,
        )
        await session.execute(stmt)
        await session.commit()
        return len(values)
    
    def get_running_tasks(self) -> list[int]:
        """获取正在运行的任务ID列表"""
        return [job_id for job_id, task in self.tasks.items() if not task.done()]


# 全局实例获取函数
def get_goofish_crawl_manager(
    loop: asyncio.AbstractEventLoop | None = None,
) -> GoofishCrawlManager:
    """获取全局 Goofish 采集任务管理器"""
    return GoofishCrawlManager.get_instance(loop=loop)
