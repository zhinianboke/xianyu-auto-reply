"""
消息发送路由
外部系统发送消息和闲鱼回复匹配接口
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.api import deps
from common.models.user import User
from app.services.keyword_service import KeywordService
from app.services.default_reply_service import DefaultReplyService

router = APIRouter(tags=["消息"])


# ==================== 请求/响应模型 ====================

class SendMessageRequest(BaseModel):
    """发送消息请求"""
    api_key: str
    cookie_id: str
    chat_id: str
    to_user_id: str
    message: str


class SendMessageResponse(BaseModel):
    """发送消息响应"""
    success: bool
    message: str


class XianyuReplyRequest(BaseModel):
    """闲鱼回复请求"""
    cookie_id: str
    msg_time: str
    user_url: str
    send_user_id: str
    send_user_name: str
    item_id: str
    send_message: str
    chat_id: str


class XianyuReplyResponse(BaseModel):
    """闲鱼回复响应"""
    code: int
    data: dict


# ==================== 工具函数 ====================

# API秘钥（从配置读取）
def get_api_secret_key() -> str:
    """获取API密钥"""
    from app.core.config import get_settings
    settings = get_settings()
    # 优先从环境变量读取，否则使用默认值
    return getattr(settings, 'api_secret_key', 'xianyu_api_secret_2024')


def verify_api_key(api_key: str) -> bool:
    """验证API秘钥"""
    return api_key == get_api_secret_key()


def clean_param(param_str: str) -> str:
    """清理参数中的换行符"""
    if isinstance(param_str, str):
        return param_str.replace("\\n", "").replace("\n", "")
    return param_str


# ==================== 路由 ====================

@router.post("/send", response_model=SendMessageResponse)
async def send_message(request: SendMessageRequest):
    """
    发送消息API接口（使用秘钥验证）
    
    用于外部系统（如QQ机器人）向闲鱼发送消息
    """
    try:
        # 清理参数
        cleaned_api_key = clean_param(request.api_key)
        cleaned_cookie_id = clean_param(request.cookie_id)
        cleaned_chat_id = clean_param(request.chat_id)
        cleaned_to_user_id = clean_param(request.to_user_id)
        cleaned_message = clean_param(request.message)
        
        # 验证API秘钥
        if not cleaned_api_key:
            logger.warning("API秘钥为空")
            return SendMessageResponse(
                success=False,
                message="API秘钥不能为空"
            )
        
        # 特殊测试秘钥
        if cleaned_api_key == "zhinina_test_key":
            logger.info("使用测试秘钥，直接返回成功")
            return SendMessageResponse(
                success=True,
                message="接口验证成功"
            )
        
        # 验证秘钥
        if not verify_api_key(cleaned_api_key):
            logger.warning(f"API秘钥验证失败: {cleaned_api_key}")
            return SendMessageResponse(
                success=False,
                message="API秘钥验证失败"
            )
        
        # 验证必需参数
        required_params = {
            "cookie_id": cleaned_cookie_id,
            "chat_id": cleaned_chat_id,
            "to_user_id": cleaned_to_user_id,
            "message": cleaned_message,
        }
        
        for param_name, param_value in required_params.items():
            if not param_value:
                logger.warning(f"必需参数 {param_name} 为空")
                return SendMessageResponse(
                    success=False,
                    message=f"参数 {param_name} 不能为空"
                )
        
        # 通过WebSocket服务发送消息
        from app.services.websocket_client import websocket_client
        
        result = await websocket_client.send_message(
            account_id=cleaned_cookie_id,
            chat_id=cleaned_chat_id,
            content=cleaned_message,
            message_type="text"
        )
        
        if result.get('success'):
            logger.info(f"消息发送成功: {cleaned_cookie_id} -> {cleaned_to_user_id}")
            return SendMessageResponse(
                success=True,
                message="消息发送成功"
            )
        else:
            error_msg = result.get('message', '发送失败')
            logger.error(f"发送消息失败: {error_msg}")
            return SendMessageResponse(
                success=False,
                message=error_msg
            )
        
    except Exception as e:
        logger.error(f"发送消息异常: {e}")
        return SendMessageResponse(
            success=False,
            message=f"发送消息失败: {str(e)}"
        )


@router.post("/xianyu-reply", response_model=XianyuReplyResponse)
async def xianyu_reply(
    request: XianyuReplyRequest,
    session: AsyncSession = Depends(deps.get_db_session),
):
    """
    闲鱼回复匹配接口
    
    根据消息内容匹配关键词回复或默认回复
    """
    try:
        from app.services.account_service import AccountService
        
        account_service = AccountService(session)
        keyword_service = KeywordService(session)
        default_reply_service = DefaultReplyService(session)
        
        # 获取账号（不验证用户，因为这是内部调用）
        # 这里简化处理，实际应该通过account_id查找
        
        # 1. 尝试匹配关键词
        msg_template = None
        is_default_reply = False
        
        # 获取账号的所有关键词规则
        from common.db.compat import db_manager
        keywords = db_manager.get_keywords_with_type(request.cookie_id)
        
        # 遍历关键词进行匹配
        for keyword_rule in keywords:
            keyword = keyword_rule.get('keyword', '')
            if keyword and keyword in request.message:
                # 匹配成功
                msg_template = keyword_rule.get('reply', '')
                logger.info(f"【消息发送】匹配到关键词: {keyword}")
                break
        
        # 2. 如果没有匹配到关键词，尝试默认回复
        if not msg_template:
            default_settings = await default_reply_service.get_default_reply(request.cookie_id)
            
            if default_settings and default_settings.get("enabled", False):
                # 检查是否开启了"只回复一次"
                if default_settings.get("reply_once", False):
                    # 检查是否已经回复过
                    has_replied = await default_reply_service.check_user_replied(
                        request.cookie_id, request.chat_id
                    )
                    if has_replied:
                        return XianyuReplyResponse(
                            code=404,
                            data={"error": "该对话已使用默认回复，不再重复回复"}
                        )
                
                msg_template = default_settings.get("reply_content", "")
                is_default_reply = True
        
        # 3. 如果都没有匹配到
        if not msg_template:
            return XianyuReplyResponse(
                code=404,
                data={"error": "未找到匹配的回复规则且未设置默认回复"}
            )
        
        # 4. 格式化回复内容
        try:
            send_msg = msg_template.format(
                send_user_id=request.send_user_id,
                send_user_name=request.send_user_name,
                send_message=request.send_message,
            )
        except Exception:
            send_msg = msg_template
        
        # 5. 如果是默认回复且开启了"只回复一次"，记录回复
        if is_default_reply:
            default_settings = await default_reply_service.get_default_reply(request.cookie_id)
            if default_settings and default_settings.get("reply_once", False):
                await default_reply_service.record_user_replied(
                    request.cookie_id, request.chat_id
                )
        
        return XianyuReplyResponse(
            code=200,
            data={"send_msg": send_msg}
        )
        
    except Exception as e:
        logger.error(f"闲鱼回复匹配异常: {e}")
        return XianyuReplyResponse(
            code=500,
            data={"error": str(e)}
        )
