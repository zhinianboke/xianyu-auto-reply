"""
推广返佣系统 - 系统设置API路由

功能：
1. 提供公开的主题设置接口（无需认证）
2. 从共享的xy_system_settings表读取主题颜色和字体配置
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from common.models.system_setting import SystemSetting

router = APIRouter(tags=["系统设置"])

# 允许公开访问的主题相关设置key
THEME_SETTING_KEYS = [
    "theme.effect",
    "theme.color_preset",
    "theme.font_family",
]

# 允许公开访问的所有公共设置key（含验证码开关等）
PUBLIC_SETTING_KEYS = THEME_SETTING_KEYS + [
    "login_captcha_enabled",
]


@router.get("/theme")
async def get_theme_settings(
    session: AsyncSession = Depends(deps.get_db_session),
):
    """
    获取主题设置（公开接口，无需登录）

    从共享的xy_system_settings表中读取主题相关的配置参数，
    返回主题颜色预设、主题效果和字体设置
    """
    try:
        query = select(SystemSetting).where(
            SystemSetting.key.in_(THEME_SETTING_KEYS)
        )
        result = await session.execute(query)
        rows = result.scalars().all()

        settings = {}
        for row in rows:
            settings[row.key] = row.value

        return {
            "success": True,
            "data": settings,
        }
    except Exception as e:
        # 主题设置获取失败不应影响页面加载，返回空数据让前端使用默认值
        return {
            "success": True,
            "data": {},
            "message": f"主题设置读取异常: {str(e)}",
        }


@router.get("/public")
async def get_public_settings(
    session: AsyncSession = Depends(deps.get_db_session),
):
    """
    获取公共系统设置（公开接口，无需登录）

    返回登录验证码开关等公共配置
    """
    try:
        query = select(SystemSetting).where(
            SystemSetting.key.in_(PUBLIC_SETTING_KEYS)
        )
        result = await session.execute(query)
        rows = result.scalars().all()

        settings = {}
        for row in rows:
            settings[row.key] = row.value

        return {
            "success": True,
            "data": settings,
        }
    except Exception as e:
        return {
            "success": True,
            "data": {},
            "message": f"公共设置读取异常: {str(e)}",
        }
