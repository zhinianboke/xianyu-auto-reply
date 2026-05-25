"""
推广返佣系统 - API路由注册

所有前端API接口的路由定义与挂载，
由 __init__.py 通过 from ._exports import * 重新导出。
"""
from __future__ import annotations

from fastapi import APIRouter

from .routes import auth, cookies, dashboard, delete_rule, geetest, health, material, product_rule, publish_rule, settings, taobao_alliance

# 创建API路由器
api_router = APIRouter()

# 健康检查
api_router.include_router(health.router, tags=["健康检查"])

# 认证相关
api_router.include_router(auth.router, prefix="/auth", tags=["认证"])

# 账号管理
api_router.include_router(cookies.router, prefix="/cookies", tags=["账号管理"])

# 仪表盘
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["仪表盘"])

# 系统设置（含公开主题接口）
api_router.include_router(settings.router, prefix="/settings", tags=["系统设置"])

# 极验验证码
api_router.include_router(geetest.router, prefix="/geetest", tags=["极验验证码"])

# 淘宝联盟
api_router.include_router(taobao_alliance.router, prefix="/taobao-alliance", tags=["淘宝联盟"])

# 选品规则
api_router.include_router(product_rule.router, prefix="/product-rule", tags=["选品规则"])

# 素材库
api_router.include_router(material.router, prefix="/material", tags=["素材库"])

# 发布规则
api_router.include_router(publish_rule.router, prefix="/publish-rule", tags=["发布规则"])

# 删除规则
api_router.include_router(delete_rule.router, prefix="/delete-rule", tags=["删除规则"])

__all__ = ["api_router"]
