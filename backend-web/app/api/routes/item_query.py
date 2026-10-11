"""
商品通用查询 - 管理配置接口 + 公开执行接口

功能：
1. 管理端（需登录，挂在 /items 下，与 ai-prompt 端点同风格）：
   - GET /items/{cookie_id}/{item_id}/query-buttons ：读取商品查询按钮配置
   - PUT /items/{cookie_id}/{item_id}/query-buttons ：整体覆盖保存（含字段校验）
   - GET /items/{cookie_id}/{item_id}/display-links ：读取商品展示入口配置（提货页链接/弹窗按钮）
   - PUT /items/{cookie_id}/{item_id}/display-links ：整体覆盖保存（含字段校验）
   - POST /items/{cookie_id}/{item_id}/display-links/upload-image ：上传展示入口图片，返回静态资源 URL
2. 公开端（无需登录）：
   - GET  /item-query/buttons?order_no= ：按订单号返回买家可见按钮名列表
   - POST /item-query/execute           ：执行查询按钮（订单卡密逐行并发 / 手动 Cookie 单次）

安全：
- 公开接口只返回按钮名与执行结果，绝不回传配置中的 URL/headers，日志不打印 Cookie/卡密
- 配置存储在 xy_catalog_items.metadata_json.query_buttons / display_links，不涉及表结构变更
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.api import deps
from app.core.paths import STATIC_ROOT
from app.services.account_service import AccountService
from app.services.display_link_service import validate_display_links as _validate_display_links
from app.services.item_query_service import ItemQueryService
from common.models.user import User
from common.models.xy_catalog_item import XYCatalogItem
from common.schemas.common import ApiResponse
from common.services.query_template import template_url_has_variable_host
from common.utils.auth_scope import resolve_owner_scope
from common.utils.local_image_upload import ImageUploadError, save_uploaded_image

# 管理端：注册时挂 prefix="/items"，路径与 ai-prompt 端点保持同风格
admin_router = APIRouter(tags=["商品查询配置"])
# 公开端：注册时挂 prefix="/item-query"
public_router = APIRouter(tags=["商品通用查询"])


class QueryButtonsSaveRequest(BaseModel):
    """查询按钮配置保存请求（整体覆盖）"""

    buttons: List[dict]
    # 查询页顶部提示文案，空串表示不显示；与 buttons 一起写入 metadata_json
    page_hint: Optional[str] = None


class DisplayLinksSaveRequest(BaseModel):
    """商品展示入口配置保存请求（整体覆盖）"""

    links: List[dict]


class ItemQueryExecuteRequest(BaseModel):
    """公开执行请求：order_no 定位商品配置与发货内容；cookie_override 非空时手动 Cookie 单次执行"""

    order_no: Optional[str] = None
    button_index: int = 0
    cookie_override: Optional[str] = None


def _validate_buttons(buttons: List[dict]) -> tuple[bool, str, List[dict]]:
    """校验并规范化查询按钮配置。

    校验规则（契约）：name/url/result_fields 必填、method 仅 GET/POST、
    url 必须以 http:// 或 https:// 开头、result_fields 每项 path 必填。

    Returns:
        (ok, message, normalized_buttons)；失败时 normalized_buttons 为空列表。
    """
    normalized: List[dict] = []
    for index, button in enumerate(buttons, start=1):
        if not isinstance(button, dict):
            return False, f"第 {index} 个按钮配置格式不正确", []

        name = str(button.get("name") or "").strip()
        if not name:
            return False, f"第 {index} 个按钮缺少名称", []

        url = str(button.get("url") or "").strip()
        if not url:
            return False, f"第 {index} 个按钮缺少请求地址", []
        if not (url.startswith("http://") or url.startswith("https://")):
            return False, f"第 {index} 个按钮的请求地址必须以 http:// 或 https:// 开头", []
        # SSRF 防护：URL 的 host 段不允许出现变量占位符（变量只允许在 path/query/headers/body）
        if template_url_has_variable_host(url):
            return False, f"第 {index} 个按钮的请求地址域名部分不允许使用变量", []

        method = str(button.get("method") or "GET").upper()
        if method not in ("GET", "POST"):
            return False, f"第 {index} 个按钮的请求方法仅支持 GET/POST", []

        headers = button.get("headers")
        if headers is not None and not isinstance(headers, dict):
            return False, f"第 {index} 个按钮的请求头格式不正确", []

        body = button.get("body")
        if body is not None and not isinstance(body, str):
            return False, f"第 {index} 个按钮的请求体格式不正确", []

        result_fields = button.get("result_fields")
        if not isinstance(result_fields, list) or not result_fields:
            return False, f"第 {index} 个按钮缺少结果字段配置", []
        for field_index, field in enumerate(result_fields, start=1):
            if not isinstance(field, dict) or not str(field.get("path") or "").strip():
                return False, f"第 {index} 个按钮的第 {field_index} 个结果字段缺少取值路径", []

        normalized.append({**button, "name": name, "url": url, "method": method})
    return True, "", normalized


async def _load_catalog_item(
    session: AsyncSession, owner_id: int, item_id: str
) -> XYCatalogItem | None:
    """按所属用户 + 商品ID 查询商品目录行。"""
    result = await session.execute(
        select(XYCatalogItem).where(
            XYCatalogItem.owner_id == owner_id,
            XYCatalogItem.item_id == item_id,
        )
    )
    return result.scalars().first()


# ==================== 管理端：查询按钮配置 ====================


@admin_router.get("/{cookie_id}/{item_id}/query-buttons")
async def get_item_query_buttons(
    cookie_id: str,
    item_id: str,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    session: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    """获取商品查询按钮配置"""
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)

    account = await account_service.get_account_for_user(owner_id, cookie_id)
    if not account:
        return ApiResponse(success=False, message="账号不存在")

    try:
        # 注意：管理员 resolve_owner_scope 返回 owner_id=None，不能用作查询条件；
        # 商品归属以上一步解析出的 account.owner_id 为准（账号已按管理员/普通用户做过权限过滤）
        item = await _load_catalog_item(session, account.owner_id, item_id)
        if not item:
            return ApiResponse(success=False, message="商品不存在")

        buttons = (item.metadata_json or {}).get("query_buttons")
        return ApiResponse(
            success=True,
            message="获取成功",
            data={
                "item_id": item_id,
                "buttons": buttons if isinstance(buttons, list) else [],
                "page_hint": (item.metadata_json or {}).get("page_hint") or "",
            },
        )
    except Exception as e:
        logger.error(f"获取商品查询按钮配置失败: {e}")
        return ApiResponse(success=False, message=f"获取失败: {str(e)}")


@admin_router.put("/{cookie_id}/{item_id}/query-buttons", response_model=ApiResponse)
async def save_item_query_buttons(
    cookie_id: str,
    item_id: str,
    payload: QueryButtonsSaveRequest,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    session: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    """保存商品查询按钮配置（整体覆盖）"""
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)

    account = await account_service.get_account_for_user(owner_id, cookie_id)
    if not account:
        return ApiResponse(success=False, message="账号不存在")

    valid, message, buttons = _validate_buttons(payload.buttons)
    if not valid:
        return ApiResponse(success=False, message=message)

    try:
        item = await _load_catalog_item(session, account.owner_id, item_id)
        if not item:
            return ApiResponse(success=False, message="商品不存在")

        metadata = dict(item.metadata_json or {})
        metadata["query_buttons"] = buttons
        metadata["page_hint"] = payload.page_hint
        item.metadata_json = metadata
        # JSON 列原地修改需显式标记，否则 SQLAlchemy 不会感知变更
        flag_modified(item, "metadata_json")
        await session.commit()
        return ApiResponse(success=True, message="商品查询配置已保存")
    except Exception as e:
        logger.error(f"保存商品查询按钮配置失败: {e}")
        return ApiResponse(success=False, message=f"保存失败: {str(e)}")


# ==================== 管理端：展示入口配置（买家提货页链接/弹窗按钮） ====================


@admin_router.get("/{cookie_id}/{item_id}/display-links")
async def get_item_display_links(
    cookie_id: str,
    item_id: str,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    session: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    """获取商品展示入口配置"""
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)

    account = await account_service.get_account_for_user(owner_id, cookie_id)
    if not account:
        return ApiResponse(success=False, message="账号不存在")

    try:
        # 同 query-buttons：管理员 resolve_owner_scope 返回 None，商品归属以 account.owner_id 为准
        item = await _load_catalog_item(session, account.owner_id, item_id)
        if not item:
            return ApiResponse(success=False, message="商品不存在")

        links = (item.metadata_json or {}).get("display_links")
        return ApiResponse(
            success=True,
            message="获取成功",
            data={"links": links if isinstance(links, list) else []},
        )
    except Exception as e:
        logger.error(f"获取商品展示入口配置失败: {e}")
        return ApiResponse(success=False, message=f"获取失败: {str(e)}")


@admin_router.put("/{cookie_id}/{item_id}/display-links", response_model=ApiResponse)
async def save_item_display_links(
    cookie_id: str,
    item_id: str,
    payload: DisplayLinksSaveRequest,
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    session: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    """保存商品展示入口配置（整体覆盖）"""
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)

    account = await account_service.get_account_for_user(owner_id, cookie_id)
    if not account:
        return ApiResponse(success=False, message="账号不存在")

    valid, message, links = _validate_display_links(payload.links)
    if not valid:
        return ApiResponse(success=False, message=message)

    try:
        item = await _load_catalog_item(session, account.owner_id, item_id)
        if not item:
            return ApiResponse(success=False, message="商品不存在")

        metadata = dict(item.metadata_json or {})
        metadata["display_links"] = links
        item.metadata_json = metadata
        # JSON 列原地修改需显式标记，否则 SQLAlchemy 不会感知变更
        flag_modified(item, "metadata_json")
        await session.commit()
        return ApiResponse(success=True, message="商品展示入口配置已保存")
    except Exception as e:
        logger.error(f"保存商品展示入口配置失败: {e}")
        return ApiResponse(success=False, message=f"保存失败: {str(e)}")


# 展示入口图片存储目录（与通用模板共用，URL 可互换使用）
DISPLAY_LINK_UPLOAD_DIR = STATIC_ROOT / "uploads" / "display_links"


@admin_router.post("/{cookie_id}/{item_id}/display-links/upload-image")
async def upload_item_display_link_image(
    cookie_id: str,
    item_id: str,
    image: UploadFile = File(...),
    current_user: User = Depends(deps.get_current_active_user),
    account_service: AccountService = Depends(deps.get_account_service),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """上传商品展示入口图片，返回可访问的静态资源 URL"""
    # 管理员可以操作所有账号，普通用户只能操作自己的账号
    owner_id, _ = resolve_owner_scope(current_user)

    account = await account_service.get_account_for_user(owner_id, cookie_id)
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")

    # 同 display-links 配置端点：管理员 resolve_owner_scope 返回 None，商品归属以 account.owner_id 为准
    item = await _load_catalog_item(session, account.owner_id, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="商品不存在")

    try:
        _, filename, _ = await save_uploaded_image(
            image,
            DISPLAY_LINK_UPLOAD_DIR,
            filename_prefix=item_id,
            short_uuid=True,
        )
    except ImageUploadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return {"success": True, "image_url": f"/static/uploads/display_links/{filename}"}


# ==================== 公开端：按钮列表与执行 ====================


@public_router.get("/buttons", response_model=ApiResponse)
async def get_query_buttons(
    order_no: str = Query(default="", description="闲鱼订单号"),
    session: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    """按订单号返回买家可见的查询按钮列表（只含按钮名，不含 URL/headers）。"""
    success, message, data = await ItemQueryService(session).get_buttons_public(order_no)
    return ApiResponse(success=success, message=message, data=data)


@public_router.post("/execute", response_model=ApiResponse)
async def execute_query_button(
    request: ItemQueryExecuteRequest,
    session: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    """执行查询按钮：订单卡密逐行并发执行；cookie_override 非空时手动 Cookie 单次执行。"""
    success, message, data = await ItemQueryService(session).execute(
        request.order_no, request.button_index, request.cookie_override
    )
    return ApiResponse(success=success, message=message, data=data)
