"""
推广返佣系统 - 账号管理API路由

功能：
1. 账号列表查询（后端分页）
2. 通过Cookies新增账号（支持账号类型：淘宝/京东/美团）
3. 账号启用/禁用
4. 账号备注修改
5. 更新Cookies
"""
from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from common.models.user import User, UserRole
from common.models.fy_account import FYAccount, FYAccountType
from common.utils.time_utils import get_beijing_now

router = APIRouter(tags=["账号管理"])

# 账号类型中文映射
ACCOUNT_TYPE_LABELS = {
    FYAccountType.TAOBAO: "淘宝",
    FYAccountType.JD: "京东",
    FYAccountType.MEITUAN: "美团",
}


@router.get("/list")
async def list_accounts(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=10, le=100, description="每页条数"),
    keyword: str = Query(default="", description="搜索关键词（账号ID/备注）"),
    account_type: str = Query(default="", description="账号类型筛选"),
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """
    查询账号列表（后端分页）

    管理员可查看所有账号，普通用户只能查看自己的
    """
    base_query = select(FYAccount)

    # 权限过滤
    if current_user.role != UserRole.ADMIN:
        base_query = base_query.where(FYAccount.owner_id == current_user.id)

    # 账号类型筛选
    if account_type.strip():
        try:
            at = FYAccountType(account_type.strip())
            base_query = base_query.where(FYAccount.account_type == at)
        except ValueError:
            pass

    # 关键词搜索
    if keyword.strip():
        search_pattern = f"%{keyword.strip()}%"
        base_query = base_query.where(
            (FYAccount.account_id.like(search_pattern)) |
            (FYAccount.remark.like(search_pattern))
        )

    # 查询总数
    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # 分页查询
    offset = (page - 1) * page_size
    data_query = base_query.order_by(FYAccount.created_at.desc()).offset(offset).limit(page_size)
    result = await session.execute(data_query)
    accounts = result.scalars().all()

    # 构建返回数据
    items = []
    for account in accounts:
        items.append({
            "id": account.id,
            "account_id": account.account_id,
            "account_type": account.account_type.value if account.account_type else FYAccountType.TAOBAO.value,
            "account_type_label": ACCOUNT_TYPE_LABELS.get(account.account_type, "淘宝"),
            "display_name": account.display_name or "",
            "owner_id": account.owner_id,
            "enabled": account.enabled,
            "remark": account.remark or "",
            "app_key": account.app_key or "",
            "app_secret_masked": _mask_secret(account.app_secret) if account.app_secret else "",
            "adzone_id": account.adzone_id or "",
            "created_at": account.created_at.strftime("%Y-%m-%d %H:%M:%S") if account.created_at else "",
            "updated_at": account.updated_at.strftime("%Y-%m-%d %H:%M:%S") if account.updated_at else "",
        })

    return {
        "success": True,
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


@router.post("/add")
async def add_account(
    payload: dict,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """
    新增账号

    淘宝类型：填写AppKey + AppSecret（调用淘宝开放平台API）
    其他类型：填写Cookies
    """
    remark = (payload.get("remark") or "").strip()
    account_type_str = (payload.get("account_type") or FYAccountType.TAOBAO.value).strip()

    # 解析账号类型
    try:
        account_type = FYAccountType(account_type_str)
    except ValueError:
        return {"success": False, "message": f"不支持的账号类型: {account_type_str}"}

    # 根据账号类型校验必填字段
    if account_type == FYAccountType.TAOBAO:
        app_key = (payload.get("app_key") or "").strip()
        app_secret = (payload.get("app_secret") or "").strip()
        adzone_id_raw = (payload.get("adzone_id") or "").strip()
        if not app_key or not app_secret:
            return {"success": False, "message": "淘宝类型账号请填写AppKey和AppSecret"}
        if not adzone_id_raw:
            return {"success": False, "message": "淘宝类型账号请填写推广位ID"}
        account_id = f"taobao_{app_key}"
        cookies_str = ""
    else:
        cookies_str = (payload.get("cookies") or "").strip()
        if not cookies_str:
            return {"success": False, "message": "请输入Cookies"}
        account_id = _extract_account_id(cookies_str)
        app_key = ""
        app_secret = ""

    # 检查账号是否已存在
    existing = await session.execute(
        select(FYAccount).where(FYAccount.account_id == account_id)
    )
    if existing.scalar_one_or_none():
        return {"success": False, "message": f"账号 {account_id} 已存在"}

    # 创建账号
    now = get_beijing_now()
    new_account = FYAccount(
        account_id=account_id,
        account_type=account_type,
        owner_id=current_user.id,
        cookie=cookies_str,
        app_key=app_key or None,
        app_secret=app_secret or None,
        adzone_id=adzone_id_raw if account_type == FYAccountType.TAOBAO else None,
        enabled=True,
        remark=remark,
        created_at=now,
        updated_at=now,
    )
    session.add(new_account)
    await session.commit()

    return {
        "success": True,
        "message": f"账号 {account_id} 添加成功",
        "data": {"id": new_account.id, "account_id": account_id},
    }


@router.put("/update")
async def update_account(
    payload: dict,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """
    统一修改账号信息

    淘宝类型：可修改AppKey/AppSecret/推广位ID/备注
    其他类型：可修改Cookies/备注
    """
    account_pk = payload.get("id")
    if not account_pk:
        return {"success": False, "message": "请提供账号ID"}

    account = await _get_account_with_permission(session, account_pk, current_user)
    if isinstance(account, dict):
        return account

    # 根据账号类型更新对应字段
    if account.account_type == FYAccountType.TAOBAO:
        app_key = payload.get("app_key")
        app_secret = payload.get("app_secret")
        adzone_id = payload.get("adzone_id")
        if app_key is not None:
            account.app_key = app_key.strip() or account.app_key
        if app_secret is not None:
            account.app_secret = app_secret.strip() or account.app_secret
        if adzone_id is not None:
            account.adzone_id = adzone_id.strip() or account.adzone_id
    else:
        cookies_str = payload.get("cookies")
        if cookies_str is not None:
            account.cookie = cookies_str.strip()

    remark = payload.get("remark")
    if remark is not None:
        account.remark = remark.strip()

    account.updated_at = get_beijing_now()
    await session.commit()

    return {"success": True, "message": "账号信息更新成功"}


@router.put("/update-cookies")
async def update_cookies(
    payload: dict,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """更新账号Cookies（兼容旧接口）"""
    account_pk = payload.get("id")
    cookies_str = (payload.get("cookies") or "").strip()

    if not account_pk or not cookies_str:
        return {"success": False, "message": "参数不完整"}

    account = await _get_account_with_permission(session, account_pk, current_user)
    if isinstance(account, dict):
        return account

    account.cookie = cookies_str
    account.updated_at = get_beijing_now()
    await session.commit()

    return {"success": True, "message": "Cookies更新成功"}


@router.put("/toggle-status")
async def toggle_account_status(
    payload: dict,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """启用/禁用账号"""
    account_pk = payload.get("id")
    enabled = payload.get("enabled", True)

    if not account_pk:
        return {"success": False, "message": "请提供账号ID"}

    account = await _get_account_with_permission(session, account_pk, current_user)
    if isinstance(account, dict):
        return account

    account.enabled = bool(enabled)
    account.updated_at = get_beijing_now()
    await session.commit()

    status_text = "启用" if enabled else "禁用"
    return {"success": True, "message": f"账号已{status_text}"}


@router.put("/update-remark")
async def update_remark(
    payload: dict,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """更新账号备注"""
    account_pk = payload.get("id")
    remark = (payload.get("remark") or "").strip()

    if not account_pk:
        return {"success": False, "message": "请提供账号ID"}

    account = await _get_account_with_permission(session, account_pk, current_user)
    if isinstance(account, dict):
        return account

    account.remark = remark
    account.updated_at = get_beijing_now()
    await session.commit()

    return {"success": True, "message": "备注更新成功"}


def _mask_secret(secret: str) -> str:
    """对密钥做掩码处理，只显示前4后4位"""
    if not secret or len(secret) <= 8:
        return "****"
    return f"{secret[:4]}{'*' * (len(secret) - 8)}{secret[-4:]}"


def _extract_account_id(cookies_str: str) -> str:
    """从cookies中提取账号ID，提取失败则用MD5哈希"""
    try:
        for part in cookies_str.split(";"):
            part = part.strip()
            if part.startswith("munb="):
                val = part.split("=", 1)[1].strip()
                if val:
                    return val
    except Exception:
        pass
    return hashlib.md5(cookies_str[:100].encode()).hexdigest()[:16]


async def _get_account_with_permission(session: AsyncSession, account_pk: int, current_user: User):
    """根据主键获取账号并检查权限，返回账号对象或错误dict"""
    result = await session.execute(
        select(FYAccount).where(FYAccount.id == int(account_pk))
    )
    account = result.scalar_one_or_none()
    if not account:
        return {"success": False, "message": "账号不存在"}
    if current_user.role != UserRole.ADMIN and account.owner_id != current_user.id:
        return {"success": False, "message": "无权操作此账号"}
    return account
