# 展示入口图片类型 + 通用展示入口模板 — 设计文档

日期：2026-09-25
状态：已确认（用户已批准设计）

## 背景与目标

买家提卡页（`AgreePickupPage`）底部的「展示入口」目前支持 `link`（外链）与 `text`（弹窗文本）两种类型，由卖家在商品级配置（`xy_catalog_items.metadata_json.display_links`）。

两个新需求：

1. **图片类型**：展示入口新增 `image` 类型，用于展示二维码类图片（如「QQ群」「微信群」入群码）。图片来源支持本地上传或外链，买家点击入口后弹窗查看大图。
2. **通用展示入口**：新增用户级的「通用展示入口」模板库，避免每个商品重复录入同一批入口；标记为「默认展示」的模板在提卡页读取时自动合并到所有商品，全店即时生效。

## 数据模型

### 展示入口条目（扩展第三种类型）

```
link:  {"name": str, "type": "link",  "url": str, "note": str?}
text:  {"name": str, "type": "text",  "title": str, "content": str}
image: {"name": str, "type": "image", "url": str, "note": str?}   ← 新增
```

- `image.url`：允许 `/static/uploads/display_links/...` 相对路径（本地上传）或 `http(s)://` 外链
- `image.note`：可选，入口右侧的说明文字（与 `link` 一致），如「扫码进群」
- 存储位置不变：`xy_catalog_items.metadata_json.display_links`（数组）

### 通用展示入口模板（新表）

```sql
CREATE TABLE IF NOT EXISTS xy_display_link_templates (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(16) NOT NULL,          -- link / text / image
    url VARCHAR(512) NULL,              -- link、image 用
    note VARCHAR(255) NULL,             -- link、image 用
    title VARCHAR(255) NULL,            -- text 用
    content TEXT NULL,                  -- text 用
    is_default TINYINT(1) NOT NULL DEFAULT 0,   -- 默认展示：读取时自动合并到所有商品
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_dlt_user_default (user_id, is_default)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
```

建表走 `ensure_*_schema` 幂等模式（参照 `common/db/auto_relist_schema.py`）。

## 后端接口契约（冻结）

所有接口按当前登录用户隔离（`resolve_owner_scope`），权限校验沿用现有模式。

### 1. 商品展示入口（现有接口，扩展校验）

- `GET /api/v1/items/{cookie_id}/{item_id}/display-links` → `{links: [...]}`
- `PUT /api/v1/items/{cookie_id}/{item_id}/display-links` body `{links: [...]}`（整体覆盖）
- 校验器 `_validate_display_links` 扩展：
  - 类型白名单 `link | text | image`
  - `image` 分支：`name` 必填（去空白非空）、`url` 必填且满足「以 `/static/` 开头」或「以 `http://` / `https://` 开头」、`note` 可选（非空才存）
  - 非法条目行为与现状一致：整个请求 400 并返回具体原因

### 2. 图片上传（新增，商品级）

- `POST /api/v1/items/{cookie_id}/{item_id}/display-links/upload-image`
- multipart，字段名 `image`；复用 `common/utils/local_image_upload.py::save_uploaded_image`
  - 仅 `image/*`、≤5MB、扩展名白名单 `{.jpg,.jpeg,.png,.gif,.webp,.bmp}`
  - 存储目录：`STATIC_ROOT/uploads/display_links/`，文件名 `{item_id}_{uuid}{ext}`
- 返回 `{success, message, data: {image_url: "/static/uploads/display_links/xxx.png"}}`

### 3. 通用展示入口模板（新增）

- `GET /api/v1/display-link-templates` → `{templates: [...]}`（按 id 升序）
- `POST /api/v1/display-link-templates` body `{name, type, url?, note?, title?, content?, is_default}` → 新建
- `PUT /api/v1/display-link-templates/{id}` body 同上；**部分更新语义**：只更新请求里显式提供的字段，未提供的保持原值；若 `type` 变更，按新类型重新校验并清空不适用的字段（如 text→image 时清空 title/content）
- `DELETE /api/v1/display-link-templates/{id}` → 删除
- `POST /api/v1/display-link-templates/upload-image` → 上传模板图片，返回 `{image_url}`（同一存储目录，文件名前缀 `tpl_{uuid}`）
- 条目校验复用与商品级相同的规则函数（单条校验抽成共享函数，避免两处逻辑漂移）；新建与更新都走该函数

### 4. 提卡页下发（现有接口，扩展合并逻辑）

- `GET /api/v1/agree-pickup/order?order_no=...` → `PickupOrderView.display_links`
- `agree_pickup_service._load_display_links` 变更：
  1. 读商品自身 `metadata_json.display_links`，按类型契约过滤（新增 image 分支：需 `url`）
  2. 查该商品 `owner_id` 名下 `is_default=1` 的模板
  3. 合并：商品自身条目在前，默认模板在后；**按名称去重**（`name.strip().lower()` 比较，商品自身优先）
  4. 模板条目按与商品条目相同的契约过滤后下发

## 前端（Web）

### 买家提卡页 `AgreePickupPage.tsx`

- 底部入口区新增 image 分支：渲染与 link/text 一致风格的按钮（名称 + 备注），点击打开弹窗
- 弹窗：标题为条目 `name`，内容为 `<img>`（`max-h-[70vh] object-contain` 居中，点击遮罩关闭），加载失败显示「图片加载失败」占位
- 类型定义 `frontend/src/api/itemQuery.ts` 扩展 `DisplayLinkImage` 并加入联合类型

### 商品配置弹窗 `ItemQueryConfigModal.tsx`（展示入口 tab）

- 类型下拉新增「图片」
- 图片分支表单：上传按钮（hidden `<input type="file">`，image/*、≤5MB）+ URL 输入框（上传后自动回填，也可手填外链）+ 缩略图预览 + 可选备注
- 新增「从通用入口添加」选择器：列出模板中名称尚未出现在当前草稿里的条目（带「默认」徽标），点击插入草稿（深拷贝）
- `LinkDraft` / `toDisplayLink` / `linkToDraft` 支持 image 类型

### 商品管理页 `Items.tsx`

- 工具栏新增「通用展示入口」按钮 → 新弹窗 `DisplayLinkTemplatesModal.tsx`
- 弹窗内容：模板列表（名称、类型徽标、「默认展示」开关、编辑、删除）+ 新增/编辑表单（字段与商品级图片/链接/文本一致，含图片上传）

## 移动端（App）

目标：手机端具备同等配置能力。

1. **`item-edit.tsx`**：新增「展示入口」折叠卡片（与现有「查询配置」卡片同构）
   - 条目列表增删改：类型选择（链接/文本/图片）
   - 图片：`expo-image-picker` 选图 → 走上传接口拿 `image_url`
   - 「从通用入口添加」选择器
   - 加载失败内联提示 + 重试，禁止空态保存覆盖服务端配置（沿用查询配置卡片模式）
2. **`material-edit.tsx`**：商品列表配置区加入 `display_links` 编辑（发布回写数据源）
3. **新页面 `app/(tabs)/mine/display-link-templates.tsx`**：通用展示入口管理（列表 + 默认开关 + 增删改 + 图片上传），在「我的」菜单「商品管理」分组加入口
4. **Wrappers**：`api/wrappers/item-query-config.ts` 增加 display links 读写 + 上传；新建 `api/wrappers/display-link-templates.ts`

## 部署

- 新表：`CREATE TABLE IF NOT EXISTS xy_display_link_templates`（幂等建表脚本随部署执行）
- 后端：同步 `common/`、`backend-web/app/` 后重启 `xianyu-backend-web`
- 前端：`build_frontend.sh` 构建 → `/opt/xianyu-auto-reply/dist`
- 移动端：随下次 APK 版本发布，本次不改版本号

## 测试策略

- 单元测试（pytest）：`_validate_display_links` 的 image 分支（合法相对路径/合法外链/缺 url/非法协议/缺 name）；模板条目校验复用同一函数；合并去重逻辑（重名去重、顺序、模板过滤）
- 前端：`tsc --noEmit` 0 错误
- 移动端：`tsc --noEmit` 0 错误
- 部署后真机验证：配置图片入口 → 提卡页弹窗看图；设置默认模板 → 未配置该条目的商品提卡页自动出现；删除模板 → 立即消失

## 范围外

- 商品级「排除某默认条目」的能力（如需排除，当前可通过同名覆盖实现；不做显式排除开关）
- 模板排序拖拽（按创建顺序展示）
- 移动端买家提卡页（提卡页为 Web 专属，App 不渲染）
