# 素材库配置联动 + 采集初始化 + 发布回写 设计文档

日期：2026-09-12 ｜ 状态：已获用户确认（单JSON字段/一步到位全回写/采集入口在素材编辑页/含移动端）

## 目标

让「素材库」成为一个完整的「可发布 + 已配置」模板：素材携带商品列表配置（多规格/多数量发货/关联卡券/默认回复/AI提示/查询配置）；新增「采集」功能从已有商品列表项一键初始化素材配置；单品/批量发布成功后把素材配置一步到位回写到新商品列表项。

## 现状（探索结论）

| 组件 | 事实 |
|---|---|
| 素材库 `xy_product_materials` | 富发布素材（标题/价格/分类/图片/规格/sku/数量/运费…），**不携带**商品列表配置 |
| 商品列表 `xy_catalog_items` | `ai_prompt` 列 + `metadata_json`（`multi_quantity_delivery`/`query_buttons`） |
| 关联卡券 | `xy_card_item_relations`（card_id ↔ item_id，多对多） |
| 默认回复 | `xy_default_replies`（account_id + item_id + reply_content + enabled） |
| 卡券绑定工具 | `CardMatcher.batch_bind_cards_to_items` / `delete_relations_by_item_id` |
| 查询按钮配置弹窗 | `frontend/src/pages/items/ItemQueryConfigModal.tsx`（可复用） |
| 发布成功点 | `publish_execution_service.py` 的 `log.item_id`（单品 L405/469）；批量发布循环同文件 |
| 素材前端页 | `frontend/src/pages/product-publish/` |
| 移动端素材 | `xianyu-mobile/app/(tabs)/mine/` 下（需新增/扩展素材管理页） |

## 设计

### A. 数据模型

`xy_product_materials` 加一个 JSON 列 `item_config`，形状镜像商品列表配置：

```json
{
  "multi_quantity_delivery": false,
  "card_ids": [21, 22],
  "default_reply": "亲，已发货请注意查收～",
  "ai_prompt": "你是闲鱼客服…",
  "query_buttons": [{"name":"查余额","method":"GET","url":"…","headers":{…},"success_path":"code","success_value":"0","result_fields":[…]}]
}
```

迁移：`ALTER TABLE xy_product_materials ADD COLUMN item_config JSON`

### B. 采集（后端 + Web + 移动）

后端新 API：`GET /api/v1/materials/collect-from-item/{item_id}`
- 返回从该商品列表项采集出的素材草稿（标题/价格/图片/规格 + 完整 `item_config`）
- 配置来源拼装：
  - `ai_prompt` ← `xy_catalog_items.ai_prompt`
  - `multi_quantity_delivery` / `query_buttons` ← `xy_catalog_items.metadata_json`
  - `card_ids` ← `xy_card_item_relations`（该 item 已绑卡券）
  - `default_reply` ← `xy_default_replies`（account_id + item_id 命中，取 reply_content）
- 入口：素材编辑页加「从商品列表采集」按钮（Web + 移动），弹选商品 → 填充表单含配置区

### C. 素材编辑页配置区（Web + 移动）

素材表单新增「商品列表配置」区块：
- 多数量发货（开关）
- 关联卡券（多选，复用卡券选择）
- 默认回复（文本域）
- AI 提示（文本域）
- 查询按钮（复用 `ItemQueryConfigModal`）
- 提交时一并存入 `material.item_config`

### D. 发布回写（一步到位）

新服务 `common/services/material_config_writer.py`：`async def apply_to_item(session, material, account_id, item_id)`
- 创建/更新 `xy_catalog_items` 行（title/price/ai_prompt 列 + metadata 写 `multi_quantity_delivery`/`query_buttons`）
- 卡券绑定：`delete_relations_by_item_id(item_id)` → `batch_bind_cards_to_items(cfg.card_ids, [item_id])`
- 默认回复：upsert `xy_default_replies`(account_id, item_id, reply_content=cfg.default_reply, enabled=True)
- 幂等：已存在则更新；任何子步骤失败仅记日志，不回滚发布结果

挂钩点：`publish_execution_service.py` 发布成功拿到 `log.item_id` 后调用（单品）；批量发布循环里每个素材各自调用各自的 `item_config`。

### E. 不做（YAGNI）

- 不改闲鱼发布接口调用本身
- 不做素材↔商品双向实时同步（采集是单向快照）
- 保留商品列表手动配置入口不动

### F. 验证

- 后端：`material_config_writer` 单元测试（mock DB：catalog/card/default_reply 三处落库 + 幂等）
- Web：`tsc` 构建；素材编辑页配置区 + 采集按钮交互手测
- 移动：`tsc` 构建；素材页配置区 + 采集入口手测
- 发布回写端到端：造测试素材发布，确认 catalog/card/default_reply 三处自动就位（部署后做，本期不部署）

## 任务并行性

- 后端（模型+迁移+采集API+回写服务+发布挂钩）—— 链式，单线
- Web（素材编辑页配置区 + 采集按钮 + API 封装）—— 依赖后端 API 契约，可与后端并行（按契约先行）
- 移动（素材页配置区 + 采集入口 + API 封装）—— 依赖后端 API 契约，可与 Web 并行
三条线可并行，后端是关键路径。
