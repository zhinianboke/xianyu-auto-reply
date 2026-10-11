# 卡券售罄自动下架 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 待发货订单购买的卡券数量总和 ≥ 卡券剩余库存时，自动下架该卡券绑定的所有商品（卡券级开关，仅 data 批量数据卡）。

**Architecture:** 新服务 `common/services/stock_guard_service.py` 统一实现检查+下架+通知；`order_service.py` 两处订单创建点与两处发货完成点调用它；下架复用 `batch_offline_items_from_xianyu`；通知复用 `notification_utils` 各渠道 sender。

**Tech Stack:** FastAPI / SQLAlchemy async (MySQL) / React+Vite 前端 / systemd 三服务部署（backend-web 8095、websocket 8093、scheduler）

## Global Constraints

- 待发货状态口径（与 order_service.py:446 一致）：`{"待发货", "pending", "paid", "pending_ship"}`
- 仅 `card.type == 'data'` 生效；text/image/api 一律跳过
- 阈值：`pending_qty >= stock`（等于即触发）
- 全部钩子必须 try/except 包裹，任何异常只记日志，不影响下单/发货主流程
- 开关字段：`xy_cards.auto_delist_on_soldout`（Boolean 默认 False）
- 绑定口径：`xy_card_item_relations` ∪ legacy `xy_cards.item_id`
- 不做自动重新上架；不做 api/对接卡券售罄下架

---

### Task 1: 数据模型与迁移

**Files:**
- Modify: `common/models/card.py:39` 附近（`is_dockable` 字段后）
- Modify: `common/db/init_database.py`（卡券表新增列的迁移清单，仿照 L2002 模式）
- Test: 无单测（无 async 测试基建）；以服务器 `DESC xy_cards` 验证

- [ ] **Step 1: Card 模型加字段**

在 `common/models/card.py` 的 `is_dockable` 字段定义之后添加：

```python
    auto_delist_on_soldout: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0",
        comment="售罄自动下架开关（待发货订单数量≥剩余库存时自动下架绑定商品，仅data类型生效）",
    )
```

- [ ] **Step 2: init_database.py 迁移清单加列**

在 `common/db/init_database.py` 中 `xy_cards` 表对应的“补列”元组列表里（仿 L2002 `("seller_fill_status", ..., "detail_json")` 的模式），追加：

```python
            ("auto_delist_on_soldout", "TINYINT(1) NOT NULL DEFAULT 0 COMMENT '售罄自动下架开关'", "is_dockable"),
```

- [ ] **Step 3: Commit**

```bash
git add common/models/card.py common/db/init_database.py
git commit -m "feat(stock-guard): xy_cards新增售罄自动下架开关字段"
```

---

### Task 2: stock_guard_service 核心服务

**Files:**
- Create: `common/services/stock_guard_service.py`
- Consumes: `common/models/card.py`（Task 1 的字段）、`common/services/item_offline_service.py::batch_offline_items_from_xianyu`、`common/services/card_matcher.py::CardMatcher.get_card_item_ids`、`common/utils/notification_utils.py` 各 sender、`common/models/notification_channel.py`
- Produces（后续任务依赖的确切签名）:
  - `async def check_card_and_delist(session: AsyncSession, card_id: int, *, trigger: str) -> dict` — 返回 `{"checked": bool, "delisted": list[str], "reason": str}`
  - `async def check_item_cards_after_order(session: AsyncSession, item_id: str, *, trigger: str) -> None`
  - `async def delist_card_if_empty(session: AsyncSession, card_id: int, *, trigger: str) -> None`

**Interfaces:**
- Consumes: `CardMatcher(session).get_card_item_ids(card_id) -> list[str]`；`batch_offline_items_from_xianyu(account_id: str, cookies_str: str, item_ids: list[str]) -> dict`（返回含 `results`/`cookies_str`）
- Produces: 上述 3 个公开函数

- [ ] **Step 1: 创建服务文件**

`common/services/stock_guard_service.py` 完整内容：

```python
"""卡券售罄自动下架守卫（stock guard）

触发语义：
- 对待发货订单（status ∈ {"待发货","pending","paid","pending_ship"}）按 quantity 求和，
  当总和 ≥ 卡券剩余库存（data_content 非空行数）时，自动下架该卡券绑定的所有商品。
- 仅 data（批量数据）类型且开启 auto_delist_on_soldout 的卡券生效。
- 所有入口函数均为尽力而为：任何异常只记日志，绝不抛出影响主流程。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.card import Card
from common.models.notification_channel import NotificationChannel
from common.models.xy_account import XYAccount
from common.models.xy_catalog_item import XYCatalogItem
from common.models.xy_order import XYOrder
from common.services.card_matcher import CardMatcher
from common.services.item_offline_service import batch_offline_items_from_xianyu

PENDING_STATUSES = ("待发货", "pending", "paid", "pending_ship")


def _count_stock(card: Card) -> int:
    """data 卡剩余库存 = data_content 非空行数"""
    if not card.data_content:
        return 0
    return len([ln for ln in card.data_content.split("\n") if ln.strip()])


async def _pending_quantity(session: AsyncSession, item_ids: List[str]) -> int:
    if not item_ids:
        return 0
    stmt = select(func.coalesce(func.sum(XYOrder.quantity), 0)).where(
        XYOrder.item_id.in_(item_ids),
        XYOrder.status.in_(PENDING_STATUSES),
    )
    result = await session.execute(stmt)
    return int(result.scalar() or 0)


async def _bound_item_ids(session: AsyncSession, card: Card) -> List[str]:
    ids = await CardMatcher(session).get_card_item_ids(card.id)
    if card.item_id and card.item_id not in ids:  # legacy 单绑
        ids.append(card.item_id)
    return ids


async def _delist_items(session: AsyncSession, item_ids: List[str], card: Card) -> Dict[str, List[str]]:
    """按商品所属账号分组下架，返回 {"success": [...], "failed": [...]}"""
    result = {"success": [], "failed": []}
    if not item_ids:
        return result
    stmt = select(XYCatalogItem.item_id, XYAccount).join(
        XYAccount, XYAccount.id == XYCatalogItem.account_pk
    ).where(XYCatalogItem.item_id.in_(item_ids))
    rows = (await session.execute(stmt)).all()
    by_account: Dict[int, Dict[str, Any]] = {}
    for item_id, account in rows:
        slot = by_account.setdefault(account.id, {"account": account, "items": []})
        slot["items"].append(item_id)
    missing = [i for i in item_ids if i not in {r[0] for r in rows}]
    if missing:
        logger.warning(f"[售罄下架] 以下商品不在商品库，跳过下架: {missing}")
        result["failed"].extend(missing)
    for slot in by_account.values():
        account: XYAccount = slot["account"]
        try:
            resp = await batch_offline_items_from_xianyu(
                account.account_id, account.cookie, slot["items"]
            )
            new_cookie = resp.get("cookies_str")
            if new_cookie and new_cookie != account.cookie:
                account.cookie = new_cookie
                await session.commit()
            for r in resp.get("results") or []:
                (result["success"] if r.get("success") else result["failed"]).append(r.get("item_id", ""))
            logger.info(
                f"[售罄下架] 卡券{card.id}({card.name}) 账号{account.account_id} 下架: "
                f"{resp.get('message')}"
            )
        except Exception as e:
            logger.error(f"[售罄下架] 账号{account.account_id} 下架异常: {e}")
            result["failed"].extend(slot["items"])
    return result


async def _notify_owner(session: AsyncSession, owner_id: int, message: str) -> None:
    """向用户所有启用的通知渠道发送告警（失败静默）"""
    try:
        channels = (
            await session.execute(
                select(NotificationChannel).where(
                    NotificationChannel.owner_id == owner_id,
                    NotificationChannel.enabled == True,  # noqa: E712
                )
            )
        ).scalars().all()
        if not channels:
            return
        from common.utils.notification_utils import (
            parse_notification_config, send_bark_notification, send_dingtalk_notification,
            send_email_notification, send_feishu_notification, send_pushplus_notification,
            send_telegram_notification, send_webhook_notification, send_wechat_notification,
        )
        for ch in channels:
            try:
                cfg = parse_notification_config(ch.config_payload)
                t = ch.channel_type
                if t in ("ding_talk", "dingtalk"):
                    await send_dingtalk_notification(cfg, message)
                elif t in ("feishu", "lark"):
                    await send_feishu_notification(cfg, message)
                elif t == "bark":
                    await send_bark_notification(cfg, message)
                elif t == "email":
                    await send_email_notification(cfg, message, None)
                elif t == "webhook":
                    await send_webhook_notification(cfg, message)
                elif t in ("wechat", "wechat_work"):
                    await send_wechat_notification(cfg, message)
                elif t == "pushplus":
                    await send_pushplus_notification(cfg, message)
                elif t == "telegram":
                    await send_telegram_notification(cfg, message)
            except Exception as e:
                logger.warning(f"[售罄下架] 通知渠道 {ch.id}({ch.channel_type}) 发送失败: {e}")
    except Exception as e:
        logger.warning(f"[售罄下架] 通知发送异常: {e}")


async def check_card_and_delist(
    session: AsyncSession, card_id: int, *, trigger: str
) -> Dict[str, Any]:
    """对单张卡执行售罄检查并按需下架。任何路径都不抛异常。"""
    try:
        card = (
            await session.execute(select(Card).where(Card.id == card_id))
        ).scalars().first()
        if not card or not card.enabled:
            return {"checked": False, "delisted": [], "reason": "card_missing_or_disabled"}
        if card.type != "data":
            return {"checked": False, "delisted": [], "reason": f"type_{card.type}_skipped"}
        if not card.auto_delist_on_soldout:
            return {"checked": False, "delisted": [], "reason": "switch_off"}

        stock = _count_stock(card)
        item_ids = await _bound_item_ids(session, card)
        pending = await _pending_quantity(session, item_ids)
        logger.info(
            f"[售罄下架] 检查 卡券{card.id}({card.name}) trigger={trigger} "
            f"stock={stock} pending={pending} items={item_ids}"
        )
        if pending < stock:
            return {"checked": True, "delisted": [], "reason": "below_threshold"}

        delist_result = await _delist_items(session, item_ids, card)
        ok_items = delist_result["success"]
        if ok_items:
            await _notify_owner(
                session, card.user_id,
                f"【售罄自动下架】卡券「{card.name}」库存{stock}张，待发货订单共{pending}张，"
                f"已达售罄阈值，已自动下架{len(ok_items)}个商品：{','.join(ok_items)}",
            )
        return {"checked": True, "delisted": ok_items, "failed": delist_result["failed"],
                "reason": "threshold_hit"}
    except Exception as e:
        logger.error(f"[售罄下架] check_card_and_delist({card_id}, {trigger}) 异常: {e}")
        return {"checked": False, "delisted": [], "reason": f"error:{e}"}


async def check_item_cards_after_order(
    session: AsyncSession, item_id: str, *, trigger: str
) -> None:
    """下单入库后：对该商品绑定的所有卡券执行检查。"""
    if not item_id:
        return
    try:
        matcher = CardMatcher(session)
        cards = await matcher.get_all_cards_by_item_id(item_id)
        for c in cards or []:
            cid = c.get("id") if isinstance(c, dict) else getattr(c, "id", None)
            if cid:
                await check_card_and_delist(session, int(cid), trigger=trigger)
    except Exception as e:
        logger.error(f"[售罄下架] check_item_cards_after_order({item_id}, {trigger}) 异常: {e}")


async def delist_card_if_empty(
    session: AsyncSession, card_id: int, *, trigger: str
) -> None:
    """发货完成后：data 卡库存归零时兜底下架（复用同一检查，stock=0 时 0>=0 必命中）。"""
    try:
        await check_card_and_delist(session, card_id, trigger=trigger)
    except Exception as e:
        logger.error(f"[售罄下架] delist_card_if_empty({card_id}, {trigger}) 异常: {e}")
```

- [ ] **Step 2: 语法检查**

```bash
python -m py_compile common/services/stock_guard_service.py
```

预期：无输出（编译通过）

- [ ] **Step 3: Commit**

```bash
git add common/services/stock_guard_service.py
git commit -m "feat(stock-guard): 售罄检查与自动下架核心服务"
```

---

### Task 3: 订单创建钩子（触发点 A）

**Files:**
- Modify: `common/services/order_service.py`（`create_order_from_message` ~L745 的 commit 后；`_upsert_order` ~L1386 的 `self.session.add(new_order)` + commit 后）

**Interfaces:**
- Consumes: Task 2 的 `check_item_cards_after_order(session, item_id, trigger=...)`

- [ ] **Step 1: `create_order_from_message` 挂钩**

在 `new_order` commit 成功、即将 `return True` 之前（L745-747 区域）插入：

```python
            self.session.add(new_order)
            await self.session.commit()
            logger.info(f"订单 {order_no} 创建成功")
            # 售罄守卫：新订单计入待发货后检查该商品绑定卡券（异常不影响下单）
            from common.services.stock_guard_service import check_item_cards_after_order
            await check_item_cards_after_order(self.session, item_id or "", trigger="order_create_msg")
            return True
```

- [ ] **Step 2: `_upsert_order` 挂钩**

在 else 分支 `self.session.add(new_order)` 之后的 commit 后（创建新订单路径、`return 'created'` 之前）插入同样两行（trigger 用 `"order_create_sync"`）。需先 Read `_upsert_order` 的 1376-1400 确认准确插入点。

- [ ] **Step 3: 语法检查 + Commit**

```bash
python -m py_compile common/services/order_service.py
git add common/services/order_service.py
git commit -m "feat(stock-guard): 订单创建两处入口接入售罄守卫"
```

---

### Task 4: 发货完成钩子（触发点 B）

**Files:**
- Modify: `websocket/app/api/routes/internal.py`（批量发货消费循环结束后、构建响应前，约 L2050-2060）
- Modify: `common/services/agree_pickup_delivery.py`（成功落库 commit 后，约 L160-170）

**Interfaces:**
- Consumes: Task 2 的 `delist_card_if_empty(session, card_id, trigger=...)`；`common.db.session.async_session_maker`

- [ ] **Step 1: internal.py 挂钩**

先 Read 消费循环结束后的代码（L2040-2070），在 `card.type == 'data'` 且循环已结束时插入：

```python
        # 售罄守卫：data 卡库存被消费后归零时兜底下架（自带开关/类型判断）
        if card.type == 'data':
            try:
                from common.db.session import async_session_maker as _sg_asm
                from common.services.stock_guard_service import delist_card_if_empty
                async with _sg_asm() as _sg_session:
                    await delist_card_if_empty(_sg_session, request.card_id, trigger="delivery_internal")
            except Exception as _sg_e:
                logger.warning(f"【内部API】售罄守卫异常(忽略): {_sg_e}")
```

- [ ] **Step 2: agree_pickup_delivery.py 挂钩**

在成功路径的 `await session.commit()` 之后、`return True` 之前插入：

```python
        # 售罄守卫：提货发货成功后检查（自带开关/类型判断）
        if card.type == 'data':
            from common.services.stock_guard_service import delist_card_if_empty
            await delist_card_if_empty(session, card_id, trigger="delivery_pickup")
```

- [ ] **Step 3: 语法检查 + Commit**

```bash
python -m py_compile websocket/app/api/routes/internal.py common/services/agree_pickup_delivery.py
git add websocket/app/api/routes/internal.py common/services/agree_pickup_delivery.py
git commit -m "feat(stock-guard): 发货完成两处入口接入售罄兜底"
```

---

### Task 5: API 字段透出

**Files:**
- Modify: `backend-web/app/api/routes/cards.py:26-73`（`CardCreate`/`CardUpdate` 加字段；create 路由透传）
- Modify: `backend-web/app/services/card_service.py`（`create_card` 签名+kwargs、`update_card` 无需改、`_card_to_dict` L768 与 `_card_to_dict_lite` 与 L218 的列表序列化）

**Interfaces:**
- Produces: 请求/响应字段 `auto_delist_on_soldout: bool`

- [ ] **Step 1: Schema 加字段**（两个类都加，位置在 `dock_visibility` 后）

```python
    auto_delist_on_soldout: Optional[bool] = None  # 售罄自动下架开关（仅data类型）
```

- [ ] **Step 2: create 路由透传** — `create_card(...)` 调用末尾追加 `auto_delist_on_soldout=bool(card_data.auto_delist_on_soldout),`

- [ ] **Step 3: card_service.create_card 签名加 `auto_delist_on_soldout: bool = False` 参数**，并在构造 `Card(...)` 的 kwargs 中加入；`update_card` 的 `for key, value in kwargs.items(): if hasattr(card, key)` 自动支持，无需改

- [ ] **Step 4: 序列化透出** — `_card_to_dict` 返回 dict 加 `"auto_delist_on_soldout": card.auto_delist_on_soldout,`；`_card_to_dict_lite` 与 L218 的列表 dict 同样加

- [ ] **Step 5: 语法检查 + Commit**

```bash
python -m py_compile backend-web/app/api/routes/cards.py backend-web/app/services/card_service.py
git add backend-web/app/api/routes/cards.py backend-web/app/services/card_service.py
git commit -m "feat(stock-guard): 卡券API透出售罄自动下架开关"
```

---

### Task 6: Web 前端开关

**Files:**
- Modify: `frontend/src/pages/cards/CardFormModal.tsx`（表单 state + payload + UI）
- Modify: `frontend/src/api/cards.ts`（若存在 Card 类型定义则加字段；先 grep `auto_delist\|interface Card`）

- [ ] **Step 1:** grep/Read `CardFormModal.tsx`，找到表单 state 初始化（如 `useState` 的 form 对象）与提交 payload 构造处
- [ ] **Step 2:** 表单加 `auto_delist_on_soldout: boolean` state（编辑回显 `card.auto_delist_on_soldout`，新建默认 false），payload 透传
- [ ] **Step 3:** UI：仅当 `type === 'data'` 时渲染一行开关（样式复用弹窗内现有 Switch/勾选样式）：
  文案「售罄自动下架」，说明「待发货订单数量 ≥ 剩余库存时，自动下架该卡券绑定的全部商品（多账号商品各自下架）。补货后需手动重新上架」
- [ ] **Step 4:** `cd frontend && npm run build` 通过（tsc 0 错误）
- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/cards/CardFormModal.tsx frontend/src/api/cards.ts
git commit -m "feat(stock-guard-web): 卡券表单新增售罄自动下架开关"
```

---

### Task 7: 部署与线上验证

**Files:**
- 服务器路径：`/opt/xianyu-auto-reply/src/`（backend-web / websocket / scheduler 共享 common/）
- 工具：`remote_write.py`（base64 写文件）、`ssh_exec.py`

- [ ] **Step 1:** 用 `remote_write.py` 推送 8 个改动文件：`common/models/card.py`、`common/db/init_database.py`、`common/services/stock_guard_service.py`、`common/services/order_service.py`、`common/services/agree_pickup_delivery.py`、`websocket/app/api/routes/internal.py`、`backend-web/app/api/routes/cards.py`、`backend-web/app/services/card_service.py`（相对路径与服务端一致）；前端重新 `npm run build` 后同步 `frontend/dist/`（`tar czf - dist | ssh 'tar xzf - -C .../frontend/'` 或 scp 压缩包解开）

- [ ] **Step 2:** 服务器执行迁移与重启

```bash
mysql -uxianyu -p'<数据库密码>' xianyu_data -e "ALTER TABLE xy_cards ADD COLUMN auto_delist_on_soldout TINYINT(1) NOT NULL DEFAULT 0 COMMENT '售罄自动下架开关'"
systemctl restart xianyu-backend-web xianyu-websocket xianyu-scheduler
```

- [ ] **Step 3:** 定位用户目标卡券并开启开关

```sql
SELECT id,name,type FROM xy_cards WHERE type='data' AND id IN (SELECT card_id FROM xy_card_item_relations GROUP BY card_id HAVING COUNT(*)>=2);
-- 确认为“库存30张、绑2个商品”的那张后：
UPDATE xy_cards SET auto_delist_on_soldout=1 WHERE id=<card_id>;
```

- [ ] **Step 4:** 线上 dry-run 验证（不实际下架，先看统计值）——服务器上用 backend venv python 调 `_pending_quantity`/`_count_stock` 打印该卡的 stock/pending/绑定商品，核对数字合理

- [ ] **Step 5:** 实际触发验证——人工把阈值场景造出来（如临时修改 pending 统计或直接调用 `check_card_and_delist` 观察日志），确认：两个账号商品被下架、通知渠道收到告警、`journalctl -u xianyu-websocket -n 50` 有 `[售罄下架]` 日志；验证后如需恢复商品，手动重新上架

- [ ] **Step 6: Commit 部署记录 + 汇总**

---

### Task 8（可选）: PR #325 同步

本地分支提交后，如需纳入 PR：沿用 Git Data API 推送（父提交=fork 分支头），PR 描述追加“售罄自动下架”一节。
