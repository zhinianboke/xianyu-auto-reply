"""
意见反馈路由

功能：
1. 用户提交反馈
2. 用户查看自己的反馈列表
3. 管理员查看所有反馈
4. 用户和管理员可以多次回复（对话形式）
5. 管理员标记解决状态
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_admin_user, get_db_session
from common.models.user import User, UserRole
from common.models.feedback import Feedback, FeedbackType
from common.models.feedback_message import FeedbackMessage
from common.schemas.common import ApiResponse
from common.utils.text_utils import escape_xss

from common.utils.time_utils import get_beijing_now_naive, safe_isoformat
from common.utils.pagination import execute_paginated_with_filters
router = APIRouter(tags=["feedback"])


@router.get("/stats", response_model=ApiResponse)
async def get_feedback_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """获取反馈统计数据（总数、已解决、待解决）- 所有用户看到相同的全局统计"""
    # 总数
    total_query = select(func.count(Feedback.id))
    total = (await db.execute(total_query)).scalar() or 0
    
    # 已解决数
    resolved_query = select(func.count(Feedback.id)).where(Feedback.is_resolved == True)
    resolved = (await db.execute(resolved_query)).scalar() or 0
    
    # 待解决数
    pending = total - resolved
    
    return ApiResponse(
        success=True,
        data={
            "total": total,
            "resolved": resolved,
            "pending": pending,
        }
    )


@router.get("", response_model=ApiResponse)
async def get_feedbacks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    is_resolved: bool | None = None,
    feedback_type: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """获取反馈列表（普通用户只能看自己的，管理员可以看所有）"""
    filters = []
    # 非管理员只能看自己的
    if current_user.role != UserRole.ADMIN:
        filters.append(Feedback.user_id == current_user.id)
    # 筛选条件
    if is_resolved is not None:
        filters.append(Feedback.is_resolved == is_resolved)
    if feedback_type:
        try:
            filters.append(Feedback.feedback_type == FeedbackType(feedback_type))
        except ValueError:
            pass

    feedbacks, total = await execute_paginated_with_filters(
        db, Feedback,
        filters=filters,
        order_by=[desc(Feedback.created_at)],
        page=page, page_size=page_size,
    )
    
    items = []
    for fb in feedbacks:
        # 获取消息数量
        msg_count_query = select(func.count(FeedbackMessage.id)).where(
            FeedbackMessage.feedback_id == fb.id
        )
        msg_count = (await db.execute(msg_count_query)).scalar() or 0
        
        items.append({
            "id": fb.id,
            "user_id": fb.user_id,
            "cookie_id": fb.cookie_id,
            "title": fb.title,
            "content": fb.content,
            "feedback_type": fb.feedback_type.value,
            "images": json.loads(fb.images) if fb.images else [],
            "is_resolved": fb.is_resolved,
            "resolved_at": safe_isoformat(fb.resolved_at),
            "message_count": msg_count + 1,  # +1 是原始内容
            "created_at": safe_isoformat(fb.created_at),
        })
    
    return ApiResponse(
        success=True,
        data={
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/{feedback_id}", response_model=ApiResponse)
async def get_feedback_detail(
    feedback_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """获取反馈详情（包含对话消息，按时间升序）"""
    result = await db.execute(select(Feedback).where(Feedback.id == feedback_id))
    feedback = result.scalar_one_or_none()
    
    if not feedback:
        return ApiResponse(success=False, message="反馈不存在")
    
    # 非管理员只能看自己的反馈
    if current_user.role != UserRole.ADMIN and feedback.user_id != current_user.id:
        return ApiResponse(success=False, message="无权查看此反馈")
    
    # 获取对话消息（按时间升序）
    msg_query = (
        select(FeedbackMessage)
        .where(FeedbackMessage.feedback_id == feedback_id)
        .order_by(asc(FeedbackMessage.created_at))
    )
    msg_result = await db.execute(msg_query)
    db_messages = msg_result.scalars().all()
    
    # 构建消息列表，第一条是原始内容
    messages = [{
        "id": 0,
        "is_admin": False,
        "content": feedback.content,
        "created_at": safe_isoformat(feedback.created_at),
    }]
    
    # 兼容旧数据：如果有admin_reply但没有消息记录
    if feedback.admin_reply and not db_messages:
        messages.append({
            "id": -1,
            "is_admin": True,
            "content": feedback.admin_reply,
            "created_at": safe_isoformat(feedback.resolved_at),
        })
    
    # 添加消息表中的记录
    for msg in db_messages:
        messages.append({
            "id": msg.id,
            "is_admin": msg.is_admin,
            "content": msg.content,
            "created_at": safe_isoformat(msg.created_at),
        })
    
    return ApiResponse(
        success=True,
        data={
            "id": feedback.id,
            "user_id": feedback.user_id,
            "cookie_id": feedback.cookie_id,
            "title": feedback.title,
            "feedback_type": feedback.feedback_type.value,
            "images": json.loads(feedback.images) if feedback.images else [],
            "is_resolved": feedback.is_resolved,
            "resolved_at": safe_isoformat(feedback.resolved_at),
            "created_at": safe_isoformat(feedback.created_at),
            "messages": messages,
        }
    )


@router.post("", response_model=ApiResponse)
async def create_feedback(
    title: str,
    content: str,
    feedback_type: str,
    cookie_id: str | None = None,
    images: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """提交反馈，对内容进行XSS转义"""
    try:
        ft = FeedbackType(feedback_type)
    except ValueError:
        return ApiResponse(success=False, message="无效的反馈类型")
    
    images_list = []
    if images:
        try:
            images_list = json.loads(images)
            if not isinstance(images_list, list):
                images_list = []
        except json.JSONDecodeError:
            images_list = []
    
    # XSS转义
    feedback = Feedback(
        user_id=current_user.id,
        cookie_id=cookie_id,
        title=escape_xss(title),
        content=escape_xss(content),
        feedback_type=ft,
        images=json.dumps(images_list) if images_list else None,
    )
    
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)
    
    return ApiResponse(success=True, message="反馈提交成功", data={"id": feedback.id})


@router.post("/{feedback_id}/reply", response_model=ApiResponse)
async def reply_feedback(
    feedback_id: int,
    content: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """回复反馈（用户和管理员都可以回复），对内容进行XSS转义"""
    result = await db.execute(select(Feedback).where(Feedback.id == feedback_id))
    feedback = result.scalar_one_or_none()
    
    if not feedback:
        return ApiResponse(success=False, message="反馈不存在")
    
    # 非管理员只能回复自己的反馈
    if current_user.role != UserRole.ADMIN and feedback.user_id != current_user.id:
        return ApiResponse(success=False, message="无权回复此反馈")
    
    # 创建消息，XSS转义
    message = FeedbackMessage(
        feedback_id=feedback_id,
        user_id=current_user.id,
        content=escape_xss(content),
        is_admin=(current_user.role == UserRole.ADMIN),
    )
    
    db.add(message)
    await db.commit()
    await db.refresh(message)
    
    return ApiResponse(success=True, message="回复成功", data={"id": message.id})


@router.put("/{feedback_id}/resolve", response_model=ApiResponse)
async def resolve_feedback(
    feedback_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db_session),
):
    """标记反馈为已解决（仅管理员）"""
    result = await db.execute(select(Feedback).where(Feedback.id == feedback_id))
    feedback = result.scalar_one_or_none()
    
    if not feedback:
        return ApiResponse(success=False, message="反馈不存在")
    
    feedback.is_resolved = True
    feedback.resolved_at = get_beijing_now_naive()
    await db.commit()
    
    return ApiResponse(success=True, message="已标记为解决")


@router.put("/{feedback_id}/unresolve", response_model=ApiResponse)
async def unresolve_feedback(
    feedback_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db_session),
):
    """标记反馈为未解决（仅管理员）"""
    result = await db.execute(select(Feedback).where(Feedback.id == feedback_id))
    feedback = result.scalar_one_or_none()
    
    if not feedback:
        return ApiResponse(success=False, message="反馈不存在")
    
    feedback.is_resolved = False
    feedback.resolved_at = None
    await db.commit()
    
    return ApiResponse(success=True, message="已标记为未解决")


@router.delete("/{feedback_id}", response_model=ApiResponse)
async def delete_feedback(
    feedback_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db_session),
):
    """删除反馈（仅管理员）"""
    result = await db.execute(select(Feedback).where(Feedback.id == feedback_id))
    feedback = result.scalar_one_or_none()
    
    if not feedback:
        return ApiResponse(success=False, message="反馈不存在")
    
    # 先删除关联的消息
    await db.execute(
        FeedbackMessage.__table__.delete().where(FeedbackMessage.feedback_id == feedback_id)
    )
    
    await db.delete(feedback)
    await db.commit()
    
    return ApiResponse(success=True, message="删除成功")
