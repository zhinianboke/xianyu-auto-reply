# 卡券售罄自动下架 设计文档

日期：2026-09-12 ｜ 状态：已获用户确认方向（卡券级开关，默认关）

## 背景与目标

卡券（批量数据/卡密）卖空后商品仍挂在架上，买家拍下或同意提货后才发现发不出货。
目标：**统计待发货订单购买的卡券数量，当其总和 ≥ 卡券剩余库存时，自动下架该卡券绑定的所有商品**，防止超卖。

典型场景：一张库存 30 张的卡券绑定两个账号的商品；订单陆续进来，待发货订单数量累计达到 30 时，两个账号的商品同时下架。

## 现状（探索结论）

| 组件 | 事实 |
|---|---|
| 卡券库存 | `xy_cards.data_content` 剩余非空行数 = 批量数据卡库存；发货按行 CAS 消费。text/image 无库存概念；api 库存在外部系统 |
| 卡券-商品绑定 | `xy_card_item_relations`（多对多）+ legacy `xy_cards.item_id`（单绑） |
| 卡券匹配 | `CardMatcher.get_card_item_ids()`（卡→商品，仅 relations）、`get_all_cards_by_item_id()`（商品→卡，含 legacy 与多规格） |
| 订单 | `xy_orders.status` 待发货口径已有先例：`{"待发货","pending","paid","pending_ship"}`（order_service.py:446）；`quantity` 为购买数量 |
| 订单创建入口 | `common/services/order_service.py` 两处：同步创建(~L734) 与 详情同步(~L1376)，`add → commit` 后返回 |
| 下架通道 | `common/services/item_offline_service.py::batch_offline_items_from_xianyu(account_id, cookies_str, item_ids)`，返回含更新后 cookies |
| 通知 | `common/utils/notification_utils.py` 各渠道 sender（钉钉/飞书/Bark/邮件/webhook/微信/pushplus/telegram）；绑定表为 `xy_message_notifications` |
| 自动下架功能 | **不存在**（上游与本地均无） |

## 设计

### 范围

仅 **data（批量数据/卡密）类型卡券**生效。text/image/api 跳过（无本地库存或库存在外部）。
开关为**卡券级**：`xy_cards.auto_delist_on_soldout`（Boolean，默认 False，新增列）。

### 判断逻辑

对启用开关的 data 卡 C：

1. `stock = C.data_content` 非空行数（剩余库存）
2. `bound_items = relations(C.id) ∪ {C.item_id(legacy)}`
3. `pending_qty = Σ quantity`，范围：`xy_orders.item_id ∈ bound_items` 且 `status ∈ {待发货, pending, paid, pending_ship}`
4. 若 `pending_qty >= stock`（等于或超过即触发，按用户要求）→ 下架 `bound_items` 全部商品

商品绑多卡时，任一卡命中阈值即下架该商品（保守防超卖）。

### 触发点（双保险）

- **A. 下单入库后**：`order_service.py` 两处订单创建点 commit 成功后，对新订单的 `item_id` 反查绑定卡券（`CardMatcher.get_all_cards_by_item_id`），逐卡执行检查
- **B. 发货完成后**：data 卡库存被消费至 0 时兜底——`websocket/app/api/routes/internal.py` 批量发货循环结束后、`common/services/agree_pickup_delivery.py` 提货发货成功后，对该卡执行 `delist_if_empty`

两触发点共用一个服务函数，行为幂等：已下架商品重复下架接口报错仅记日志。

### 下架执行

1. 商品按所属账号分组（`xy_catalog_items.item_id → account_pk → xy_accounts`），各账号只下架自己名下商品
2. 每账号调用 `batch_offline_items_from_xianyu`；返回的新 cookies 回写 `xy_accounts.cookie`
3. 下架成功 → 通知渠道告警（复用 message_notification 绑定 + notification_utils，失败不阻塞）
4. 全部动作 try/except 包裹：检查/下架/通知的任何异常只记日志，**绝不影响下单与发货主流程**

### 不做的事（YAGNI）

- 不做自动重新上架（项目无上架接口；补货后卖家手动上架，避免反复抖动）
- 不做 api/对接卡券的售罄下架（外部库存本期不可知）
- 不改 delivery_content / 发货流程本身的任何行为

### API 与界面

- `backend-web/app/api/routes/cards.py`：`CardCreate` / `CardUpdate` 增加 `auto_delist_on_soldout?: bool`；列表/详情响应透出该字段；`card_service.update_card` 透传
- Web 端卡券新建/编辑弹窗：data 类型卡券显示「售罄自动下架」开关（默认关），附说明文案
- 移动端暂不加开关（后端字段已就绪，后续版本接入）

### 数据库变更

```sql
ALTER TABLE xy_cards ADD COLUMN auto_delist_on_soldout TINYINT(1) NOT NULL DEFAULT 0 COMMENT '售罄自动下架开关';
```

## 测试与验证

1. 服务器实测（用户 30 库存卡）：开启开关 → 人工核查统计值（SQL 验证 pending_qty 与库存）→ 模拟达到阈值（构造测试订单或直接触发检查函数）→ 观察两个账号商品下架 + 通知送达 + 日志
2. 字段回读：GET 卡券详情返回开关字段；PUT 更新生效
3. 回归：未开开关的卡券行为不变；text/image/api 卡不受任何影响
