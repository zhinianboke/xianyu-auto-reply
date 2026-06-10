"""
在线聊天(新) API路由

功能：
1. 获取当前用户的账号列表（供前端选择）
2. 连接/断开指定账号的IM
3. 获取会话列表
4. 获取聊天记录
5. 获取已连接账号列表
6. WebSocket接口，实时推送IM消息给前端

与自动回复WebSocket隔离，使用独立的token和device_id
"""
from __future__ import annotations

import asyncio
import base64
import json
import time
from urllib.parse import unquote

from fastapi import APIRouter, Depends
from loguru import logger
from pydantic import BaseModel

from app.api.deps import get_current_active_user, get_db_session
from app.services.chat_new import get_im_session_manager
from app.services.chat_new.avatar_service import get_owner_user_info, get_user_info, AVATAR_CACHE_PREFIX, AVATAR_CACHE_TTL
from app.services.chat_new.official_blacklist_service import official_blacklist_request
from common.db.redis_client import get_redis_client
from common.models import User, XYAccount
from common.schemas.common import ApiResponse
from common.utils.auth_scope import is_admin_user
from common.utils.xianyu_utils import trans_cookies
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


# 无效昵称黑名单（系统生成的非真实用户昵称 / 系统消息摘要）
_INVALID_NICK_SET = {
    "交易消息", "系统消息", "卡片消息",
    "我完成了评价", "对方完成了评价", "快给ta一个评价吧～",
    "卖家已发货", "买家已付款", "买家已确认收货", "等待您发货",
    "超时未付款，系统关闭了订单",
}


def _is_valid_nick(name: str) -> bool:
    """
    检查昵称是否有效（非空、非纯数字、非系统昵称）

    过滤规则：
    1. 空值或纯空白
    2. 纯数字（可能是用户ID误当昵称）
    3. 精确匹配系统消息摘要黑名单
    4. 被方括号包裹的文本（如"[卡片消息]"去括号后匹配）
    """
    if not name or not name.strip():
        return False
    stripped = name.strip()
    if stripped.isdigit():
        return False
    if stripped in _INVALID_NICK_SET:
        return False
    # 处理可能带方括号的系统消息摘要，如 "[我完成了评价]"
    if stripped.startswith("[") and stripped.endswith("]"):
        inner = stripped[1:-1]
        if inner in _INVALID_NICK_SET:
            return False
    return True

router = APIRouter(prefix="/chat-new")


@router.get("/accounts")
async def list_accounts(
    page: int = 1,
    page_size: int = 20,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    获取账号列表（管理员查看所有账号，普通用户只看自己的），支持分页
    """
    try:
        is_admin = is_admin_user(current_user)

        # 基础条件：有cookie的账号
        base_where = [XYAccount.cookie.isnot(None), XYAccount.cookie != ""]
        if not is_admin:
            base_where.append(XYAccount.owner_id == current_user.id)

        # 查总数
        count_q = select(func.count()).select_from(XYAccount).where(*base_where)
        total = (await db.execute(count_q)).scalar() or 0

        # 分页查询，按状态排序（active在前）
        query = (
            select(XYAccount)
            .where(*base_where)
            .order_by(
                # active排前面
                func.IF(XYAccount.status == "active", 0, 1),
                XYAccount.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(query)
        accounts = result.scalars().all()

        # 管理员场景批量查用户名
        owner_map: dict[int, str] = {}
        if is_admin:
            owner_ids = list({acc.owner_id for acc in accounts if acc.owner_id})
            if owner_ids:
                user_result = await db.execute(
                    select(User).where(User.id.in_(owner_ids))
                )
                for u in user_result.scalars().all():
                    owner_map[u.id] = u.username or str(u.id)

        manager = get_im_session_manager()
        connected_ids = manager.get_connected_account_ids()

        items = []
        display_names_updated = False
        for acc in accounts:
            display_name = acc.display_name or ""
            if not display_name and acc.cookie:
                try:
                    tracknick = trans_cookies(acc.cookie).get("tracknick")
                    if tracknick:
                        display_name = unquote(tracknick)
                        acc.display_name = display_name
                        display_names_updated = True
                except Exception as e:
                    logger.warning(f"账号 {acc.account_id} 解析昵称失败: {e}")
            item = {
                "account_id": acc.account_id,
                "display_name": display_name,
                "remark": acc.remark or "",
                "connected": acc.account_id in connected_ids,
                "status": acc.status or "active",
            }
            if is_admin:
                item["owner"] = owner_map.get(acc.owner_id, str(acc.owner_id))
            items.append(item)
        if display_names_updated:
            await db.commit()

        return {
            "success": True,
            "data": items,
            "total": total,
            "hasMore": page * page_size < total,
        }

    except Exception as e:
        logger.error(f"获取账号列表失败: {e}")
        return ApiResponse(success=False, message=f"获取账号列表失败: {str(e)}")


@router.post("/connect/{account_id}")
async def connect_account(
    account_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    连接指定账号的IM WebSocket
    """
    try:
        # 校验账号归属（管理员可操作任意账号）
        query = select(XYAccount).where(XYAccount.account_id == account_id)
        if not is_admin_user(current_user):
            query = query.where(XYAccount.owner_id == current_user.id)
        result = await db.execute(query)
        account = result.scalar_one_or_none()
        if not account:
            return ApiResponse(success=False, message="账号不存在或无权操作")

        manager = get_im_session_manager()
        await manager.get_or_connect(account_id)
        return ApiResponse(success=True, message="连接成功")

    except ValueError as e:
        return ApiResponse(success=False, message=str(e))
    except Exception as e:
        logger.error(f"【{account_id}】连接IM失败: {e}")
        return ApiResponse(success=False, message=f"连接失败: {str(e)}")


@router.post("/disconnect/{account_id}")
async def disconnect_account(
    account_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """
    断开指定账号的IM WebSocket
    """
    try:
        manager = get_im_session_manager()
        await manager.disconnect(account_id)
        return ApiResponse(success=True, message="已断开连接")

    except Exception as e:
        logger.error(f"【{account_id}】断开IM失败: {e}")
        return ApiResponse(success=False, message=f"断开失败: {str(e)}")


@router.get("/conversations/{account_id}")
async def get_conversations(
    account_id: str,
    cursor: int = None,
    limit: int = 20,
    current_user: User = Depends(get_current_active_user),
):
    """
    获取指定账号的会话列表

    Args:
        account_id: 账号ID
        cursor: 分页游标（首页不传，翻页传nextCursor）
        limit: 每页数量，默认20
    """
    try:
        manager = get_im_session_manager()
        client = manager.clients.get(account_id)
        if not client or not client.is_connected:
            return ApiResponse(success=False, message="账号未连接，请先连接")

        body = await client.get_conversations(
            start_timestamp=cursor, limit=limit
        )

        # 检测IM错误响应（流控或其他服务端错误）
        if isinstance(body, dict) and "reason" in body:
            reason = body.get("reason", "")
            err_code = body.get("code", "")
            logger.warning(
                f"【{account_id}】IM会话列表返回错误, "
                f"code={err_code}, reason={reason}"
            )
            # 流控错误给前端提示
            if err_code == "400600001":
                return ApiResponse(success=False, message="请求过于频繁，请稍后再试")
            return ApiResponse(success=False, message=f"IM服务异常: {reason or err_code}")

        # 解析会话列表
        conversations = []
        user_convs = body.get("userConvs", [])
        for item in user_convs:
            # 实际会话数据嵌套在 singleChatUserConversation 中
            conv = item.get("singleChatUserConversation", item) if isinstance(item, dict) else item
            conv_info = _parse_conversation(conv, client.myid)
            if conv_info:
                conversations.append(conv_info)

        # 从 Redis 批量读取所有会话的缓存，按优先级确定昵称并回写更优数据
        try:
            redis_client = await get_redis_client()
            read_pipe = redis_client.pipeline()
            for c in conversations:
                read_pipe.get(f"{AVATAR_CACHE_PREFIX}{c['cid']}")
            results = await read_pipe.execute()

            write_pipe = redis_client.pipeline()
            need_write = False

            for c, cached_raw in zip(conversations, results):
                # 解析缓存数据
                cached_data = {}
                if cached_raw:
                    try:
                        parsed = json.loads(cached_raw) if isinstance(cached_raw, str) else cached_raw
                        if isinstance(parsed, str):
                            cached_data = {"avatar": parsed, "nick": ""}
                        elif isinstance(parsed, dict):
                            cached_data = parsed
                    except (json.JSONDecodeError, TypeError):
                        cached_data = {}

                cached_nick = cached_data.get("nick", "")
                cached_avatar = cached_data.get("avatar", "")
                conv_nick = c.get("otherUserName", "")  # 从会话列表 reminderTitle 提取的

                # 昵称优先级：会话列表有效昵称 > 缓存昵称
                if _is_valid_nick(conv_nick):
                    # 会话列表有有效昵称
                    # 如果缓存无昵称或缓存昵称带***而会话列表不带，则更新缓存
                    if not cached_nick or ("***" in cached_nick and "***" not in conv_nick):
                        new_cache = {"avatar": cached_avatar, "nick": conv_nick}
                        write_pipe.set(
                            f"{AVATAR_CACHE_PREFIX}{c['cid']}",
                            json.dumps(new_cache, ensure_ascii=False),
                            ex=AVATAR_CACHE_TTL,
                        )
                        need_write = True
                else:
                    # 会话列表无有效昵称，使用缓存昵称
                    if cached_nick:
                        c["otherUserName"] = cached_nick

                # 头像：缓存有头像且会话没有时补填
                if cached_avatar and not c.get("otherUserAvatar"):
                    c["otherUserAvatar"] = cached_avatar

            if need_write:
                await write_pipe.execute()

        except Exception as e:
            logger.warning(f"【{account_id}】Redis批量处理用户信息失败: {e}")

        return ApiResponse(
            success=True,
            data={
                "conversations": conversations,
                "hasMore": body.get("hasMore", False),
                "nextCursor": body.get("nextCursor", None),
            },
        )

    except Exception as e:
        logger.error(f"【{account_id}】获取会话列表失败: {e}")
        return ApiResponse(success=False, message=f"获取会话列表失败: {str(e)}")


@router.get("/messages/{account_id}/{cid}")
async def get_messages(
    account_id: str,
    cid: str,
    cursor: int = None,
    limit: int = 20,
    current_user: User = Depends(get_current_active_user),
):
    """
    获取指定会话的聊天记录

    Args:
        account_id: 账号ID
        cid: 会话ID
        cursor: 分页游标（首页不传，翻页传nextCursor）
        limit: 每页数量，默认20
    """
    try:
        manager = get_im_session_manager()
        client = manager.clients.get(account_id)
        if not client or not client.is_connected:
            return ApiResponse(success=False, message="账号未连接，请先连接")

        body = await client.get_messages(
            cid=cid, start_timestamp=cursor, limit=limit
        )

        # 检测IM错误响应（可能是瞬态问题，返回空数据让轮询重试）
        if isinstance(body, dict) and "reason" in body:
            err_msg = body.get("developerMessage", body.get("reason", ""))
            logger.warning(f"【{account_id}】IM消息列表返回错误: {err_msg}，等待下次轮询重试")
            return ApiResponse(
                success=True,
                data={"messages": [], "hasMore": False, "nextCursor": None},
            )

        # 解析消息列表（IM返回倒序，需反转为正序：最旧在前，最新在后）
        messages = []
        models = body.get("userMessageModels", [])
        for model in models:
            msg_info = _parse_message(model, client.myid)
            if msg_info:
                messages.append(msg_info)
        messages.reverse()

        return ApiResponse(
            success=True,
            data={
                "messages": messages,
                "hasMore": body.get("hasMore", False)
                    if isinstance(body.get("hasMore"), bool)
                    else body.get("hasMore", 0) == 1,
                "nextCursor": body.get("nextCursor", None),
            },
        )

    except Exception as e:
        logger.error(f"【{account_id}】获取聊天记录失败: {e}")
        return ApiResponse(success=False, message=f"获取聊天记录失败: {str(e)}")


# ==================== 发送消息请求模型 ====================


class SendMessageRequest(BaseModel):
    """发送消息请求体"""
    cid: str
    toUserId: str
    text: str


class RecallMessageRequest(BaseModel):
    messageId: str
    messageTime: int


class AvatarQueryItem(BaseModel):
    """单条头像查询项"""
    userId: str
    cid: str


class AvatarQueryRequest(BaseModel):
    """批量查询头像请求体"""
    queries: list[AvatarQueryItem]


@router.post("/send-message/{account_id}")
async def send_message(
    account_id: str,
    req: SendMessageRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    发送文本消息

    Args:
        account_id: 账号ID
        req: 包含 cid（会话ID）、toUserId（对方用户ID）、text（消息内容）
    """
    try:
        manager = get_im_session_manager()
        client = manager.clients.get(account_id)
        if not client or not client.is_connected:
            return ApiResponse(success=False, message="账号未连接，请先连接")

        if not req.text.strip():
            return ApiResponse(success=False, message="消息内容不能为空")

        send_result = await client.send_text_message(
            cid=req.cid,
            to_user_id=req.toUserId,
            text=req.text,
        )
        logger.info(
            f"【{account_id}】发送消息到 {req.toUserId}: {req.text[:50]}"
        )
        return ApiResponse(
            success=True,
            message="发送成功",
            data={"messageId": send_result.get("messageId", "")},
        )

    except Exception as e:
        # send_text_message 在被 IM 安全拦截等业务错误时会抛出明文原因，
        # 直接透传给前端展示（如"内容存在不当信息..."），便于用户调整后重发。
        logger.warning(f"【{account_id}】发送消息失败: {e}")
        return ApiResponse(success=False, message=f"发送失败：{str(e)}")


@router.post("/recall-message/{account_id}")
async def recall_message(
    account_id: str,
    req: RecallMessageRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    if not await _get_owned_chat_account(account_id, current_user, db):
        return ApiResponse(success=False, message="账号不存在或无权操作")
    client = get_im_session_manager().clients.get(account_id)
    if not client or not client.is_connected:
        return ApiResponse(success=False, message="账号未连接")
    if not req.messageId:
        return ApiResponse(success=False, message="缺少消息ID，无法撤回")
    message_time_ms = req.messageTime * 1000 if req.messageTime < 1_000_000_000_000 else req.messageTime
    elapsed_ms = int(time.time() * 1000) - message_time_ms
    if elapsed_ms < -10_000 or elapsed_ms > 120_000:
        return ApiResponse(success=False, message="消息发送超过两分钟，无法撤回")
    try:
        await client.recall_message(req.messageId)
        return ApiResponse(success=True, message="消息已撤回")
    except Exception as e:
        logger.error(f"【{account_id}】撤回消息失败: {e}")
        return ApiResponse(success=False, message=f"撤回失败: {e}")


async def _get_owned_chat_account(account_id: str, current_user: User, db: AsyncSession) -> XYAccount | None:
    query = select(XYAccount).where(XYAccount.account_id == account_id)
    if not is_admin_user(current_user):
        query = query.where(XYAccount.owner_id == current_user.id)
    return (await db.execute(query)).scalar_one_or_none()


@router.get("/official-blacklist/{account_id}/{cid}")
async def query_official_blacklist(
    account_id: str,
    cid: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    account = await _get_owned_chat_account(account_id, current_user, db)
    if not account or not account.cookie:
        return ApiResponse(success=False, message="账号不存在或Cookie为空")
    try:
        data = await official_blacklist_request(account.cookie, cid, "query")
        return ApiResponse(success=True, data={"blocked": bool(data.get("isInBlack"))})
    except Exception as e:
        return ApiResponse(success=False, message=f"查询黑名单状态失败: {e}")


@router.post("/official-blacklist/{account_id}/{cid}/{action}")
async def change_official_blacklist(
    account_id: str,
    cid: str,
    action: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    if action not in {"add", "remove"}:
        return ApiResponse(success=False, message="无效操作")
    account = await _get_owned_chat_account(account_id, current_user, db)
    if not account or not account.cookie:
        return ApiResponse(success=False, message="账号不存在或Cookie为空")
    try:
        await official_blacklist_request(account.cookie, cid, action)
        blocked = action == "add"
        return ApiResponse(
            success=True,
            message="已加入闲鱼官方黑名单" if blocked else "已解除闲鱼官方黑名单",
            data={"blocked": blocked},
        )
    except Exception as e:
        return ApiResponse(success=False, message=f"黑名单操作失败: {e}")


@router.post("/avatars/{account_id}")
async def query_avatars(
    account_id: str,
    req: AvatarQueryRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    批量查询用户头像

    优先从Redis缓存获取，缓存未命中时调用mtop API查询，结果缓存24小时

    Args:
        account_id: 账号ID
        req: 包含 session_ids 列表
    """
    try:
        # 校验账号归属并获取cookie（管理员可操作任意账号）
        query = select(XYAccount).where(XYAccount.account_id == account_id)
        if not is_admin_user(current_user):
            query = query.where(XYAccount.owner_id == current_user.id)
        result = await db.execute(query)
        account = result.scalar_one_or_none()
        if not account or not account.cookie:
            return ApiResponse(success=False, message="账号不存在或Cookie为空")

        user_infos = {}
        for idx, item in enumerate(req.queries):
            # 每次请求间隔 0.3 秒，防止 mtop API 限流
            if idx > 0:
                await asyncio.sleep(0.3)
            info = await get_user_info(
                account_id=account_id,
                cid=item.cid,
                cookies_str=account.cookie,
                db=db,
            )
            if info:
                user_infos[item.userId] = info

        return ApiResponse(success=True, data=user_infos)

    except Exception as e:
        logger.error(f"【{account_id}】批量查询头像失败: {e}")
        return ApiResponse(success=False, message=f"查询头像失败: {str(e)}")


# ==================== 消息解析辅助函数 ====================


@router.get("/account-profile/{account_id}")
async def get_account_profile(
    account_id: str,
    cid: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """查询并持久化卖家在闲鱼的真实昵称"""
    query = select(XYAccount).where(XYAccount.account_id == account_id)
    if not is_admin_user(current_user):
        query = query.where(XYAccount.owner_id == current_user.id)
    account = (await db.execute(query)).scalar_one_or_none()
    if not account or not account.cookie:
        return ApiResponse(success=False, message="账号不存在或Cookie为空")

    info = await get_owner_user_info(account_id, cid, account.cookie, db)
    if info and _is_valid_nick(info.get("nick", "")):
        account.display_name = info["nick"]
        await db.commit()
    return ApiResponse(success=True, data=info or {})


def _parse_conversation(conv: dict, myid: str) -> dict | None:
    """
    解析单个会话数据

    数据结构参照 goofish-client 类型定义：
    userConvs[i] = {
        type: number,
        singleChatUserConversation: {
            singleChatConversation: { cid, pairFirst, pairSecond, extension },
            lastMessage: { message: { content, extension, ... } },
            modifyTime,
            redPoint,
        }
    }

    Args:
        conv: 原始会话数据（已解包 singleChatUserConversation）
        myid: 当前账号的用户ID

    Returns:
        格式化后的会话字典
    """
    try:
        # 获取单聊会话信息
        single_conv = conv.get("singleChatConversation", {})
        cid = single_conv.get("cid", "")
        if not cid:
            return None
        # 去掉 @goofish 后缀
        raw_cid = cid
        if "@goofish" in cid:
            cid = cid.split("@")[0]
        if not cid:
            return None

        # 通过 pairFirst/pairSecond 确定对方用户ID
        # 注意：pairFirst/pairSecond 可能带 @goofish 后缀，需先去掉再比较
        pair_first_raw = single_conv.get("pairFirst", "")
        pair_second_raw = single_conv.get("pairSecond", "")
        pair_first = pair_first_raw.split("@")[0] if "@" in pair_first_raw else pair_first_raw
        pair_second = pair_second_raw.split("@")[0] if "@" in pair_second_raw else pair_second_raw
        other_user_id = pair_second if pair_first == myid else pair_first

        # 过滤无效会话：otherUserId 为空或 "0" 的是系统/通知类会话，不返回给前端
        if not other_user_id or other_user_id == "0":
            return None

        # 从 extension 获取商品信息（可用作显示补充）
        ext = single_conv.get("extension", {})
        if isinstance(ext, str):
            try:
                ext = json.loads(ext)
            except (json.JSONDecodeError, TypeError):
                ext = {}
        item_title = ext.get("itemTitle", "") if isinstance(ext, dict) else ""

        # 最后一条消息
        last_msg_obj = conv.get("lastMessage", {})
        last_message = last_msg_obj.get("message", {}) if last_msg_obj else {}
        last_msg_summary = _extract_message_summary(last_message)
        last_msg_time = conv.get("modifyTime", 0)

        # 未读数（redPoint）
        unread_count = conv.get("redPoint", 0)

        # 从最后一条消息的 extension 中提取对方名称
        # reminderTitle 是最后一条消息的发送者名称，需要判断是否为对方
        last_ext = last_message.get("extension", {})
        if isinstance(last_ext, str):
            try:
                last_ext = json.loads(last_ext)
            except (json.JSONDecodeError, TypeError):
                last_ext = {}
        sender_user_id_raw = last_ext.get("senderUserId", "") if isinstance(last_ext, dict) else ""
        sender_user_id = str(sender_user_id_raw).split("@")[0] if "@" in str(sender_user_id_raw) else str(sender_user_id_raw)
        reminder_title = last_ext.get("reminderTitle", "") if isinstance(last_ext, dict) else ""
        # 只有当最后一条消息的发送者是对方时，reminderTitle 才是对方名称
        # 用 other_user_id 比较比 myid 更可靠（避免格式不一致）
        # 昵称必须是有效的（非空、非纯数字），否则视为未获取到
        if sender_user_id and sender_user_id == other_user_id and _is_valid_nick(reminder_title):
            other_user_name = reminder_title
        else:
            other_user_name = ""

        return {
            "cid": cid,
            "rawCid": raw_cid,
            "otherUserId": other_user_id,
            "otherUserName": other_user_name,
            "otherUserAvatar": "",
            "itemTitle": item_title,
            "lastMessageSummary": last_msg_summary,
            "lastMessageTime": last_msg_time,
            "unreadCount": unread_count,
        }
    except Exception as e:
        logger.warning(f"解析会话数据失败: {e}")
        return None


def _parse_message(model: dict, myid: str) -> dict | None:
    """
    解析单条消息

    参照 XianYuApis-master/goofish_live.py 的解析逻辑：
    - send_user_name = user_message["message"]["extension"]["reminderTitle"]
    - send_user_id   = user_message["message"]["extension"]["senderUserId"]
    - base64解码 user_message["message"]["content"]["custom"]["data"]
    - 解码后格式：
      文本: {"contentType": 1, "text": {"text": "实际消息"}}
      图片: {"contentType": 2, "image": {"pics": [{"url":"...", "width":0, "height":0}]}}

    Args:
        model: userMessageModels 中的单条数据
        myid: 当前账号的用户ID

    Returns:
        格式化后的消息字典
    """
    try:
        message = model.get("message", {})
        extension = message.get("extension", {})
        if isinstance(extension, str):
            try:
                extension = json.loads(extension)
            except (json.JSONDecodeError, TypeError):
                extension = {}

        sender_id_raw = str(extension.get("senderUserId", "") or "") if isinstance(extension, dict) else ""
        # 去掉 @goofish 后缀，保证与 myid 比较和前端显示一致
        sender_id = sender_id_raw.split("@")[0] if "@" in sender_id_raw else sender_id_raw
        sender_name = str(extension.get("reminderTitle", "") or "") if isinstance(extension, dict) else ""
        is_self = sender_id == myid

        # 解析消息内容
        content = message.get("content", {})
        custom = content.get("custom", {})
        custom_data = custom.get("data", "")

        msg_type = "text"
        msg_text = ""
        msg_images = []

        if custom_data:
            try:
                decoded = json.loads(
                    base64.b64decode(custom_data).decode("utf-8")
                )
                content_type = decoded.get("contentType", 0)

                if content_type == 1 and "text" in decoded:
                    # 文本消息: {"contentType":1, "text":{"text":"实际消息"}}
                    msg_type = "text"
                    text_obj = decoded["text"]
                    if isinstance(text_obj, dict):
                        msg_text = text_obj.get("text", "")
                    else:
                        msg_text = str(text_obj)

                elif content_type == 2 and "image" in decoded:
                    # 图片消息: {"contentType":2, "image":{"pics":[{"url":"..."}]}}
                    msg_type = "image"
                    pics = decoded.get("image", {}).get("pics", [])
                    msg_images = [
                        pic.get("url", "") for pic in pics if pic.get("url")
                    ]
                    if not msg_images:
                        msg_text = "[图片]"

                elif content_type == 3 and "audio" in decoded:
                    # 语音消息
                    msg_type = "text"
                    msg_text = "[语音消息]"

                elif "text" in decoded:
                    # 兼容: text 可能是字符串或对象
                    msg_type = "text"
                    text_obj = decoded["text"]
                    if isinstance(text_obj, dict):
                        msg_text = text_obj.get("text", str(text_obj))
                    else:
                        msg_text = str(text_obj)

                elif "picUrl" in decoded:
                    # 兼容旧格式图片
                    msg_type = "image"
                    msg_images = [decoded["picUrl"]]

                elif "title" in decoded or "template" in decoded:
                    # 卡片/系统消息
                    msg_type = "card"
                    msg_text = str(
                        decoded.get("title", decoded.get("template", "[卡片消息]"))
                    )

                else:
                    # 未知类型，用 summary 降级
                    msg_type = "text"
                    summary = custom.get("summary", "")
                    msg_text = str(summary) if summary else f"[未知消息类型:{content_type}]"

            except Exception:
                # base64解码或JSON解析失败，用 summary 降级
                summary = custom.get("summary", "")
                msg_text = str(summary) if summary else "[无法解析的消息]"
        else:
            # 没有 custom.data，用 summary 降级
            summary = custom.get("summary", "")
            msg_text = str(summary) if summary else "[系统消息]"

        # 消息时间戳（goofish IM 中字段名为 createAt）
        msg_time = message.get("createAt", 0) or message.get("time", 0)

        return {
            "messageId": str(message.get("messageId", "") or ""),
            "senderId": sender_id,
            "senderName": sender_name,
            "isSelf": is_self,
            "type": msg_type,
            "text": msg_text,
            "images": msg_images,
            "time": msg_time,
        }
    except Exception as e:
        logger.warning(f"解析消息失败: {e}")
        return None


def _extract_message_summary(message: dict) -> str:
    """
    从 lastMessage.message 提取摘要文本

    数据结构：message.content.custom.summary / message.content.custom.data (base64)
    """
    try:
        content = message.get("content", {})
        custom = content.get("custom", {})

        # 优先使用 summary 字段
        summary = custom.get("summary", "")
        if summary:
            return summary[:50]

        # 尝试解码 data (base64)
        custom_data = custom.get("data", "")
        if custom_data:
            try:
                decoded = json.loads(
                    base64.b64decode(custom_data).decode("utf-8")
                )
                if "text" in decoded:
                    text_obj = decoded["text"]
                    # text 可能是 dict（如 {"text": "实际内容"}）或字符串
                    if isinstance(text_obj, dict):
                        text = text_obj.get("text", "")
                    else:
                        text = str(text_obj)
                    return text[:50] if text else ""
                if "picUrl" in decoded:
                    return "[图片]"
                if "title" in decoded:
                    return decoded["title"][:50]
            except Exception:
                pass

        # 降级使用 degrade 字段
        degrade = custom.get("degrade", "")
        if degrade:
            return degrade[:50]
    except Exception:
        pass
    return ""
