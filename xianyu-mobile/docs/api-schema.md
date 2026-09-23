# 闲鱼管家 API Schema 对照文档

> 维护参考：各写操作接口（POST/PUT/PATCH/DELETE-with-body）的请求体/查询参数 schema。
> 数据来源：全量扫描 103 个写操作接口 curl 验证 + web 前端 `xianyu-auto-reply/frontend/src/types` 类型定义。
> 更新日期：2026-09-07

## 通用约定

- **响应包裹**：所有响应为 `{success: boolean, message: string, data: T | null}`。部分接口（数据分析）**双层包裹**：外层 `{success, message, data:{code, data:{真实数据}}}`——wrapper 需递归解包（见 `api/wrappers/dashboard.ts` 的 `unwrapData`）。
- **错误**：HTTP 非 2xx 时 wrapper 的 `client` onResponse 拦截器读 `body.message`/`body.detail` 抛 `ApiError`；422 的 `detail:[{loc,msg}]` 指明缺哪个字段。
- **认证**：除登录/注册/发验证码外，均需 `Authorization: Bearer <token>` 头。
- **字段命名**：路径参数与多数 body 用 **snake_case**；个别聊天接口用 **camelCase**（见下表“备注”）。修改接口前务必对照本表，勿凭惯性写 `{enabled}`。

## 账号 / Cookie（`api/wrappers/accounts.ts`）

| 方法 | 路径 | body/query | 备注 |
|---|---|---|---|
| GET | `/api/v1/cookies/options` | — | 返回 `[{pk, id, enabled, remark, show_browser}]`，**account_id 用 pk(整数)** 调业务接口，用 id(字符串) 调聊天接口 |
| GET | `/api/v1/cookies/details/paginated` | query `{page, page_size}` | |
| PUT | `/api/v1/cookies/{id}/status` | body `{enabled: bool}` | 切账号启用状态 |
| PUT | `/api/v1/cookies/{id}/remark` | body `{remark: str}` | |
| DELETE | `/api/v1/cookies/{id}` | — | |
| PUT | `/api/v1/cookies/{id}/{toggle-path}` | body **`{[ToggleKey]: bool}`**（字段名=ToggleKey，如 `auto_confirm`） | toggle-path: auto-confirm/auto-polish/auto-red-flower/scheduled-redelivery/scheduled-rate/confirm-before-send/send-before-confirm/only-send-card/ai-reply-block-ordered-users |
| PUT | `/api/v1/cookies/status/batch` | body `{account_ids: str[], enabled: bool}` | |
| PUT | `/api/v1/cookies/clear-token-cache/batch` | body `{account_ids: str[]}` | |
| PUT | `/api/v1/cookies/close-notice/batch` | body `{account_ids: str[]}` | |
| POST | `/api/v1/cookies/renew-login` | body **直接是 `str[]` 数组**（非 `{account_ids}`） | |
| POST | `/api/v1/cookies/export` | — | |
| POST | `/api/v1/cookies/import` | body 文件 | |
| PUT | `/api/v1/cookies/{id}/delivery-block-rules` | body `{rules: [{rule_code, enabled}]}` | |

## 聊天（`api/wrappers/chat.ts`）

| 方法 | 路径 | body | 备注 |
|---|---|---|---|
| GET | `/api/v1/chat-new/accounts` | — | |
| POST | `/api/v1/chat-new/connect/{accountId}` | — | accountId=id |
| POST | `/api/v1/chat-new/disconnect/{accountId}` | — | |
| POST | `/api/v1/chat-new/send-message/{accountId}` | body `{cid, toUserId, text}` | **camelCase** |
| POST | `/api/v1/chat-new/recall-message/{accountId}` | body **`{messageId, messageTime}`** | **camelCase（非 message_id）** |
| POST | `/api/v1/chat-new/send-image/{accountId}` | multipart | |
| GET | `/api/v1/chat-new/conversations/{accountId}` | query `{cursor}` | 游标分页 |
| GET | `/api/v1/chat-new/messages/{accountId}/{cid}` | query `{cursor}` | 游标分页，返回 messages 倒序 |
| POST | `/api/v1/chat-new/quick-phrases` | body `{title, content, sort_order: 0}` | |
| PUT | `/api/v1/chat-new/quick-phrases/{id}` | body `{title, content, sort_order: 0}` | |
| DELETE | `/api/v1/chat-new/quick-phrases/{id}` | — | |
| POST | `/api/v1/chat-new/official-blacklist/{accountId}/{cid}/{action}` | — | action=block/unblock |

## 订单（`api/wrappers/orders.ts` / `orders-tab.ts`）

| 方法 | 路径 | body | 备注 |
|---|---|---|---|
| GET | `/api/v1/orders` | query `{page, page_size, status?, account_id?}` | |
| POST | `/api/v1/orders/fetch-xianyu` | body `{cookie_id: str}` | 同步闲鱼订单，可能数分钟，调用方加 `withTimeout` |
| POST | `/api/v1/orders/cancel` | body `{order_no: str}` | |
| POST | `/api/v1/orders/no-logistics-delivery` | body `{order_no: str}` | |
| POST | `/api/v1/orders/manual-delivery` | body `{order_no: str}` | |
| GET | `/api/v1/agree-deliver/{accountId}` | — | 同意后发货配置 |
| PUT | `/api/v1/agree-deliver/{accountId}` | body 配置对象 | accountId 需 `encodeURIComponent` |
| POST | `/api/v1/agree-pickup/agree` | body `{order_no, order_id}` | |
| GET | `/api/v1/agree-pickup` | — | 公网提货页 |

## 商品 / 改价（`api/wrappers/item-edit.ts` / `products.ts`）

| 方法 | 路径 | body | 备注 |
|---|---|---|---|
| PUT | `/api/v1/items/{cookieId}/{itemId}/price` | body `{price}` | cookieId/itemId 需 `encodeURIComponent` |
| PUT | `/api/v1/items/{cookieId}/{itemId}/seller-edit` | body 编辑字段 | |
| POST | `/api/v1/items/batch-delete-xianyu` | body **`{cookie_id, item_ids: str[]}`** | **非** `/items/{id}/batch-delete` |
| GET | `/api/v1/items/paginated` | query | 商品列表 |

## 搜索（`api/wrappers/search.ts`）

| 方法 | 路径 | body | 备注 |
|---|---|---|---|
| POST | `/api/v1/compass/goofish/search` | body **`{keyword, page, account_id: int(pk)}`** | account_id 必填，缺则 422；响应 `{success, data:{items, total}}` |
| POST | `/api/v1/search/items` | body `{keyword}` | 本地库搜索 |

## 消息过滤（`api/wrappers/message-filters.ts`）

| 方法 | 路径 | body | 备注 |
|---|---|---|---|
| GET | `/api/v1/message-filters` | query `{account_id?}` | |
| POST | `/api/v1/message-filters` | body **`{keyword: str, filter_types: FilterType[], account_id: str}`** | FilterType ∈ `skip_reply`/`skip_notify`（非 keyword/regex/user_id） |
| PUT | `/api/v1/message-filters/{id}` | body `{keyword?, filter_type?, enabled?}` | **update 用 filter_type 单数**（create 用复数） |
| DELETE | `/api/v1/message-filters/{id}` | — | |
| PUT | `/api/v1/message-filters/{id}/toggle` | — | |

## 黑名单（`api/wrappers/blacklist-manage.ts`）

| 方法 | 路径 | body | 备注 |
|---|---|---|---|
| GET | `/api/v1/blacklist/personal` | — | |
| POST | `/api/v1/blacklist/personal` | body `{buyer_ids: str, reason?, account_id?, is_enabled: true}` | |
| DELETE | `/api/v1/blacklist/personal/{recordId}` | — | |
| POST | `/api/v1/blacklist/personal/batch-delete` | body **`{ids: int[]}`** | **非 record_ids** |

## 反馈（`api/wrappers/misc.ts`）

| 方法 | 路径 | 参数 | 备注 |
|---|---|---|---|
| GET | `/api/v1/feedbacks` | query `{page, page_size}` | |
| POST | `/api/v1/feedbacks` | **query** `{title, content, feedback_type}` | **query 非 body**；feedback_type ∈ `FEATURE`/`BUG`/`OTHER` |
| GET | `/api/v1/feedbacks/{id}` | — | 含对话消息 |
| POST | `/api/v1/feedbacks/{id}/reply` | body `{reply: str}` | |
| PUT | `/api/v1/feedbacks/{id}/resolve` | — | |
| DELETE | `/api/v1/feedbacks/{id}` | — | |

## 公告 / 广告 / 反馈

| 方法 | 路径 | body | 备注 |
|---|---|---|---|
| POST | `/api/v1/announcements` | body `{title, content}` | |
| PUT | `/api/v1/announcements/{id}` | body `{title, content}` | |
| DELETE | `/api/v1/announcements/{id}` | — | |

## 分销（`api/wrappers/distribution.ts`）

| 方法 | 路径 | body | 备注 |
|---|---|---|---|
| POST | `/api/v1/distribution/dock-records` | body `{card_id: int, dock_name: str, markup_amount?: str, remark?}` | **markup_amount 是 string** |
| POST | `/api/v1/distribution/sub-dock-records` | body `{parent_dock_id: int, dock_name: str, markup_amount?: str, remark?}` | |

## 通知渠道 / 消息通知绑定（`api/wrappers/notifications.ts`）

| 方法 | 路径 | body | 备注 |
|---|---|---|---|
| GET | `/api/v1/notification-channels` | — | |
| POST | `/api/v1/notification-channels` | body `{name, type, config, enabled: true}` | |
| PUT | `/api/v1/notification-channels/{id}` | body 编辑字段 | |
| DELETE | `/api/v1/notification-channels/{id}` | — | |
| POST | `/api/v1/notification-channels/{id}/test` | — | |
| GET | `/api/v1/message-notifications` | — | 返回 {cookieId: [binding]} 映射 |
| POST | **`/api/v1/message-notifications/{accountId}`** | body `{channel_id: int, enabled: bool}` | **路径带 accountId，非 root**；body 不含 account_id |
| PUT | `/api/v1/message-notifications/{id}` | body `{enabled}` | |
| DELETE | `/api/v1/message-notifications/{id}` | — | |

## 监控 / 上下架（`api/wrappers/monitor.ts`）

| 方法 | 路径 | body | 备注 |
|---|---|---|---|
| GET/POST/PUT/DELETE | `/api/v1/product-monitor/categories[/{id}]` | body `{name}` (POST/PUT) | |
| POST | `/api/v1/product-monitor/listing-tasks` | body `{monitor_type, category_id, keyword, interval_minutes, price_min?, price_max?, is_enabled?}` | |
| PUT | `/api/v1/product-monitor/listing-tasks/{taskId}/status` | body `{is_enabled: bool}` | |
| POST | `/api/v1/product-monitor/listing-tasks/{taskId}/run` | — | |
| POST | `/api/v1/product-monitor/listing-tasks/batch-delete` | body `{ids: int[]}` | |
| DELETE | `/api/v1/product-monitor/listing-tasks/logs/clear` | — | |
| PUT | `/api/v1/product-monitor/fallback-config` | body `{category_id, account_ids}` | |

## 卡券（`api/wrappers/cards.ts`）

| 方法 | 路径 | body | 备注 |
|---|---|---|---|
| POST | `/api/v1/cards` | body `{name, type:'text', text_content, description?, use_no_logistics_form?}` | |
| PUT | `/api/v1/cards/{cardId}` | body 同上 | |
| DELETE | `/api/v1/cards/{cardId}` | — | |

## 数据分析（`api/wrappers/dashboard.ts`）

| 方法 | 路径 | body | 备注 |
|---|---|---|---|
| POST | `/api/v1/data-analysis/browse-summary` | body `{account_id: int(pk), date_type:'customDate', date_range:'YYYYMMDD\|YYYYMMDD'}` | **双层包裹**，需递归 unwrapData |
| POST | `/api/v1/data-analysis/seller-summary` | 同上 | |

## 用户管理 / 充值提现 / 系统（`api/wrappers/admin.ts` / `settings.ts`）

| 方法 | 路径 | body | 备注 |
|---|---|---|---|
| POST | `/api/v1/admin/users` | body `{username, email, password, role}` | **role ∈ `ADMIN`/`OPERATOR`/`MEMBER`**（大写，非 user/admin） |
| PUT | `/api/v1/admin/users/{userId}` | body 编辑字段 | |
| DELETE | `/api/v1/admin/users/{userId}` | — | |
| POST | `/api/v1/admin/users/{userId}/recharge` | body `{amount: str}` | amount 是 string |
| POST | `/api/v1/users/change-password` | body `{current_password, new_password}` | |
| POST | `/api/v1/payment/recharge` | body `{amount: str}` | amount 是 string |
| POST | `/api/v1/payment/withdraw` | body `{amount: str, payment_method: str}` | |
| PUT | `/api/v1/system-settings/{key}` | body `{value}` | key 需 `encodeURIComponent` |
| PUT | `/api/v1/auto-rate/{accountId}` | body `{enabled, rate_type, text_content, api_url?}` | |
| POST | `/api/v1/auto-rate/batch-rate` | body `{account_ids: str[]}` | |
| PUT | `/api/v1/confirm-receipt-messages/{accountId}` | body `{enabled, message_content, message_image}` | |

## 认证（`api/wrappers/auth.ts`）

| 方法 | 路径 | body | 备注 |
|---|---|---|---|
| POST | `/api/v1/auth/login` | body `{username, password, geetest_challenge?}` | 返回 `{token, refresh_token}` |
| POST | `/api/v1/auth/login` | body `{email, password, geetest_challenge?}` | 邮箱登录 |
| POST | `/api/v1/auth/login` | body `{email, verification_code, email_session_id}` | 验证码登录 |
| POST | `/api/v1/auth/register` | body `{username, email, password, verification_code, session_id}` | |
| POST | `/api/v1/auth/reset-password` | body `{email, verification_code, new_password}` | |
| POST | `/api/v1/auth/logout` | — | |
| POST | `/api/v1/captcha/send-email-code` | body `{email, type}` | type ∈ register/login/reset 等 |
| POST | `/api/v1/geetest/validate` | body `{challenge, validate, seccode}` | |
| POST | `/api/v1/qr-login/generate` | — | 返回 session_id + qr_url |
| GET | `/api/v1/qr-login/status/{sessionId}` | — | 轮询扫码状态 |

## 常见 422 陷阱速查

1. **缺 account_id**：搜索、消息过滤等接口要求 account_id（用 cookie 的 pk 整数 或 id 字符串，按接口而定）。
2. **字段名=ToggleKey**：账号功能开关 body 字段名是 `auto_confirm` 等 ToggleKey，不是 `enabled`。
3. **camelCase vs snake_case**：聊天 recall-message 用 `messageId`/`messageTime`（驼峰），其余多用 snake。
4. **query vs body**：反馈 create 用 query 参数（title/content/feedback_type），非 body。
5. **双层包裹**：数据分析响应双层 `{success, data:{code, data}}`，需递归解包。
6. **金额是 string**：充值/提现/分销加价 amount 是字符串，不是数字。
7. **枚举大小写**：role 是 `ADMIN`/`OPERATOR`/`MEMBER`（大写）；feedback_type 是 `FEATURE`/`BUG`/`OTHER`；filter_type 是 `skip_reply`/`skip_notify`。
8. **路径带参数**：消息通知绑定 POST 到 `/{accountId}` 非 root；商品批量删除是 `/items/batch-delete-xianyu`。
