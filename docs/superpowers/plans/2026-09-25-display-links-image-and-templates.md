# 展示入口图片类型 + 通用展示入口模板 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给买家提卡页的展示入口新增 `image` 类型（本地上传/外链），并新增用户级「通用展示入口」模板库（默认条目在提卡页读取时自动合并到所有商品），Web 与 App 两端均可配置。

**Architecture:** 展示入口条目仍存 `xy_catalog_items.metadata_json.display_links`；通用模板存新表 `xy_display_link_templates`（用户级）。校验与合并逻辑抽到 `backend-web/app/services/display_link_service.py` 共享，提货页下发时「商品自身条目 + is_default 模板」按名称去重合并。

**Tech Stack:** FastAPI + SQLAlchemy(async) + MariaDB / React 18 + TS + Vite (recharts 无关) / Expo SDK 57 + React Native 0.86 + expo-image-picker

## Global Constraints

- 条目类型白名单：`link | text | image`（三端一致）
- 字段白名单收敛（安全）：`link`/`image` 只保留 `name/type/url/note`，`text` 只保留 `name/type/title/content`；禁止额外键入库（防误拷 headers/Cookie 泄漏给买家）
- `image.url`：`/static/` 开头站内路径 或 `http://`/`https://` 外链；`link.url` 仍只允许 http(s)
- `text.content` 上限 2000 字符
- 上传：仅 `image/*`，≤5MB，扩展名白名单 `{.jpg,.jpeg,.png,.gif,.webp,.bmp}`，目录 `STATIC_ROOT/uploads/display_links/`，返回 `/static/uploads/display_links/{filename}`
- 合并顺序：商品自身条目在前，默认模板在后；按 `name.strip().lower()` 去重，商品自身优先
- 合并只发生在提货页读取时；商品 metadata 不写入默认模板（素材透传链路零改动）
- 所有接口按当前登录用户隔离（`resolve_owner_scope`）
- 测试脚本风格：`scripts/test_*.py`，纯 assert，`python scripts/test_xxx.py` 直接运行，末尾 `print("全部测试通过")`
- 前端/移动端 `tsc --noEmit` 必须 0 错误
- 提交信息用中文，格式 `feat:/fix:/docs:` 前缀

---

## 文件结构

**后端（新建）**
- `backend-web/app/services/display_link_service.py` — 校验（单条/整体）+ 合并 + 模板行→条目转换
- `backend-web/app/api/routes/display_link_templates.py` — 模板 CRUD + 模板图片上传
- `common/models/display_link_template.py` — ORM 模型
- `common/db/display_link_schema.py` — 幂等建表
- `scripts/test_display_link_service.py` — 校验/合并纯函数测试

**后端（修改）**
- `backend-web/app/api/routes/item_query.py` — 校验改为引用共享函数；新增商品级图片上传端点
- `backend-web/app/services/agree_pickup_service.py` — `_load_display_links` 加 image 过滤 + 默认模板合并
- `backend-web/app/api/routes/_exports.py` — 注册模板路由
- `common/models/_exports.py` — 导出模型
- `common/db/init_database.py` — 启动时调用 `ensure_display_link_schema`

**Web（新建）**
- `frontend/src/api/displayLinkTemplates.ts` — 模板 CRUD API
- `frontend/src/pages/items/DisplayLinkTemplatesModal.tsx` — 通用入口管理弹窗

**Web（修改）**
- `frontend/src/api/itemQuery.ts` — `DisplayLinkImage` 类型 + 上传 API
- `frontend/src/pages/agree-pickup/AgreePickupPage.tsx` — 图片入口渲染 + 看图弹窗
- `frontend/src/pages/items/ItemQueryConfigModal.tsx` — 图片类型表单 + 从通用入口添加
- `frontend/src/pages/items/Items.tsx` — 工具栏「通用展示入口」按钮

**App（新建）**
- `xianyu-mobile/api/wrappers/display-link-templates.ts` — 模板 CRUD API
- `xianyu-mobile/components/display-links/DisplayLinkEditor.tsx` — 展示入口编辑共享组件
- `xianyu-mobile/app/(tabs)/mine/display-link-templates.tsx` — 通用入口管理页

**App（修改）**
- `xianyu-mobile/api/wrappers/item-query-config.ts` — 展示入口读写 + 上传
- `xianyu-mobile/app/(tabs)/mine/item-edit.tsx` — 展示入口卡片
- `xianyu-mobile/app/(tabs)/mine/material-edit.tsx` — 配置区接入展示入口编辑
- `xianyu-mobile/app/(tabs)/mine/index.tsx` — 菜单入口

---

# Phase 1 — 后端 + Web 实现（多子智能体并行）

## 并行波次

- **Wave 1（互不依赖，可 3 个智能体并行）**：Task 1（后端共享服务+测试）、Task 4（Web API 层）、Task 8（App wrappers）
- **Wave 2（依赖 Wave 1）**：Task 2（后端模型+建表+CRUD+上传，依赖 Task 1）、Task 5（提货页图片渲染，依赖 Task 4）、Task 6（Web 配置弹窗，依赖 Task 4）
- **Wave 3**：Task 3（提货页合并逻辑，依赖 Task 2 的模型）、Task 7（Items 工具栏+模板管理弹窗，依赖 Task 4、Task 6 的弹窗字段模式）

---

### Task 1: 后端共享校验/合并服务（display_link_service）

**Files:**
- Create: `backend-web/app/services/display_link_service.py`
- Modify: `backend-web/app/api/routes/item_query.py:116-166`（改为引用共享函数）
- Test: `scripts/test_display_link_service.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `validate_display_links(links: list) -> tuple[bool, str, list]`
  - `validate_display_link_entry(entry: dict) -> tuple[bool, str, dict]`
  - `merge_display_links(item_links: list, template_links: list) -> list`
  - `template_row_to_entry(template) -> dict`

- [ ] **Step 1: 写失败测试** `scripts/test_display_link_service.py`

```python
"""
display_link_service 校验/合并纯函数测试

覆盖 image 类型校验、字段白名单收敛、默认模板合并去重。
运行：python scripts/test_display_link_service.py
"""
from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend-web"))

from app.services.display_link_service import (
    merge_display_links,
    validate_display_link_entry,
    validate_display_links,
)


def test_image_relative_url_ok() -> None:
    ok, message, entry = validate_display_link_entry(
        {"name": "QQ群", "type": "image", "url": "/static/uploads/display_links/a.png", "note": "扫码进群"}
    )
    assert ok, message
    assert entry == {
        "name": "QQ群", "type": "image",
        "url": "/static/uploads/display_links/a.png", "note": "扫码进群",
    }


def test_image_external_url_ok_and_extra_keys_dropped() -> None:
    """字段白名单：多余键（如 cookie/headers）必须被丢弃，防泄漏给买家"""
    ok, message, entry = validate_display_link_entry(
        {"name": "微信群", "type": "image", "url": "https://img.example.com/qr.png", "cookie": "secret"}
    )
    assert ok, message
    assert entry == {"name": "微信群", "type": "image", "url": "https://img.example.com/qr.png"}
    assert "cookie" not in entry


def test_image_missing_url_rejected() -> None:
    ok, message, _ = validate_display_link_entry({"name": "QQ群", "type": "image"})
    assert not ok and "图片地址" in message


def test_image_invalid_protocol_rejected() -> None:
    ok, message, _ = validate_display_link_entry(
        {"name": "QQ群", "type": "image", "url": "ftp://x/a.png"}
    )
    assert not ok and "/static/" in message


def test_image_missing_name_rejected() -> None:
    ok, message, _ = validate_display_link_entry({"name": "  ", "type": "image", "url": "/static/a.png"})
    assert not ok and "名称" in message


def test_batch_validate_error_position() -> None:
    ok, message, _ = validate_display_links([
        {"name": "A", "type": "link", "url": "https://a.com"},
        {"name": "B", "type": "image"},
    ])
    assert not ok and message.startswith("第 2 个入口")


def test_merge_item_first_and_dedup_by_name() -> None:
    item = [{"name": "QQ群", "type": "image", "url": "/static/own.png"}]
    templates = [
        {"name": " qq群 ", "type": "image", "url": "/static/tpl.png"},  # 同名（忽略大小写/空白）→ 去重
        {"name": "微信群", "type": "image", "url": "/static/wx.png"},
    ]
    merged = merge_display_links(item, templates)
    assert merged == [
        {"name": "QQ群", "type": "image", "url": "/static/own.png"},
        {"name": "微信群", "type": "image", "url": "/static/wx.png"},
    ]


def test_merge_empty_template_name_skipped() -> None:
    merged = merge_display_links([], [{"name": "  ", "type": "image", "url": "/static/a.png"}])
    assert merged == []


if __name__ == "__main__":
    test_image_relative_url_ok()
    test_image_external_url_ok_and_extra_keys_dropped()
    test_image_missing_url_rejected()
    test_image_invalid_protocol_rejected()
    test_image_missing_name_rejected()
    test_batch_validate_error_position()
    test_merge_item_first_and_dedup_by_name()
    test_merge_empty_template_name_skipped()
    print("全部测试通过")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python scripts/test_display_link_service.py`
Expected: `ModuleNotFoundError: No module named 'app.services.display_link_service'`

- [ ] **Step 3: 实现 `backend-web/app/services/display_link_service.py`**

```python
"""展示入口（display_links）校验与合并服务。

商品级展示入口与用户级通用模板共用同一套条目契约：
- link:  {"name", "type": "link",  "url", "note"?}
- text:  {"name", "type": "text",  "title", "content"}
- image: {"name", "type": "image", "url", "note"?}

安全：规范化按白名单收敛字段，防止误拷的 headers/Cookie 等键随提货页下发泄漏给买家。
"""
from __future__ import annotations

from typing import Any

ENTRY_TYPES = ("link", "text", "image")
MAX_TEXT_CONTENT_LEN = 2000


def validate_display_link_entry(entry: Any) -> tuple[bool, str, dict]:
    """校验并规范化单条展示入口。

    Returns:
        (ok, message, normalized)；失败时 normalized 为空 dict。
    """
    if not isinstance(entry, dict):
        return False, "入口配置格式不正确", {}

    name = str(entry.get("name") or "").strip()
    if not name:
        return False, "入口缺少按钮名称", {}

    link_type = str(entry.get("type") or "").strip()
    if link_type not in ENTRY_TYPES:
        return False, "入口的类型仅支持 link/text/image", {}

    if link_type == "link":
        url = str(entry.get("url") or "").strip()
        if not url:
            return False, "入口缺少链接地址", {}
        if not (url.startswith("http://") or url.startswith("https://")):
            return False, "入口的链接地址必须以 http:// 或 https:// 开头", {}
        normalized = {"name": name, "type": link_type, "url": url}
        note = str(entry.get("note") or "").strip()
        if note:
            normalized["note"] = note
        return True, "", normalized

    if link_type == "image":
        url = str(entry.get("url") or "").strip()
        if not url:
            return False, "入口缺少图片地址", {}
        if not (
            url.startswith("/static/")
            or url.startswith("http://")
            or url.startswith("https://")
        ):
            return False, "入口的图片地址必须是 /static/ 开头的站内路径或 http(s) 链接", {}
        normalized = {"name": name, "type": link_type, "url": url}
        note = str(entry.get("note") or "").strip()
        if note:
            normalized["note"] = note
        return True, "", normalized

    # text
    title = str(entry.get("title") or "").strip()
    if not title:
        return False, "入口缺少弹窗标题", {}
    # content 为多行文本，仅校验去空白后非空，存储时保留原文以不破坏换行排版
    content = str(entry.get("content") or "")
    if not content.strip():
        return False, "入口缺少弹窗内容", {}
    if len(content) > MAX_TEXT_CONTENT_LEN:
        return False, f"入口的弹窗内容不能超过 {MAX_TEXT_CONTENT_LEN} 字符", {}
    return True, "", {"name": name, "type": link_type, "title": title, "content": content}


def validate_display_links(links: Any) -> tuple[bool, str, list]:
    """校验并规范化展示入口数组（整体覆盖语义）。

    Returns:
        (ok, message, normalized_links)；失败时 normalized_links 为空列表。
    """
    if not isinstance(links, list):
        return False, "入口配置必须是数组", []
    normalized: list[dict] = []
    for index, link in enumerate(links, start=1):
        ok, message, entry = validate_display_link_entry(link)
        if not ok:
            return False, f"第 {index} 个{message}", []
        normalized.append(entry)
    return True, "", normalized


def merge_display_links(item_links: list, template_links: list) -> list:
    """合并商品自身条目与默认模板条目。

    规则：商品自身条目在前，默认模板在后；按名称（strip+lower）去重，商品自身优先。
    空名称条目直接跳过（脏数据兜底）。
    """
    merged: list[dict] = []
    seen: set[str] = set()
    for entry in list(item_links) + list(template_links):
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("name") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(entry)
    return merged


def template_row_to_entry(template: Any) -> dict:
    """把 xy_display_link_templates 行转换为展示入口条目结构（按类型收敛字段）。"""
    link_type = str(getattr(template, "type", "") or "")
    entry: dict = {"name": getattr(template, "name", "") or "", "type": link_type}
    if link_type in ("link", "image"):
        entry["url"] = getattr(template, "url", "") or ""
        note = getattr(template, "note", "") or ""
        if note:
            entry["note"] = note
    elif link_type == "text":
        entry["title"] = getattr(template, "title", "") or ""
        entry["content"] = getattr(template, "content", "") or ""
    return entry
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python scripts/test_display_link_service.py`
Expected: `全部测试通过`

- [ ] **Step 5: item_query.py 改为引用共享函数**

把 `item_query.py` 的 `_validate_display_links`（116-166 行整段）删除，改为在 import 区加：

```python
from app.services.display_link_service import (
    validate_display_links as _validate_display_links,
    validate_display_link_entry as _validate_display_link_entry,
)
```

说明：保留 `_validate_display_links` 这个名字，现有测试 `scripts/test_display_links.py` 与调用点无需改动。原 docstring 里的契约说明移入 `display_link_service.py`（已含）。

- [ ] **Step 6: 回归旧测试**

Run: `python scripts/test_display_links.py && python scripts/test_query_template.py`
Expected: 两个脚本都输出「全部测试通过」

- [ ] **Step 7: 提交**

```bash
git add backend-web/app/services/display_link_service.py backend-web/app/api/routes/item_query.py scripts/test_display_link_service.py
git commit -m "feat(display-links): 共享校验/合并服务 + image 类型支持"
```

---

### Task 2: 通用展示入口模板（模型 + 建表 + CRUD + 上传）

**Files:**
- Create: `common/models/display_link_template.py`
- Create: `common/db/display_link_schema.py`
- Create: `backend-web/app/api/routes/display_link_templates.py`
- Modify: `common/models/_exports.py`
- Modify: `common/db/init_database.py`（在 ensure_auto_relist_schema 调用后追加）
- Modify: `backend-web/app/api/routes/_exports.py`

**Interfaces:**
- Consumes: Task 1 的 `validate_display_link_entry`、`template_row_to_entry`
- Produces:
  - 模型 `DisplayLinkTemplate`（表 `xy_display_link_templates`，字段见下）
  - `ensure_display_link_schema(conn)` 幂等建表
  - HTTP API（契约见设计文档 §后端接口契约 3）

- [ ] **Step 1: 建模型 `common/models/display_link_template.py`**

```python
"""通用展示入口模板模型（用户级，供提货页默认合并与商品配置快速选用）。"""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from common.db.base_class import Base, TimestampMixin


class DisplayLinkTemplate(TimestampMixin, Base):
    """通用展示入口模板 - 与商品级 display_links 条目同构"""

    __tablename__ = "xy_display_link_templates"
    __table_args__ = (
        Index("idx_dlt_user_default", "user_id", "is_default"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="模板ID")
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True, comment="所属用户ID")
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="入口名称")
    type: Mapped[str] = mapped_column(String(16), nullable=False, comment="类型：link/text/image")
    url: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="链接/图片地址")
    note: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="右侧备注")
    title: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="文本弹窗标题")
    content: Mapped[str | None] = mapped_column(Text, nullable=True, comment="文本弹窗内容")
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0",
        comment="默认展示：提货页读取时自动合并到所有商品",
    )
```

- [ ] **Step 2: 建表脚本 `common/db/display_link_schema.py`**

```python
"""通用展示入口模板表的幂等建表。"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import text

DISPLAY_LINK_TABLE_DDL = """
    CREATE TABLE IF NOT EXISTS xy_display_link_templates (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        user_id BIGINT NOT NULL,
        name VARCHAR(255) NOT NULL,
        type VARCHAR(16) NOT NULL,
        url VARCHAR(512) NULL,
        note VARCHAR(255) NULL,
        title VARCHAR(255) NULL,
        content TEXT NULL,
        is_default TINYINT(1) NOT NULL DEFAULT 0,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        KEY idx_dlt_user_default (user_id, is_default)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


async def ensure_display_link_schema(conn) -> None:
    """创建通用展示入口模板表（幂等，可重复执行）。"""
    await conn.execute(text(DISPLAY_LINK_TABLE_DDL))
    logger.info("通用展示入口模板表已就绪: xy_display_link_templates")
```

- [ ] **Step 3: 挂到启动建表 `common/db/init_database.py`**

在 `await ensure_auto_relist_schema(conn, get_beijing_now_naive())` 之后追加（同一个 `ddl_connection()` 块内）：

```python
                    # 通用展示入口模板表（用户级）
                    await ensure_display_link_schema(conn)
```

并在文件顶部 import 区加：`from common.db.display_link_schema import ensure_display_link_schema`

- [ ] **Step 4: 导出模型 `common/models/_exports.py`**

在 auto_relist 相关导出旁追加：

```python
from common.models.display_link_template import DisplayLinkTemplate
```

并把 `"DisplayLinkTemplate"` 加进该文件的 `__all__`（若无 `__all__` 则只需 import，与文件现有风格一致）。

- [ ] **Step 5: 建路由 `backend-web/app/api/routes/display_link_templates.py`**

```python
"""通用展示入口模板 - 管理接口（用户级）

- GET    /display-link-templates                     列表（按 id 升序）
- POST   /display-link-templates                     新建
- PUT    /display-link-templates/{template_id}       部分更新（type 变更时按新类型重校验并清空不适用字段）
- DELETE /display-link-templates/{template_id}       删除
- POST   /display-link-templates/upload-image        模板图片上传

存储：xy_display_link_templates（用户隔离，resolve_owner_scope）
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.paths import STATIC_ROOT
from app.services.display_link_service import (
    template_row_to_entry,
    validate_display_link_entry,
)
from common.models.display_link_template import DisplayLinkTemplate
from common.models.user import User
from common.schemas.common import ApiResponse
from common.utils.auth_scope import resolve_owner_scope
from common.utils.local_image_upload import ImageUploadError, save_uploaded_image
from pydantic import BaseModel

router = APIRouter(prefix="/display-link-templates", tags=["通用展示入口"])

TEMPLATE_UPLOAD_DIR = STATIC_ROOT / "uploads" / "display_links"


class TemplateSaveRequest(BaseModel):
    """新建/更新通用展示入口模板（PUT 为部分更新语义）"""

    name: Optional[str] = None
    type: Optional[str] = None
    url: Optional[str] = None
    note: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    is_default: Optional[bool] = None


def _apply_entry_to_row(row: DisplayLinkTemplate, entry: dict) -> None:
    """把校验后的条目写回模型行；先清空三类字段避免类型切换残留。"""
    row.name = entry["name"]
    row.type = entry["type"]
    row.url = entry.get("url")
    row.note = entry.get("note")
    row.title = entry.get("title")
    row.content = entry.get("content")


@router.get("", response_model=ApiResponse)
async def list_templates(
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    owner_id, _ = resolve_owner_scope(current_user)
    stmt = select(DisplayLinkTemplate).where(DisplayLinkTemplate.user_id == owner_id).order_by(DisplayLinkTemplate.id)
    rows = (await session.execute(stmt)).scalars().all()
    return ApiResponse(
        success=True,
        message="获取通用展示入口成功",
        data={
            "templates": [
                {**template_row_to_entry(r), "id": r.id, "is_default": bool(r.is_default)}
                for r in rows
            ]
        },
    )


@router.post("", response_model=ApiResponse)
async def create_template(
    payload: TemplateSaveRequest,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    owner_id, _ = resolve_owner_scope(current_user)
    ok, message, entry = validate_display_link_entry(payload.model_dump(exclude_none=True))
    if not ok:
        return ApiResponse(success=False, message=message, data=None)
    row = DisplayLinkTemplate(user_id=owner_id, is_default=bool(payload.is_default))
    _apply_entry_to_row(row, entry)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return ApiResponse(
        success=True,
        message="创建成功",
        data={**template_row_to_entry(row), "id": row.id, "is_default": bool(row.is_default)},
    )


@router.put("/{template_id}", response_model=ApiResponse)
async def update_template(
    template_id: int,
    payload: TemplateSaveRequest,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    owner_id, _ = resolve_owner_scope(current_user)
    row = (
        await session.execute(
            select(DisplayLinkTemplate).where(
                DisplayLinkTemplate.id == template_id,
                DisplayLinkTemplate.user_id == owner_id,
            )
        )
    ).scalars().first()
    if not row:
        return ApiResponse(success=False, message="模板不存在", data=None)

    provided = payload.model_dump(exclude_none=True)
    # 合并现有值后整体校验：保证「部分更新」也不会产生非法组合
    merged = {
        "name": provided.get("name", row.name),
        "type": provided.get("type", row.type),
        "url": provided.get("url", row.url),
        "note": provided.get("note", row.note),
        "title": provided.get("title", row.title),
        "content": provided.get("content", row.content),
    }
    ok, message, entry = validate_display_link_entry(merged)
    if not ok:
        return ApiResponse(success=False, message=message, data=None)
    _apply_entry_to_row(row, entry)
    if "is_default" in provided:
        row.is_default = bool(provided["is_default"])
    await session.commit()
    await session.refresh(row)
    return ApiResponse(
        success=True,
        message="更新成功",
        data={**template_row_to_entry(row), "id": row.id, "is_default": bool(row.is_default)},
    )


@router.delete("/{template_id}", response_model=ApiResponse)
async def delete_template(
    template_id: int,
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    owner_id, _ = resolve_owner_scope(current_user)
    row = (
        await session.execute(
            select(DisplayLinkTemplate).where(
                DisplayLinkTemplate.id == template_id,
                DisplayLinkTemplate.user_id == owner_id,
            )
        )
    ).scalars().first()
    if not row:
        return ApiResponse(success=False, message="模板不存在", data=None)
    await session.delete(row)
    await session.commit()
    return ApiResponse(success=True, message="删除成功", data=None)


@router.post("/upload-image")
async def upload_template_image(
    image: UploadFile = File(...),
    current_user: User = Depends(deps.get_current_active_user),
):
    """上传通用展示入口图片，返回可访问的静态资源 URL"""
    try:
        _, filename, _ = await save_uploaded_image(
            image,
            TEMPLATE_UPLOAD_DIR,
            filename_prefix="tpl",
            short_uuid=True,
        )
    except ImageUploadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return {"success": True, "image_url": f"/static/uploads/display_links/{filename}"}
```

注意：`POST /upload-image` 与 `PUT/DELETE /{template_id}` 方法不同，无路径解析冲突，注册顺序不敏感。

- [ ] **Step 6: 注册路由 `backend-web/app/api/routes/_exports.py`**

import 区加 `display_link_templates,`（与 `item_query` 等并列），并在 router 注册区加：

```python
api_router.include_router(display_link_templates.router)
```

（该 router 自带 `prefix="/display-link-templates"`，注册时不传 prefix。）

- [ ] **Step 7: 商品级图片上传端点（item_query.py 追加）**

在 `item_query.py` 的 `admin_router` 下追加（`DisplayLinksSaveRequest` 定义之后的位置即可）：

```python
# 展示入口图片存储目录（与通用模板共用，URL 可互换使用）
DISPLAY_LINK_UPLOAD_DIR = STATIC_ROOT / "uploads" / "display_links"


@admin_router.post("/{cookie_id}/{item_id}/display-links/upload-image")
async def upload_item_display_link_image(
    cookie_id: str,
    item_id: str,
    image: UploadFile = File(...),
    current_user: User = Depends(deps.get_current_active_user),
    session: AsyncSession = Depends(deps.get_db_session),
):
    """上传商品展示入口图片，返回可访问的静态资源 URL"""
    owner_id, _ = resolve_owner_scope(current_user)
    item = await _load_catalog_item(session, owner_id, item_id)
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
```

import 区追加：

```python
from fastapi import File, HTTPException, UploadFile
from app.core.paths import STATIC_ROOT
from common.utils.local_image_upload import ImageUploadError, save_uploaded_image
```

- [ ] **Step 8: 冒烟验证（本地起服务或直接在服务器验证）**

Run（本地，若有 venv）：
```bash
cd backend-web && python -c "from app.api.routes import display_link_templates as m; print(m.router.prefix)"
```
Expected: `/display-link-templates`

- [ ] **Step 9: 提交**

```bash
git add common/models/display_link_template.py common/db/display_link_schema.py common/db/init_database.py common/models/_exports.py backend-web/app/api/routes/display_link_templates.py backend-web/app/api/routes/item_query.py backend-web/app/api/routes/_exports.py
git commit -m "feat(display-links): 通用展示入口模板表+CRUD+图片上传接口（含商品级上传）"
```

---

### Task 3: 提货页合并逻辑（默认模板自动展示）

**Files:**
- Modify: `backend-web/app/services/agree_pickup_service.py`（`_load_display_links`，约 126-161 行）

**Interfaces:**
- Consumes: Task 1 `merge_display_links`、Task 2 `DisplayLinkTemplate` 模型
- Produces: `_load_display_links` 返回「商品自身 + 默认模板」合并后的数组（提货页无需改动）

- [ ] **Step 1: 改造 `_load_display_links`**

把方法体替换为（保持异常兜底与注释风格）：

```python
    async def _load_display_links(self, order: XYOrder) -> list:
        """读取商品展示入口 = 商品自身条目 + 用户默认模板条目（按名称去重，商品优先）。

        完整内容下发给买家；name/type/url/title/content/note 均为展示文案，不含敏感信息；
        不做 enabled 过滤（该体系没有启用开关，数组里有就展示）。
        任何异常都按空数组处理，不阻断提货主流程。
        """
        try:
            if not order.item_id:
                return []
            result = await self.session.execute(
                select(XYCatalogItem).where(
                    XYCatalogItem.owner_id == order.owner_id,
                    XYCatalogItem.item_id == order.item_id,
                )
            )
            item = result.scalars().first()
            links = (item.metadata_json or {}).get("display_links") if item else None
            item_links = links if isinstance(links, list) else []

            # 默认模板：读取时合并，改动即时全店生效
            template_rows = (
                await self.session.execute(
                    select(DisplayLinkTemplate).where(
                        DisplayLinkTemplate.user_id == order.owner_id,
                        DisplayLinkTemplate.is_default.is_(True),
                    ).order_by(DisplayLinkTemplate.id)
                )
            ).scalars().all()
            template_links = [template_row_to_entry(r) for r in template_rows]

            # 按契约过滤脏数据（绕过管理接口写入的缺字段项），避免前端渲染出空弹窗
            def _valid(entry: object) -> bool:
                if not isinstance(entry, dict):
                    return False
                entry_type = entry.get("type")
                if entry_type in ("link", "image") and entry.get("url"):
                    return True
                if entry_type == "text" and entry.get("title") and entry.get("content"):
                    return True
                return False

            return [e for e in merge_display_links(item_links, template_links) if _valid(e)]
        except Exception as e:
            logger.warning(f"[同意提货] 展示入口配置读取失败 order={order.order_no}: {e}")
            return []
```

import 区追加：

```python
from common.models.display_link_template import DisplayLinkTemplate
from app.services.display_link_service import merge_display_links, template_row_to_entry
```

- [ ] **Step 2: 语法与导入自检**

Run: `cd backend-web && python -c "import ast,sys; ast.parse(open('app/services/agree_pickup_service.py',encoding='utf-8').read()); print('syntax ok')"`
Expected: `syntax ok`

- [ ] **Step 3: 提交**

```bash
git add backend-web/app/services/agree_pickup_service.py
git commit -m "feat(display-links): 提货页读取时合并默认通用入口（按名称去重）"
```

---

### Task 4: Web API 层（类型 + 上传 + 模板 CRUD）

**Files:**
- Modify: `frontend/src/api/itemQuery.ts`
- Create: `frontend/src/api/displayLinkTemplates.ts`

**Interfaces:**
- Consumes: 后端契约（设计文档）
- Produces:
  - `DisplayLinkImage` 类型、`DisplayLink` 联合扩展
  - `uploadItemDisplayLinkImage(cookieId, itemId, file): Promise<string>`（返回 image_url）
  - `getDisplayLinkTemplates() / createDisplayLinkTemplate() / updateDisplayLinkTemplate() / deleteDisplayLinkTemplate() / uploadDisplayLinkTemplateImage(file)`

- [ ] **Step 1: 扩展 `frontend/src/api/itemQuery.ts`**

在 `DisplayLinkText` 后追加并扩展联合类型：

```ts
/** 图片入口：点击弹窗展示图片（url 为 /static/ 站内路径或 http(s) 外链） */
export interface DisplayLinkImage {
  name: string
  type: 'image'
  url: string
  note?: string
}

export type DisplayLink = DisplayLinkLink | DisplayLinkText | DisplayLinkImage
```

追加上传函数（与现有 `saveItemDisplayLinks` 同风格）：

```ts
/** 上传展示入口图片，返回可访问的 image_url（/static/uploads/display_links/xxx） */
export const uploadItemDisplayLinkImage = async (
  cookieId: string,
  itemId: string,
  file: File,
): Promise<string> => {
  const token = localStorage.getItem('auth_token')
  const formData = new FormData()
  formData.append('image', file)
  const resp = await fetch(
    `/api/v1/items/${encodeURIComponent(cookieId)}/${encodeURIComponent(itemId)}/display-links/upload-image`,
    { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: formData },
  )
  const body = await resp.json()
  if (!resp.ok || body?.success === false) {
    throw new Error(body?.message || body?.detail || '图片上传失败')
  }
  const url = body?.image_url ?? body?.data?.image_url
  if (!url) throw new Error('图片上传失败：响应缺少 image_url')
  return url
}
```

- [ ] **Step 2: 新建 `frontend/src/api/displayLinkTemplates.ts`**

```ts
/**
 * 通用展示入口模板 API（用户级，默认条目在提货页读取时自动合并）
 * 后端前缀: /api/v1/display-link-templates
 */
import { get, post, put, del } from '@/utils/request'
import type { ApiResponse } from '@/types'
import type { DisplayLink } from '@/api/itemQuery'

const PREFIX = '/api/v1/display-link-templates'

/** 模板 = 展示入口条目 + 主键 + 默认开关（联合类型用交叉类型而非 extends） */
export type DisplayLinkTemplate = DisplayLink & { id: number; is_default: boolean }

export interface DisplayLinkTemplatePayload {
  name?: string
  type?: string
  url?: string
  note?: string
  title?: string
  content?: string
  is_default?: boolean
}

export const getDisplayLinkTemplates = async (): Promise<DisplayLinkTemplate[]> => {
  const resp = await get<ApiResponse<{ templates: DisplayLinkTemplate[] }>>(PREFIX)
  if (!resp.success || !resp.data) throw new Error(resp.message || '获取通用展示入口失败')
  return resp.data.templates
}

export const createDisplayLinkTemplate = (payload: DisplayLinkTemplatePayload) =>
  post<ApiResponse<DisplayLinkTemplate>>(PREFIX, payload)

export const updateDisplayLinkTemplate = (id: number, payload: DisplayLinkTemplatePayload) =>
  put<ApiResponse<DisplayLinkTemplate>>(`${PREFIX}/${id}`, payload)

export const deleteDisplayLinkTemplate = (id: number) =>
  del<ApiResponse>(`${PREFIX}/${id}`)

/** 上传模板图片，返回 image_url */
export const uploadDisplayLinkTemplateImage = async (file: File): Promise<string> => {
  const token = localStorage.getItem('auth_token')
  const formData = new FormData()
  formData.append('image', file)
  const resp = await fetch(`${PREFIX}/upload-image`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  })
  const body = await resp.json()
  if (!resp.ok || body?.success === false) {
    throw new Error(body?.message || body?.detail || '图片上传失败')
  }
  const url = body?.image_url ?? body?.data?.image_url
  if (!url) throw new Error('图片上传失败：响应缺少 image_url')
  return url
}
```

注意：`@/utils/request` 的 `post/put/del` 泛型用法与 `frontend/src/api/productPublish.ts` 保持一致；若 `del` 不接受泛型则去掉泛型参数（参照该文件实际写法）。

- [ ] **Step 3: 类型检查**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 错误

- [ ] **Step 4: 提交**

```bash
git add frontend/src/api/itemQuery.ts frontend/src/api/displayLinkTemplates.ts
git commit -m "feat(display-links): Web API 层支持图片入口与通用模板"
```

---

### Task 5: 提货页图片入口渲染（AgreePickupPage）

**Files:**
- Modify: `frontend/src/pages/agree-pickup/AgreePickupPage.tsx`（footer 渲染区 282-334 行附近 + 弹窗区）

**Interfaces:**
- Consumes: Task 4 的 `DisplayLinkImage` 类型
- Produces: 买家提卡页图片入口 + 看图弹窗

- [ ] **Step 1: 新增图片弹窗状态**

在文本弹窗状态旁追加：

```tsx
  const [imageModal, setImageModal] = useState<{ name: string; url: string } | null>(null)
```

- [ ] **Step 2: footer 渲染区新增 image 分支**

在 `type === 'link'` 与 `type === 'text'` 之间插入（样式复用现有 footer 按钮类名，与 link 分支同构）：

```tsx
                  {link.type === 'image' && (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => setImageModal({ name: link.name, url: link.url })}
                      className="flex w-full items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-left text-sm hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800"
                    >
                      <span className="flex items-center gap-2">
                        <ImageIcon className="h-4 w-4" />
                        {link.name}
                      </span>
                      {link.note && <span className="text-xs text-slate-400">{link.note}</span>}
                    </button>
                  )}
```

（`idx`/`link` 变量名以文件现有 map 变量为准；`ImageIcon` 从 `lucide-react` 引入，命名冲突时用 `Image as ImageIcon`。）

- [ ] **Step 3: 新增看图弹窗**

在文本弹窗（modal）之后追加：

```tsx
      {imageModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          onClick={() => setImageModal(null)}
        >
          <div
            className="max-h-[85vh] w-full max-w-md overflow-auto rounded-xl bg-white p-4 dark:bg-slate-800"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">{imageModal.name}</h3>
              <button type="button" onClick={() => setImageModal(null)} className="text-slate-400 hover:text-slate-600">
                <X className="h-4 w-4" />
              </button>
            </div>
            <img
              src={imageModal.url}
              alt={imageModal.name}
              className="mx-auto max-h-[70vh] w-auto object-contain"
              onError={(e) => {
                const el = e.currentTarget
                el.style.display = 'none'
                el.insertAdjacentHTML('afterend', '<p class="py-8 text-center text-sm text-slate-400">图片加载失败</p>')
              }}
            />
          </div>
        </div>
      )}
```

- [ ] **Step 4: 类型检查**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 错误

- [ ] **Step 5: 提交**

```bash
git add frontend/src/pages/agree-pickup/AgreePickupPage.tsx
git commit -m "feat(display-links): 提货页图片入口渲染与看图弹窗"
```

---

### Task 6: Web 商品配置弹窗（图片类型 + 从通用入口添加）

**Files:**
- Modify: `frontend/src/pages/items/ItemQueryConfigModal.tsx`

**Interfaces:**
- Consumes: Task 4 全部 API
- Produces: 配置弹窗支持 image 编辑与模板选用

- [ ] **Step 1: 扩展草稿结构与转换函数**

`LinkDraft` 增加字段（保持扁平结构）：

```ts
interface LinkDraft {
  name: string
  type: 'link' | 'text' | 'image'
  url: string
  note: string
  title: string
  content: string
}
```

`linkToDraft` 增加 image 分支（url/note 与 link 相同回填）；`toDisplayLink` 增加：

```ts
  if (draft.type === 'image') {
    const url = draft.url.trim()
    if (!url) throw new Error('请填写图片地址或上传图片')
    if (!(url.startsWith('/static/') || url.startsWith('http://') || url.startsWith('https://'))) {
      throw new Error('图片地址必须是 /static/ 开头的站内路径或 http(s) 链接')
    }
    const entry: DisplayLinkImage = { name, type: 'image', url }
    if (draft.note.trim()) entry.note = draft.note.trim()
    return entry
  }
```

- [ ] **Step 2: 类型下拉加「图片」选项**

```tsx
                <option value="image">图片</option>
```

- [ ] **Step 3: 图片分支表单（上传 + URL + 预览 + 备注）**

在 link 分支字段区后追加（`uploading` 为新增的 per-entry 上传中状态，用 `useState<Record<number, boolean>>` 或单个 index 均可）：

```tsx
          {draft.type === 'image' && (
            <>
              <div className="flex items-center gap-2">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={async (e) => {
                    const file = e.target.files?.[0]
                    e.target.value = ''
                    if (!file) return
                    if (!file.type.startsWith('image/')) { addToast({ type: 'error', message: '请选择图片文件' }); return }
                    if (file.size > 5 * 1024 * 1024) { addToast({ type: 'error', message: '图片不能超过 5MB' }); return }
                    try {
                      setUploadingIndex(index)
                      const url = await uploadItemDisplayLinkImage(cookieId, itemId, file)
                      updateLinkDraft(index, { url })
                      addToast({ type: 'success', message: '图片已上传' })
                    } catch (err) {
                      addToast({ type: 'error', message: (err as Error).message })
                    } finally {
                      setUploadingIndex(null)
                    }
                  }}
                />
                <button type="button" className="btn-ios-secondary" onClick={() => fileInputRef.current?.click()} disabled={uploadingIndex === index}>
                  {uploadingIndex === index ? '上传中...' : '上传图片'}
                </button>
                <span className="text-xs text-slate-400">或直接粘贴图片链接</span>
              </div>
              <Input label="图片地址" value={draft.url} onChange={(e) => updateLinkDraft(index, { url: e.target.value })} placeholder="/static/uploads/display_links/xxx.png 或 https://..." />
              {draft.url && (
                <img src={draft.url} alt="预览" className="mt-2 max-h-32 rounded border border-slate-200 object-contain dark:border-slate-700" />
              )}
              <Input label="备注（可选）" value={draft.note} onChange={(e) => updateLinkDraft(index, { note: e.target.value })} placeholder="如：扫码进群" />
            </>
          )}
```

（`Input`/`addToast`/按钮类名以该文件现有用法为准；`cookieId`/`itemId` 取该组件的 props。）

- [ ] **Step 4: 「从通用入口添加」选择器**

在展示入口列表上方加一行：

```tsx
          <div className="mb-2 flex items-center justify-between">
            <button
              type="button"
              className="text-sm text-blue-600 hover:underline dark:text-blue-400"
              onClick={() => setTemplatePickerOpen((v) => !v)}
            >
              从通用入口添加
            </button>
          </div>
          {templatePickerOpen && (
            <div className="mb-3 rounded-lg border border-slate-200 p-2 dark:border-slate-700">
              {availableTemplates.length === 0 ? (
                <p className="py-2 text-center text-xs text-slate-400">通用入口为空或已全部添加</p>
              ) : (
                availableTemplates.map((tpl) => (
                  <button
                    key={tpl.id}
                    type="button"
                    className="flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-sm hover:bg-slate-50 dark:hover:bg-slate-800"
                    onClick={() => { addLinkDraft(templateToDraft(tpl)); setTemplatePickerOpen(false) }}
                  >
                    <span className="flex items-center gap-2">
                      <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500 dark:bg-slate-700 dark:text-slate-300">
                        {tpl.type === 'link' ? '链接' : tpl.type === 'text' ? '文本' : '图片'}
                      </span>
                      {tpl.name}
                    </span>
                    {tpl.is_default && <span className="text-[10px] text-emerald-600">默认</span>}
                  </button>
                ))
              )}
            </div>
          )}
```

配套状态与派生：

```tsx
  const [templatePickerOpen, setTemplatePickerOpen] = useState(false)
  const [templates, setTemplates] = useState<DisplayLinkTemplate[]>([])
  // 展示入口 tab 首次展开时加载模板（与 links 懒加载同处）
  // availableTemplates = 名称未出现在当前草稿中的模板
  const availableTemplates = useMemo(() => {
    const used = new Set(linkDrafts.map((d) => d.name.trim().toLowerCase()).filter(Boolean))
    return templates.filter((t) => !used.has(t.name.trim().toLowerCase()))
  }, [templates, linkDrafts])
```

`templateToDraft(tpl)` 为纯函数（模板 → LinkDraft，字段直接映射）。

- [ ] **Step 5: 类型检查**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 错误

- [ ] **Step 6: 提交**

```bash
git add frontend/src/pages/items/ItemQueryConfigModal.tsx
git commit -m "feat(display-links): 配置弹窗支持图片类型与从通用入口添加"
```

---

### Task 7: 商品管理页工具栏 + 通用入口管理弹窗

**Files:**
- Create: `frontend/src/pages/items/DisplayLinkTemplatesModal.tsx`
- Modify: `frontend/src/pages/items/Items.tsx`

**Interfaces:**
- Consumes: Task 4 模板 API；Task 6 的图片表单字段模式
- Produces: 「通用展示入口」管理弹窗

- [ ] **Step 1: 新建 `DisplayLinkTemplatesModal.tsx`**

结构（复用 ItemQueryConfigModal 的字段与样式模式）：

- Props: `{ visible: boolean; onClose: () => void }`
- 打开时 `getDisplayLinkTemplates()` 加载；失败显示内联错误 + 重试（禁止空态覆盖）
- 列表项：类型徽标 + 名称 + 「默认展示」Switch（调 `updateDisplayLinkTemplate(id, { is_default })`，乐观更新失败回滚）+ 编辑 + 删除（确认框）
- 新增/编辑表单：名称、类型下拉（链接/文本/图片）、按类型条件字段（含图片上传 + URL + 预览 + 备注），保存调 create/update
- 顶部说明文案：「标记为『默认展示』的入口会自动出现在所有商品的提卡页底部（按名称去重，商品自身配置优先）」

- [ ] **Step 2: `Items.tsx` 工具栏加按钮**

在现有工具栏按钮组中追加：

```tsx
        <button onClick={() => setTemplatesModalOpen(true)} className="btn-ios-secondary">
          <Images className="w-4 h-4" />
          <span className="hidden sm:inline">通用展示入口</span>
          <span className="sm:hidden">通用入口</span>
        </button>
```

配套：`const [templatesModalOpen, setTemplatesModalOpen] = useState(false)` 与 `<DisplayLinkTemplatesModal visible={templatesModalOpen} onClose={() => setTemplatesModalOpen(false)} />`。

- [ ] **Step 3: 类型检查**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 错误

- [ ] **Step 4: 提交**

```bash
git add frontend/src/pages/items/DisplayLinkTemplatesModal.tsx frontend/src/pages/items/Items.tsx
git commit -m "feat(display-links): 商品管理页新增通用展示入口管理"
```

---

### Task 8: App wrappers（展示入口读写/上传 + 模板 CRUD）

**Files:**
- Modify: `xianyu-mobile/api/wrappers/item-query-config.ts`
- Create: `xianyu-mobile/api/wrappers/display-link-templates.ts`

**Interfaces:**
- Consumes: 后端契约
- Produces:
  - `DisplayLinkEntry` 类型（三型联合）
  - `getItemDisplayLinks(cookieId, itemId)` / `saveItemDisplayLinks(cookieId, itemId, links)` / `uploadItemDisplayLinkImage(cookieId, itemId, uri)`
  - `getDisplayLinkTemplates()` / `createDisplayLinkTemplate()` / `updateDisplayLinkTemplate()` / `deleteDisplayLinkTemplate()` / `uploadDisplayLinkTemplateImage(uri)`

- [ ] **Step 1: 扩展 `item-query-config.ts`**

```ts
// ---------------------------------------------------------------------------
// 商品展示入口（存 xy_catalog_items.metadata_json.display_links）
//   GET/PUT /api/v1/items/{cookie_id}/{item_id}/display-links
//   POST    /api/v1/items/{cookie_id}/{item_id}/display-links/upload-image
// ---------------------------------------------------------------------------

/** 展示入口条目（三型联合，字段与后端契约一致） */
export type DisplayLinkEntry =
  | { name: string; type: 'link'; url: string; note?: string }
  | { name: string; type: 'text'; title: string; content: string }
  | { name: string; type: 'image'; url: string; note?: string }

/** 读取商品展示入口（返回商品自身条目，不含默认模板） */
export async function getItemDisplayLinks(cookieId: string, itemId: string): Promise<DisplayLinkEntry[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    `/api/v1/items/${encodeURIComponent(cookieId)}/${encodeURIComponent(itemId)}/display-links`,
  )) as { data?: unknown; error?: unknown };
  const inner = (data as any)?.data ?? data;
  const list = inner?.links;
  if (!Array.isArray(list)) return [];
  return list.filter((e): e is DisplayLinkEntry => !!e && typeof e === 'object' && typeof e.name === 'string' && typeof e.type === 'string');
}

/** 整体覆盖保存商品展示入口 */
export async function saveItemDisplayLinks(cookieId: string, itemId: string, links: DisplayLinkEntry[]): Promise<void> {
  const client = await getApiClient();
  const { error } = (await (client.PUT as any)(
    `/api/v1/items/${encodeURIComponent(cookieId)}/${encodeURIComponent(itemId)}/display-links`,
    { body: { links } },
  )) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
}

/** 上传展示入口图片（multipart），返回 image_url */
export async function uploadItemDisplayLinkImage(cookieId: string, itemId: string, fileUri: string): Promise<string> {
  const client = await getApiClient();
  const form = new FormData();
  const name = fileUri.split('/').pop() || 'image.jpg';
  const ext = (name.split('.').pop() || 'jpg').toLowerCase();
  form.append('image', { uri: fileUri, name, type: `image/${ext === 'jpg' ? 'jpeg' : ext}` } as any);
  const resp = await (client.POST as any)(
    `/api/v1/items/${encodeURIComponent(cookieId)}/${encodeURIComponent(itemId)}/display-links/upload-image`,
    { body: form, bodySerializer: (b: any) => b },
  );
  const url = (resp as any)?.data?.image_url ?? (resp as any)?.data?.data?.image_url;
  if (!url) throw new Error('图片上传失败');
  return url as string;
}
```

注意：multipart 上传的 client 调用方式需与仓库现有上传实现一致（参照 `xianyu-mobile/api/wrappers/` 中已有的图片上传函数，如 `product-publish.ts` 的 `uploadProductImages`；若其用 `fetch` + `getApiBaseUrl()`，则照抄该模式，不要自创）。

- [ ] **Step 2: 新建 `display-link-templates.ts`**

```ts
import { getApiClient, extractError } from './client';
import type { DisplayLinkEntry } from './item-query-config';

/** 通用展示入口模板（用户级；is_default 的条目在提卡页自动合并到所有商品） */
export interface DisplayLinkTemplate extends Record<string, unknown> {
  id: number;
  name: string;
  type: 'link' | 'text' | 'image';
  url?: string;
  note?: string;
  title?: string;
  content?: string;
  is_default: boolean;
}

const PREFIX = '/api/v1/display-link-templates';

function unwrapList(data: unknown): DisplayLinkTemplate[] {
  const inner = (data as any)?.data ?? data;
  const list = inner?.templates;
  if (!Array.isArray(list)) return [];
  return list.filter((t: any) => t && typeof t.id === 'number');
}

export async function getDisplayLinkTemplates(): Promise<DisplayLinkTemplate[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(PREFIX)) as { data?: unknown };
  return unwrapList(data);
}

export async function createDisplayLinkTemplate(payload: Partial<DisplayLinkEntry> & { is_default?: boolean }): Promise<void> {
  const client = await getApiClient();
  const { data, error } = (await (client.POST as any)(PREFIX, { body: payload })) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
  if ((data as any)?.success === false) throw new Error((data as any)?.message || '创建失败');
}

export async function updateDisplayLinkTemplate(id: number, payload: Record<string, unknown>): Promise<void> {
  const client = await getApiClient();
  const { data, error } = (await (client.PUT as any)(`${PREFIX}/${id}`, { body: payload })) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
  if ((data as any)?.success === false) throw new Error((data as any)?.message || '更新失败');
}

export async function deleteDisplayLinkTemplate(id: number): Promise<void> {
  const client = await getApiClient();
  await (client.DELETE as any)(`${PREFIX}/${id}`);
}

/** 上传模板图片，返回 image_url（实现方式与 item-query-config 的上传保持一致） */
export async function uploadDisplayLinkTemplateImage(fileUri: string): Promise<string> {
  const client = await getApiClient();
  const form = new FormData();
  const name = fileUri.split('/').pop() || 'image.jpg';
  const ext = (name.split('.').pop() || 'jpg').toLowerCase();
  form.append('image', { uri: fileUri, name, type: `image/${ext === 'jpg' ? 'jpeg' : ext}` } as any);
  const resp = await (client.POST as any)(`${PREFIX}/upload-image`, { body: form, bodySerializer: (b: any) => b });
  const url = (resp as any)?.data?.image_url ?? (resp as any)?.data?.data?.image_url;
  if (!url) throw new Error('图片上传失败');
  return url as string;
}
```

- [ ] **Step 3: 类型检查**

Run: `cd xianyu-mobile && npx tsc --noEmit`
Expected: 0 错误

- [ ] **Step 4: 提交**

```bash
git add xianyu-mobile/api/wrappers/item-query-config.ts xianyu-mobile/api/wrappers/display-link-templates.ts
git commit -m "feat(mobile): 展示入口与通用模板 API 层"
```

---

# Phase 2 — Web + 后端 2 轮审查测试优化

**第 1 轮（正确性/安全/契约）**
- 审查点：字段白名单是否真的收敛（image 分支不得透传额外键）；合并去重的名称归一化（trim+lower）；模板 PUT 部分更新不产生非法组合；上传端点权限与大小/类型校验；`_load_display_links` 异常兜底不阻断提货
- 测试：跑 `scripts/test_display_link_service.py` + `scripts/test_display_links.py` + `scripts/test_query_template.py`；前端 `tsc`；后端模块 import 冒烟
- 产出：问题清单 → 逐条修复 → 复跑测试

**第 2 轮（端到端/边界）**
- 部署到服务器（后端重启 + 前端构建），真实验证：
  1. 商品配置上传图片入口 → 保存 → 提卡页出现入口 → 点击弹窗看图
  2. 通用入口新建 image + 设为默认 → 未配置该条目的商品提卡页自动出现；取消默认 → 立即消失
  3. 商品自身同名条目 vs 默认模板 → 只显示商品自己的
  4. 外链图片、`/static/` 相对路径都能显示；坏链接显示「图片加载失败」
  5. 删除模板 → 提卡页即时消失
- 边界：空数组保存、2000 字符文本上限、5MB/非图片上传被拒
- 产出：修复 + 复验

---

# Phase 3 — App 端完善（3 轮审查测试优化）

### Task 9: App 展示入口编辑共享组件

**Files:**
- Create: `xianyu-mobile/components/display-links/DisplayLinkEditor.tsx`

**Interfaces:**
- Consumes: Task 8 wrappers（`DisplayLinkEntry`、`getDisplayLinkTemplates`）
- Produces: `<DisplayLinkEditor entries={entries} onChange={setEntries} uploadImage={(uri) => Promise<string>} />`
  —— item-edit 与 material-edit 共用；上传函数由调用方注入（商品级传 `uploadItemDisplayLinkImage` 绑定后的闭包，素材级传 `uploadDisplayLinkTemplateImage`）

- [ ] **Step 1: 实现组件（完整骨架）**

```tsx
import { useCallback, useEffect, useState } from 'react';
import { View, Text, StyleSheet, Pressable, Alert, Image } from 'react-native';
import { useColorScheme } from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { Link2, FileText, Image as ImageIcon, Plus, Trash2, ChevronDown } from 'lucide-react-native';
import { Card, Button, Input } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import { getDisplayLinkTemplates, type DisplayLinkTemplate } from '@/api/wrappers/display-link-templates';
import type { DisplayLinkEntry } from '@/api/wrappers/item-query-config';

type EntryType = DisplayLinkEntry['type'];

interface Props {
  entries: DisplayLinkEntry[];
  onChange: (next: DisplayLinkEntry[]) => void;
  /** 注入的上传实现：返回 image_url（/static/... 或 http(s)） */
  uploadImage: (fileUri: string) => Promise<string>;
  /** 顶部说明文案（可选） */
  hint?: string;
}

const TYPE_LABEL: Record<EntryType, string> = { link: '链接', text: '文本', image: '图片' };

/** 按类型构造空白草稿（编辑态与条目结构一致，扁平保存） */
function emptyEntry(type: EntryType): DisplayLinkEntry {
  if (type === 'link') return { name: '', type: 'link', url: '', note: '' };
  if (type === 'image') return { name: '', type: 'image', url: '', note: '' };
  return { name: '', type: 'text', title: '', content: '' };
}

/** 条目 → 可编辑草稿（字段齐备，避免 undefined 受控告警） */
function toDraft(e: DisplayLinkEntry): Required<Pick<DisplayLinkEntry, 'name'>> & Record<string, string> {
  return {
    name: e.name,
    type: e.type,
    url: (e as any).url ?? '',
    note: (e as any).note ?? '',
    title: (e as any).title ?? '',
    content: (e as any).content ?? '',
  } as any;
}

/** 校验单条（与后端契约一致），返回错误文案或 null */
export function validateEntry(draft: Record<string, string>): string | null {
  const name = (draft.name ?? '').trim();
  if (!name) return '请填写入口名称';
  if (draft.type === 'link') {
    const url = (draft.url ?? '').trim();
    if (!url) return '请填写链接地址';
    if (!/^https?:\/\//.test(url)) return '链接地址必须以 http:// 或 https:// 开头';
  } else if (draft.type === 'image') {
    const url = (draft.url ?? '').trim();
    if (!url) return '请上传图片或填写图片地址';
    if (!(url.startsWith('/static/') || /^https?:\/\//.test(url))) return '图片地址必须是 /static/ 开头的站内路径或 http(s) 链接';
  } else {
    if (!(draft.title ?? '').trim()) return '请填写弹窗标题';
    const content = draft.content ?? '';
    if (!content.trim()) return '请填写弹窗内容';
    if (content.length > 2000) return '弹窗内容不能超过 2000 字符';
  }
  return null;
}

/** 草稿 → 条目（白名单字段，丢弃空的可选字段） */
export function draftToEntry(draft: Record<string, string>): DisplayLinkEntry {
  const name = draft.name.trim();
  if (draft.type === 'link' || draft.type === 'image') {
    const entry: any = { name, type: draft.type, url: draft.url.trim() };
    if (draft.note.trim()) entry.note = draft.note.trim();
    return entry as DisplayLinkEntry;
  }
  return { name, type: 'text', title: draft.title.trim(), content: draft.content };
}

export function DisplayLinkEditor({ entries, onChange, uploadImage, hint }: Props) {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const [drafts, setDrafts] = useState<Record<string, string>[]>(() => entries.map(toDraft));
  const [pickerOpen, setPickerOpen] = useState(false);
  const [templates, setTemplates] = useState<DisplayLinkTemplate[]>([]);
  const [uploadingIndex, setUploadingIndex] = useState<number | null>(null);

  // 外部 entries 变化（如服务端加载完成）时重建草稿
  useEffect(() => { setDrafts(entries.map(toDraft)); }, [entries]);

  const emit = useCallback((next: Record<string, string>[]) => {
    setDrafts(next);
    onChange(next.map(draftToEntry));
  }, [onChange]);

  const updateDraft = (index: number, patch: Record<string, string>) => {
    emit(drafts.map((d, i) => (i === index ? { ...d, ...patch } : d)));
  };

  const addEntry = (type: EntryType) => {
    const blank = toDraft(emptyEntry(type));
    emit([...drafts, blank]);
  };

  const removeEntry = (index: number) => {
    Alert.alert('删除入口', '确认删除该展示入口？', [
      { text: '取消', style: 'cancel' },
      { text: '删除', style: 'destructive', onPress: () => emit(drafts.filter((_, i) => i !== index)) },
    ]);
  };

  const pickImage = async (index: number) => {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) { Alert.alert('提示', '需要相册权限才能选择图片'); return; }
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 0.9 });
    if (res.canceled || !res.assets?.[0]) return;
    try {
      setUploadingIndex(index);
      const url = await uploadImage(res.assets[0].uri);
      updateDraft(index, { url });
    } catch (e) {
      Alert.alert('上传失败', (e as Error).message);
    } finally {
      setUploadingIndex(null);
    }
  };

  const openTemplatePicker = async () => {
    try {
      const list = await getDisplayLinkTemplates();
      setTemplates(list);
      setPickerOpen(true);
    } catch (e) {
      Alert.alert('加载失败', (e as Error).message);
    }
  };

  const insertTemplate = (tpl: DisplayLinkTemplate) => {
    const used = new Set(drafts.map((d) => (d.name ?? '').trim().toLowerCase()).filter(Boolean));
    if (used.has(tpl.name.trim().toLowerCase())) {
      Alert.alert('提示', '同名入口已存在');
      return;
    }
    emit([...drafts, toDraft(tpl as unknown as DisplayLinkEntry)]);
    setPickerOpen(false);
  };

  const available = templates.filter(
    (t) => !drafts.some((d) => (d.name ?? '').trim().toLowerCase() === t.name.trim().toLowerCase()),
  );

  return (
    <View style={styles.wrap}>
      {hint ? <Text style={[styles.hint, { color: c.textMuted }]}>{hint}</Text> : null}

      {drafts.map((draft, index) => (
        <Card key={index} style={styles.entryCard}>
          <View style={styles.rowBetween}>
            <Text style={[styles.typeBadge, { color: c.primary }]}>{TYPE_LABEL[draft.type as EntryType] ?? draft.type}</Text>
            <Pressable onPress={() => removeEntry(index)} hitSlop={8}>
              <Trash2 size={16} stroke={c.danger ?? c.textMuted} />
            </Pressable>
          </View>

          <Input label="名称" value={draft.name} onChangeText={(v) => updateDraft(index, { name: v })} placeholder="如：QQ群" />

          {(draft.type === 'link' || draft.type === 'image') && (
            <>
              <Input
                label={draft.type === 'image' ? '图片地址' : '链接地址'}
                value={draft.url}
                onChangeText={(v) => updateDraft(index, { url: v })}
                placeholder={draft.type === 'image' ? '/static/uploads/display_links/xxx.png 或 https://...' : 'https://...'}
                autoCapitalize="none"
              />
              {draft.type === 'image' ? (
                <>
                  <Button
                    label={uploadingIndex === index ? '上传中...' : '从相册选择图片'}
                    variant="secondary"
                    onPress={() => pickImage(index)}
                    disabled={uploadingIndex !== null}
                  />
                  {!!draft.url && (
                    <Image source={{ uri: draft.url }} style={styles.preview} resizeMode="contain" />
                  )}
                </>
              ) : null}
              <Input label="备注（可选）" value={draft.note} onChangeText={(v) => updateDraft(index, { note: v })} placeholder="如：扫码进群" />
            </>
          )}

          {draft.type === 'text' && (
            <>
              <Input label="弹窗标题" value={draft.title} onChangeText={(v) => updateDraft(index, { title: v })} />
              <Input
                label="弹窗内容"
                value={draft.content}
                onChangeText={(v) => updateDraft(index, { content: v })}
                multiline
                textAlignVertical="top"
                style={styles.textarea}
              />
            </>
          )}
        </Card>
      ))}

      <View style={styles.actions}>
        {(['link', 'text', 'image'] as EntryType[]).map((t) => (
          <Button key={t} label={`+ ${TYPE_LABEL[t]}`} variant="secondary" onPress={() => addEntry(t)} style={styles.actionBtn} />
        ))}
      </View>

      <Pressable onPress={openTemplatePicker} style={styles.templateEntry}>
        <ChevronDown size={14} stroke={c.primary} />
        <Text style={[styles.templateEntryText, { color: c.primary }]}>从通用入口添加</Text>
      </Pressable>

      {pickerOpen && (
        <Card style={styles.pickerCard}>
          {available.length === 0 ? (
            <Text style={[styles.hint, { color: c.textMuted }]}>通用入口为空或已全部添加</Text>
          ) : (
            available.map((tpl) => (
              <Pressable key={tpl.id} onPress={() => insertTemplate(tpl)} style={styles.pickerRow}>
                <Text style={[styles.typeBadge, { color: c.primary }]}>{TYPE_LABEL[tpl.type]}</Text>
                <Text style={[styles.pickerName, { color: c.text }]} numberOfLines={1}>{tpl.name}</Text>
                {tpl.is_default && <Text style={styles.defaultBadge}>默认</Text>}
              </Pressable>
            ))
          )}
        </Card>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.sm },
  hint: { ...typography.small },
  entryCard: { gap: spacing.sm },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  typeBadge: { ...typography.small, fontWeight: '600' },
  preview: { width: '100%', height: 140, borderRadius: radius.sm, backgroundColor: 'transparent' },
  textarea: { minHeight: 88, paddingTop: spacing.md },
  actions: { flexDirection: 'row', gap: spacing.sm },
  actionBtn: { flex: 1 },
  templateEntry: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs, paddingVertical: spacing.xs },
  templateEntryText: { ...typography.caption },
  pickerCard: { gap: spacing.xs },
  pickerRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, paddingVertical: spacing.xs },
  pickerName: { ...typography.body, flex: 1 },
  defaultBadge: { ...typography.small, color: '#10b981' },
});
```

实现时核对：`@/components/ui` 的 `Input`/`Button` 是否支持 `label`、`multiline`、`style` 等 props（若 `Input` 不支持 `label`，改为上方 `<Text>` + 无 label 的 `Input`，与 item-edit 现有写法保持一致）；`colors[...]` 是否含 `danger`（没有则用 `c.textMuted`）。

- [ ] **Step 2: 类型检查** `cd xianyu-mobile && npx tsc --noEmit` → 0 错误

- [ ] **Step 3: 提交** `git add xianyu-mobile/components/display-links/DisplayLinkEditor.tsx && git commit -m "feat(mobile): 展示入口编辑共享组件"`

### Task 10: item-edit 接入展示入口卡片

**Files:** Modify `xianyu-mobile/app/(tabs)/mine/item-edit.tsx`

**Interfaces:**
- Consumes: Task 9 `DisplayLinkEditor`；Task 8 `getItemDisplayLinks`/`saveItemDisplayLinks`/`uploadItemDisplayLinkImage`
- Produces: 商品编辑页展示入口配置能力

- [ ] **Step 1:** 在「查询配置」卡片之后新增同构的折叠卡片，状态与加载照抄查询配置模式：

```tsx
  // 展示入口（展开时才加载）
  const [linksExpanded, setLinksExpanded] = useState(false);
  const [linkEntries, setLinkEntries] = useState<DisplayLinkEntry[]>([]);
  const [linksLoaded, setLinksLoaded] = useState(false);
  const [linksLoading, setLinksLoading] = useState(false);
  const [linksLoadError, setLinksLoadError] = useState('');
  const [savingLinks, setSavingLinks] = useState(false);

  const loadDisplayLinks = useCallback(async () => {
    if (!cookieId || !itemId) return;
    setLinksLoading(true);
    try {
      const list = await getItemDisplayLinks(cookieId, itemId);
      setLinkEntries(list);
      setLinksLoaded(true);
      setLinksLoadError('');
    } catch (e) {
      setLinksLoadError((e as Error).message || '获取展示入口失败');
    } finally {
      setLinksLoading(false);
    }
  }, [cookieId, itemId]);

  async function handleSaveDisplayLinks() {
    if (!linksLoaded) return;
    for (const [i, entry] of linkEntries.entries()) {
      const err = validateEntry(toDraft(entry) as Record<string, string>);
      if (err) { Alert.alert('请检查展示入口', `第 ${i + 1} 个：${err}`); return; }
    }
    setSavingLinks(true);
    try {
      await saveItemDisplayLinks(cookieId, itemId, linkEntries);
      Alert.alert('保存成功', '展示入口已更新');
    } catch (e) {
      Alert.alert('保存失败', (e as Error).message);
    } finally {
      setSavingLinks(false);
    }
  }
```

卡片 JSX（与查询配置卡片同构，展开时懒加载）：

```tsx
        {/* 展示入口（发布后买家提卡页底部可见；默认通用入口自动展示，无需在此重复添加） */}
        <Card style={styles.collapsibleCard}>
          <Pressable onPress={() => { setLinksExpanded((v) => !v); if (!linksExpanded && !linksLoaded && !linksLoading) loadDisplayLinks(); }} style={styles.collapsibleHeader}>
            <Text style={[styles.cardTitle, { color: c.text }]}>展示入口</Text>
            <ChevronDown size={16} stroke={c.textMuted} style={{ transform: [{ rotate: linksExpanded ? '180deg' : '0deg' }] }} />
          </Pressable>
          {linksExpanded && (
            linksLoadError ? (
              <LoadErrorInline message={linksLoadError} onRetry={loadDisplayLinks} />
            ) : linksLoading ? (
              <Loading label="加载展示入口..." />
            ) : (
              <>
                <DisplayLinkEditor
                  entries={linkEntries}
                  onChange={setLinkEntries}
                  uploadImage={(uri) => uploadItemDisplayLinkImage(cookieId, itemId, uri)}
                  hint="商品自身的入口优先于通用默认入口；同名时以商品配置为准"
                />
                <Button label="保存展示入口" onPress={handleSaveDisplayLinks} loading={savingLinks} disabled={!linksLoaded} style={styles.saveBtn} />
              </>
            )
          )}
        </Card>
```

（`LoadErrorInline`/`styles.collapsibleCard` 等复用文件里已有的同名辅助与样式；`cookieId`/`itemId` 用该页现有变量名。）

- [ ] **Step 2:** `cd xianyu-mobile && npx tsc --noEmit` → 0 错误
- [ ] **Step 3:** 提交 `git commit -m "feat(mobile): 商品编辑页支持展示入口配置"`

### Task 11: material-edit 接入展示入口编辑

**Files:** Modify `xianyu-mobile/app/(tabs)/mine/material-edit.tsx`

- [ ] **Step 1:** 在「商品列表配置」卡片内、查询按钮编辑之后接入（数据源为 `item_config.display_links`）：

```tsx
  const [cfgDisplayLinks, setCfgDisplayLinks] = useState<DisplayLinkEntry[]>([]);

  // 编辑模式加载素材详情时回填（与 cfgCardIds 同处）
  setCfgDisplayLinks((cfg.display_links as DisplayLinkEntry[]) ?? []);

  // 采集填充时同步（与 setCfgCardIds 同处）
  setCfgDisplayLinks((cfg.display_links as DisplayLinkEntry[]) ?? []);

  // buildItemConfig() 内加入
  display_links: cfgDisplayLinks,

  // 卡片内渲染（上传注入模板级上传：素材无 cookie/item，存储目录与商品级相同，URL 可互换）
  <DisplayLinkEditor
    entries={cfgDisplayLinks}
    onChange={setCfgDisplayLinks}
    uploadImage={uploadDisplayLinkTemplateImage}
    hint="随素材保存，发布成功后回写到新商品列表项"
  />
```

- [ ] **Step 2:** `cd xianyu-mobile && npx tsc --noEmit` → 0 错误
- [ ] **Step 3:** 提交 `git commit -m "feat(mobile): 素材编辑页支持展示入口配置"`

### Task 12: 通用展示入口管理页 + 菜单入口

**Files:**
- Create `xianyu-mobile/app/(tabs)/mine/display-link-templates.tsx`
- Modify `xianyu-mobile/app/(tabs)/mine/index.tsx`、`xianyu-mobile/app/(tabs)/mine/_layout.tsx`（注册 Stack 路由）

- [ ] **Step 1:** 页面实现（列表 + 默认开关 + 增删改 + 图片上传）：

```tsx
// 顶部说明：标记「默认展示」的入口会自动出现在所有商品的提卡页底部（按名称去重，商品自身配置优先）
// 列表项：类型徽标 + 名称 + Switch(is_default) + 编辑 / 删除（长按删除，与通知渠道页一致）
// 编辑：FormModal 内放单个 DisplayLinkEditor（entries 只有一条；onChange 取 [0] 作为草稿）
//   —— 或直接复用 DisplayLinkEditor 的多条编辑能力：新增时插入一条空草稿，保存时校验后 create
// 上传注入：uploadDisplayLinkTemplateImage
// 加载失败：内联错误 + 重试，禁止空态覆盖
```

- [ ] **Step 2:** 「我的」菜单「分销与推广」分组加入口（与「素材管理」并列）：

```tsx
        { label: '通用展示入口', icon: Images, onPress: () => router.push('/(tabs)/mine/display-link-templates') },
```

（`Images` 从 `lucide-react-native` 引入；`_layout.tsx` 内按现有 Stack 注册方式加 `display-link-templates` 屏幕，标题「通用展示入口」。）

- [ ] **Step 3:** `cd xianyu-mobile && npx tsc --noEmit` → 0 错误
- [ ] **Step 4:** 提交 `git commit -m "feat(mobile): 通用展示入口管理页"`

**App 端 3 轮审查测试优化**
- 第 1 轮：契约一致性（类型/字段与后端、与 Web 一致）；tsc；上传路径正确性；空态防覆盖
- 第 2 轮：交互与边界（图片选择取消、上传失败提示、超长文本、同名去重、模板列表为空、离线/超时）
- 第 3 轮：真机/模拟器验证（MuMu x86_64 构建安装）：商品编辑配图片入口 → 提卡页弹窗看图；素材编辑配置 → 发布回写验证；通用入口页增删改 + 默认开关生效
- 每轮产出问题清单 → 修复 → 复跑

---

# Phase 4 — 交付

- [ ] 后端/前端部署到服务器（同步 `common/`、`backend-web/app/`，重启 backend-web，`build_frontend.sh`）
- [ ] 新表 `xy_display_link_templates` 建表确认（服务启动自动建表）
- [ ] 脱敏扫描（无 IP/密码/账号 ID/sk key）
- [ ] 提交推送到 PR #325（Git Data API 方式，git push 被阻断）
- [ ] App 端随下次 APK 版本发布（本次不改版本号，除非用户要求）
