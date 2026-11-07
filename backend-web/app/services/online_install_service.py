"""
在线安装任务服务。

功能：共享 Redis 任务与增量日志、同一服务器互斥、请求幂等、线程执行阻塞 SSH。
任务使用授权范围隔离，密码、私钥及口令仅用于本次 SSH 连接，不存入任务缓存。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from uuid import UUID

from app.core.config import get_settings
from app.schemas.online_install import OnlineInstallRequest
from app.services.online_install_ssh import OnlineInstallError, run_install_script
from common.db.redis_client import DistributedLock, get_redis_client
from common.utils.time_utils import get_beijing_now


def _task_key(scope_id: str, task_id: UUID) -> str:
    """按授权范围和随机任务标识生成隔离缓存键，返回 Redis 任务前缀。"""
    scope_hash = hashlib.sha256(scope_id.encode()).hexdigest()
    return f"online_install:task:{scope_hash}:{task_id}"


def _request_signature(request: OnlineInstallRequest) -> str:
    """哈希完整连接配置，用于识别同一请求的幂等重试而不缓存原始认证凭据。"""
    return hashlib.sha256(request.model_dump_json().encode()).hexdigest()


async def _read_task(key: str) -> dict | None:
    """读取共享缓存中的真实任务元数据；缓存异常向调用者传播。"""
    client = await get_redis_client()
    raw = await client.get(key)
    return json.loads(raw) if raw else None


async def _save_task(key: str, task: dict, output: str | None = None) -> None:
    """原子保存心跳、任务结果与新增原始输出，并更新有限缓存保留期。"""
    client = await get_redis_client()
    retention = get_settings().online_install_retention_seconds
    task["heartbeat_at"] = get_beijing_now().timestamp()
    async with client.pipeline(transaction=True) as pipe:
        pipe.set(key, json.dumps(task, ensure_ascii=False), ex=retention)
        if output:
            pipe.rpush(f"{key}:logs", output)
        pipe.expire(f"{key}:logs", retention)
        await pipe.execute()


async def prepare_install_task(
    scope_id: str, task_id: UUID, request: OnlineInstallRequest, log,
) -> tuple[dict, DistributedLock | None]:
    """创建共享任务并锁定目标；同一配置重试返回原任务，不重复执行。

    Args:
        scope_id: 路由按已确认权限生成的用户或访客范围标识。
        task_id: 前端为本次安装生成且重试复用的 UUID。
        request: 已校验的远程安装参数。
        log: 包含请求标识和连接上下文的日志对象。
    Returns:
        任务摘要与锁；锁为 None 表示幂等重试，不能再安排 SSH 执行。
    """
    key = _task_key(scope_id, task_id)
    signature = _request_signature(request)
    existing = await _read_task(key)
    if existing:
        if existing["signature"] != signature:
            raise OnlineInstallError("此安装请求已提交，连接配置发生变化，请重新开始安装")
        return {"task_id": str(task_id)}, None
    settings = get_settings()
    target = hashlib.sha256(f"{request.host}:{request.port}".encode()).hexdigest()
    lock = DistributedLock(
        f"online_install:target:{target}",
        expire=settings.online_install_timeout + settings.online_install_connect_timeout * 3 + 60,
    )
    if not await lock.acquire(blocking=False):
        existing = await _read_task(key)
        if existing and existing["signature"] == signature:
            return {"task_id": str(task_id)}, None
        raise OnlineInstallError("此服务器已有安装任务正在执行，请等待完成后再试")
    try:
        # 同一任务在读取缓存与获取目标锁之间可能已由另一请求创建并完成。
        existing = await _read_task(key)
        if existing:
            if existing["signature"] != signature:
                raise OnlineInstallError("此安装请求已提交，连接配置发生变化，请重新开始安装")
            await lock.release()
            return {"task_id": str(task_id)}, None
        task = {
            "task_id": str(task_id), "signature": signature,
            "created_at": get_beijing_now().strftime("%Y-%m-%d %H:%M:%S"),
            "heartbeat_at": get_beijing_now().timestamp(),
            "finished": False, "success": None, "exit_code": None,
            "message": "安装任务已启动，正在连接服务器…",
        }
        client = await get_redis_client()
        created = await client.set(
            key, json.dumps(task, ensure_ascii=False),
            ex=settings.online_install_retention_seconds, nx=True,
        )
        if not created:
            existing = await _read_task(key)
            if not existing or existing["signature"] != signature:
                raise OnlineInstallError("此安装请求已提交，连接配置发生变化，请重新开始安装")
            await lock.release()
            return {"task_id": str(task_id)}, None
    except BaseException:
        await lock.release()
        raise
    log.info(f"[在线安装] 创建任务完成：task_id={task_id} target={request.host}:{request.port}")
    return {"task_id": str(task_id)}, lock


def _next_event(iterator) -> dict | None:
    """在线程读取下一段阻塞 SSH 输出，结束返回 None，避免 StopIteration 穿透 Future。"""
    return next(iterator, None)


async def execute_install_task(
    scope_id: str, task_id: UUID, request: OnlineInstallRequest, lock: DistributedLock, log,
) -> None:
    """执行已创建任务，实时保存输出，记录真实退出码；任何异常都保存明确失败结果。"""
    key = _task_key(scope_id, task_id)
    iterator = run_install_script(request, log)
    task = None
    worker = None
    try:
        task = await _read_task(key)
        if task is None:
            raise OnlineInstallError("安装任务缓存已失效，未执行远程安装")
        await _save_task(key, task, f"[{task['created_at']}] 正在连接 {request.host}:{request.port}…\n")
        while True:
            worker = asyncio.create_task(asyncio.to_thread(_next_event, iterator))
            event = await asyncio.shield(worker)
            worker = None
            if event is None:
                break
            output = event.get("output")
            if output:
                log.info(f"[在线安装] task_id={task_id} 服务器输出：{output}")
            if "exit_code" in event:
                # 先记录退出结果；全部输出关闭并写入最终日志后才发布完成状态。
                task.update(success=event["exit_code"] == 0, exit_code=event["exit_code"])
                task["message"] = "闲鱼自动回复安装完成" if task["success"] else f"安装失败，脚本退出码：{event['exit_code']}，请查看安装日志"
            await _save_task(key, task, output)
        if task["exit_code"] is None:
            raise OnlineInstallError("未收到安装结果，请检查目标服务器的实际状态")
        if task["success"]:
            log.info(f"[在线安装] task_id={task_id} result={task['message']}")
        else:
            log.error(f"[在线安装] task_id={task_id} result={task['message']}")
        task["finished"] = True
        await _save_task(key, task, f"\n[{get_beijing_now():%Y-%m-%d %H:%M:%S}] {task['message']}\n")
    except (Exception, asyncio.CancelledError) as exc:
        log.exception(f"[在线安装] 任务执行失败：task_id={task_id} exception_type={type(exc).__name__}")
        if task is not None:
            message = str(exc) if isinstance(exc, OnlineInstallError) else f"安装任务异常：{exc or type(exc).__name__}，请检查目标服务器的实际状态"
            task.update(finished=True, success=False, message=message)
            try:
                await _save_task(key, task, f"\n[{get_beijing_now():%Y-%m-%d %H:%M:%S}] {message}\n")
            except Exception:
                log.exception(f"[在线安装] 保存失败结果异常：task_id={task_id}")
        if isinstance(exc, asyncio.CancelledError):
            raise
    finally:
        try:
            # 取消请求不能中断正在执行的线程，先等待本次短轮询再关闭生成器与 SSH。
            if worker is not None:
                try:
                    await worker
                except Exception:
                    log.exception(f"[在线安装] 关闭前等待 SSH 输出失败：task_id={task_id}")
            await asyncio.to_thread(iterator.close)
        finally:
            try:
                released = await lock.release()
                if not released:
                    log.warning(f"[在线安装] 目标锁释放失败或已过期：task_id={task_id}")
            except Exception:
                log.exception(f"[在线安装] 释放目标锁异常，等待锁超时回收：task_id={task_id}")


async def get_install_logs(scope_id: str, task_id: UUID, cursor: int) -> dict:
    """按授权范围读取最多 100 段新增日志；发现失去心跳的任务时明确提示结果无法确认。

    Args:
        scope_id: 与创建任务一致的授权范围。
        task_id: 本次安装 UUID。
        cursor: 已读取日志段数，页面刷新后可从零重新读取。
    Returns:
        日志、下一游标、是否读取完毕及真实任务结果。
    """
    key = _task_key(scope_id, task_id)
    client = await get_redis_client()
    # 元数据、日志总数和日志片段必须取同一快照，避免完成状态与末尾日志错位。
    async with client.pipeline(transaction=True) as pipe:
        pipe.get(key)
        pipe.llen(f"{key}:logs")
        pipe.lrange(f"{key}:logs", cursor, cursor + 99)
        raw, total, logs = await pipe.execute()
    if raw is None:
        raise OnlineInstallError("安装任务不存在、已过保留期或无权访问")
    task = json.loads(raw)
    if cursor > total:
        raise OnlineInstallError("安装日志位置无效，请重新加载日志")
    stale_after = max(90, get_settings().online_install_connect_timeout * 3 + 30)
    if not task["finished"] and get_beijing_now().timestamp() - task["heartbeat_at"] > stale_after:
        task.update(finished=True, success=False, message="安装任务失去连接，无法确认结果，请检查目标服务器的实际状态")
    return {
        "task_id": str(task_id), "logs": logs, "cursor": cursor + len(logs),
        "has_more": cursor + len(logs) < total,
        "finished": task["finished"], "success": task["success"],
        "exit_code": task["exit_code"], "message": task["message"],
        "created_at": task["created_at"],
    }
