"""
在线聊天(新) - 快捷短语 API 路由

功能：
1. 查询当前用户的快捷短语列表
2. 新增快捷短语
3. 更新快捷短语
4. 删除快捷短语

与 chat_new.py 共用同一 prefix="/chat-new"，按功能拆分为独立 router 以控制单文件体积。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user, get_db_session
from common.models import ChatQuickPhrase, User
from common.schemas.common import ApiResponse


router = APIRouter(prefix="/chat-new")


class QuickPhraseRequest(BaseModel):
    """快捷短语新增/更新请求体"""
    title: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=2000)
    sort_order: int = 0


def _quick_phrase_data(phrase: ChatQuickPhrase) -> dict:
    """将快捷短语 ORM 对象转换为前端所需的字典结构"""
    return {
        "id": phrase.id,
        "title": phrase.title,
        "content": phrase.content,
        "sort_order": phrase.sort_order,
    }


@router.get("/quick-phrases")
async def list_quick_phrases(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """查询当前用户的快捷短语列表（按排序值、ID 升序）"""
    result = await db.execute(
        select(ChatQuickPhrase)
        .where(ChatQuickPhrase.owner_id == current_user.id)
        .order_by(ChatQuickPhrase.sort_order.asc(), ChatQuickPhrase.id.asc())
    )
    return ApiResponse(success=True, data=[_quick_phrase_data(item) for item in result.scalars().all()])


@router.post("/quick-phrases")
async def create_quick_phrase(
    req: QuickPhraseRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """新增一条快捷短语，归属于当前用户"""
    phrase = ChatQuickPhrase(
        owner_id=current_user.id,
        title=req.title.strip(),
        content=req.content.strip(),
        sort_order=req.sort_order,
    )
    db.add(phrase)
    await db.commit()
    await db.refresh(phrase)
    return ApiResponse(success=True, message="快捷短语已添加", data=_quick_phrase_data(phrase))


@router.put("/quick-phrases/{phrase_id}")
async def update_quick_phrase(
    phrase_id: int,
    req: QuickPhraseRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """更新指定快捷短语（仅限本人所有）"""
    result = await db.execute(
        select(ChatQuickPhrase).where(
            ChatQuickPhrase.id == phrase_id,
            ChatQuickPhrase.owner_id == current_user.id,
        )
    )
    phrase = result.scalar_one_or_none()
    if not phrase:
        return ApiResponse(success=False, message="快捷短语不存在")
    phrase.title = req.title.strip()
    phrase.content = req.content.strip()
    phrase.sort_order = req.sort_order
    await db.commit()
    await db.refresh(phrase)
    return ApiResponse(success=True, message="快捷短语已更新", data=_quick_phrase_data(phrase))


@router.delete("/quick-phrases/{phrase_id}")
async def delete_quick_phrase(
    phrase_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """删除指定快捷短语（仅限本人所有）"""
    result = await db.execute(
        select(ChatQuickPhrase).where(
            ChatQuickPhrase.id == phrase_id,
            ChatQuickPhrase.owner_id == current_user.id,
        )
    )
    phrase = result.scalar_one_or_none()
    if not phrase:
        return ApiResponse(success=False, message="快捷短语不存在")
    await db.delete(phrase)
    await db.commit()
    return ApiResponse(success=True, message="快捷短语已删除")
