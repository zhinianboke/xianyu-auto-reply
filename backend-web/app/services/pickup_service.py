"""
提货服务

功能：
1. 通过用户提货秘钥 + 对接记录ID 进行免登录提货
2. 参照自动发货逻辑取卡券内容（text/data/api/image）
3. 按对接记录的对接价格进行分润结算（复用 SettlementService）
4. 频率限制（每个对接记录每 5 秒最多 1 次）与并发控制（分布式锁）

说明：
    提货场景没有闲鱼订单，使用虚拟订单号（PICKUP 前缀）记录到代理订单表 xy_agent_orders，
    手续费按系统配置（distribution.fee_type / fee_rate）基于"对接价格"计算，
    承担方按卡券 fee_payer 决定。返回纯文本卡券内容。
"""
from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation
from typing import Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.db.redis_client import get_redis_client, DistributedLock
from common.models.agent_order import AgentOrder
from common.models.card import Card
from common.models.dock_record import DockRecord
from common.models.system_setting import SystemSetting
from common.models.user import User
from common.models.user_setting import UserSetting
from common.services.card_delivery_content import build_delivery_content
from common.services.settlement_service import SettlementService

# 频率限制：每个对接记录在该秒数内最多提货 1 次
PICKUP_RATE_LIMIT_SECONDS = 5
# 分布式锁前缀
PICKUP_LOCK_PREFIX = "pickup:dock:"
# 频率限制 Redis key 前缀
PICKUP_RATE_PREFIX = "pickup:rate:"
# 用户余额设置键
BALANCE_KEY = 'balance'


class PickupResult:
    """提货结果（成功返回纯文本内容，失败返回错误消息）"""

    def __init__(self, success: bool, content: str):
        self.success = success
        self.content = content


class PickupService:
    """提货服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def pickup(self, secret_key: str, dock_record_id: int) -> PickupResult:
        """执行一次提货

        Args:
            secret_key: 用户提货秘钥
            dock_record_id: 对接记录ID

        Returns:
            PickupResult：success=True 时 content 为卡券内容，否则为错误提示
        """
        try:
            # 1. 参数基础校验
            if not secret_key or not dock_record_id:
                return PickupResult(False, "提货失败：参数不完整")

            # 2. 校验秘钥对应用户（先校验身份，避免无效秘钥占用合法用户的限流窗口）
            user = await self._get_user_by_secret_key(secret_key)
            if not user:
                return PickupResult(False, "提货失败：秘钥无效")

            # 3. 频率限制（按 用户+对接记录 维度，每 5 秒最多 1 次）
            #    keyed by user.id 而非原始秘钥，既防刷又不把秘钥明文写入 Redis；
            #    且无效秘钥在第2步已被拦截，无法占用合法用户的限流窗口。
            allowed = await self._check_rate_limit(user.id, dock_record_id)
            if not allowed:
                return PickupResult(False, "提货失败：请求过于频繁，请 5 秒后再试")

            # 4. 分布式锁包住后续扣费+取卡，防止并发重复提货。
            #    仅当“获取锁”这一步本身因 Redis 异常失败时，才降级为依赖数据库行锁
            #    （余额 SELECT FOR UPDATE、批量卡密消费行锁）执行，保证 Redis 故障不影响可用性。
            #    注意：_do_pickup 自身的业务异常不在此降级，避免重复执行造成重复扣费/重复消费库存。
            lock = DistributedLock(f"{PICKUP_LOCK_PREFIX}{dock_record_id}", expire=30)
            lock_acquired = False
            try:
                lock_acquired = await lock.acquire(blocking=True, timeout=8.0)
            except Exception as lock_err:
                logger.warning(f"提货获取分布式锁异常，降级为数据库行锁控制: dock_id={dock_record_id}, err={lock_err}")
                lock_acquired = None  # None 表示 Redis 异常，降级执行

            if lock_acquired is False:
                # 锁被其他请求持有且等待超时
                return PickupResult(False, "提货失败：操作进行中，请稍后再试")

            try:
                return await self._do_pickup(user, dock_record_id)
            finally:
                if lock_acquired:
                    try:
                        await lock.release()
                    except Exception as rel_err:
                        logger.warning(f"提货释放分布式锁异常: dock_id={dock_record_id}, err={rel_err}")
        except Exception as e:
            logger.error(f"提货异常: dock_id={dock_record_id}, err={e}")
            # 回滚未提交的事务，避免脏数据
            try:
                await self.session.rollback()
            except Exception:
                pass
            return PickupResult(False, "提货失败：系统繁忙，请稍后再试")

    async def _do_pickup(self, user: User, dock_record_id: int) -> PickupResult:
        """锁内执行的提货主体逻辑（取卡 + 结算，同一事务）"""
        # 查对接记录
        dock_record = await self.session.get(DockRecord, dock_record_id)
        if not dock_record:
            return PickupResult(False, "提货失败：对接记录不存在")
        if dock_record.user_id != user.id:
            return PickupResult(False, "提货失败：无权操作该对接记录")
        if not dock_record.status:
            reason = dock_record.disable_reason or "对接记录已停用"
            return PickupResult(False, f"提货失败：{reason}")

        # 查卡券
        card = await self.session.get(Card, dock_record.card_id)
        if not card:
            return PickupResult(False, "提货失败：卡券不存在")
        if not card.enabled:
            return PickupResult(False, "提货失败：卡券已停用")

        # 确定对接来源与价格
        dock_level = dock_record.level
        card_price = self._to_decimal(card.price)  # 货主对接价（卡券成本）
        owner_user_id = card.user_id
        fee_payer = card.fee_payer  # distributor / dealer

        # 对接价格（提货价 = 本级拿货价），同时作为本笔提货的"订单金额"
        if dock_level == 1:
            dock_price = card_price
            upstream_user_id = owner_user_id
            level1_user_id = None
            level2_cost = Decimal('0')
        else:
            # 二级：拿货价取上级 sub_dock_price
            level2_cost = await self._get_level2_cost(dock_record, card_price)
            dock_price = level2_cost
            upstream_user_id = dock_record.source_user_id
            level1_user_id = dock_record.source_user_id

        sale_price = dock_price  # 提货：以对接价格作为订单金额

        # 手续费金额（按系统配置基于对接价格计算）
        fee_amount = await self._calc_fee(sale_price)

        # 结算前对所有参与方做净额余额校验：
        # 模拟本笔提货对每个账户的净变动，任一账户结算后会变为负数则拒绝提货，
        # 避免一级代理/货主因手续费或链路扣款被扣成负余额。
        settlement = SettlementService(self.session)
        net_deltas = self._compute_net_deltas(
            dock_level=dock_level,
            dealer_user_id=user.id,
            level1_user_id=level1_user_id,
            owner_user_id=owner_user_id,
            card_price=card_price,
            level2_cost=level2_cost,
            fee_amount=fee_amount,
            fee_payer=fee_payer,
        )
        insufficient = await self._check_parties_balance(net_deltas)
        if insufficient:
            who, balance, shortfall = insufficient
            role_label = self._role_label(who, user.id, level1_user_id, owner_user_id)
            return PickupResult(
                False,
                f"提货失败：{role_label}余额不足（当前余额 {balance}，本单需净支出 {shortfall}）",
            )

        # 生成虚拟订单号
        order_no = self._generate_order_no(dock_record_id)

        # 取卡券内容（data 类型在本事务内消费库存）
        context = {
            'order_id': order_no,
            'item_id': '',
            'buyer_id': 'pickup',
            'spec_name': card.spec_name or '',
            'spec_value': card.spec_value or '',
            'order_amount': str(sale_price),
        }
        content = await build_delivery_content(self.session, card, context)
        if not content:
            await self.session.rollback()
            return PickupResult(False, "提货失败：卡券内容获取失败或库存不足")

        # 计算利润（提货 sale=dock，利润为 0）
        profit = '0.00'

        # 创建代理订单记录
        agent_order = AgentOrder(
            user_id=user.id,
            order_no=order_no,
            item_id=card.item_id or '',
            card_id=card.id,
            dock_record_id=dock_record_id,
            dock_level=dock_level,
            sale_price=str(sale_price),
            dock_price=str(dock_price),
            card_price=str(card_price),
            level2_cost=str(level2_cost) if dock_level == 2 else None,
            profit=profit,
            fee_amount=str(fee_amount),
            fee_payer=fee_payer,
            upstream_user_id=upstream_user_id,
            upstream_dock_record_id=dock_record.parent_dock_id if dock_level == 2 else None,
            owner_user_id=owner_user_id,
            delivery_content=content[:2000],
            buyer_id='pickup',
            status='delivered',
        )
        self.session.add(agent_order)
        await self.session.flush()

        # 分润结算（同一事务）
        try:
            if dock_level == 1 and owner_user_id:
                await settlement.settle_level1_order(
                    order_no=order_no,
                    dealer_user_id=user.id,
                    owner_user_id=owner_user_id,
                    dock_record_id=dock_record_id,
                    agent_order_id=agent_order.id,
                    sale_price=str(sale_price),
                    card_price=str(card_price),
                    fee_payer=fee_payer,
                    fee_amount=str(fee_amount),
                )
                agent_order.status = 'settled'
            elif dock_level == 2 and level1_user_id and owner_user_id:
                await settlement.settle_level2_order(
                    order_no=order_no,
                    dealer_user_id=user.id,
                    level1_user_id=level1_user_id,
                    owner_user_id=owner_user_id,
                    dock_record_id=dock_record_id,
                    parent_dock_record_id=dock_record.parent_dock_id or 0,
                    agent_order_id=agent_order.id,
                    sale_price=str(sale_price),
                    level2_cost=str(level2_cost),
                    level1_cost=str(card_price),
                    fee_payer=fee_payer,
                    fee_amount=str(fee_amount),
                )
                agent_order.status = 'settled'
        except Exception as settle_err:
            logger.error(f"提货分润结算失败: {settle_err}")
            agent_order.settle_remark = f'结算失败: {settle_err}'

        # 累加对接记录发货次数
        dock_record.delivery_count = (dock_record.delivery_count or 0) + 1

        await self.session.commit()
        logger.info(
            f"提货成功: 用户={user.id}, 对接记录={dock_record_id}, 订单号={order_no}, "
            f"对接价={dock_price}, 手续费={fee_amount}({fee_payer})"
        )
        # 提货为纯文本返回：将自动发货用的多消息分隔符 ###### 转为换行符显示。
        # 仅作用于返回给调用方的文本，入库的 delivery_content 保留原始内容，不影响自动发货逻辑。
        return PickupResult(True, self._format_for_plain_text(content))

    async def _check_rate_limit(self, user_id: int, dock_record_id: int) -> bool:
        """频率限制：同一用户对同一对接记录每 PICKUP_RATE_LIMIT_SECONDS 秒最多 1 次

        使用 Redis SET NX EX 实现：key 存在则拒绝。Redis 异常时放行（不阻断业务）。
        key 维度为 用户+对接记录，避免无效请求影响合法用户。
        """
        try:
            client = await get_redis_client()
            key = f"{PICKUP_RATE_PREFIX}{user_id}:{dock_record_id}"
            # 仅当 key 不存在时设置，并附带过期时间
            ok = await client.set(key, "1", nx=True, ex=PICKUP_RATE_LIMIT_SECONDS)
            return bool(ok)
        except Exception as e:
            logger.warning(f"提货频率限制检查异常（放行）: {e}")
            return True

    async def _get_user_by_secret_key(self, secret_key: str) -> Optional[User]:
        """按提货秘钥查询用户"""
        stmt = select(User).where(User.secret_key == secret_key)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_level2_cost(self, dock_record: DockRecord, card_price: Decimal) -> Decimal:
        """获取二级拿货价（上级对接记录的 sub_dock_price），回退到卡券成本"""
        if dock_record.parent_dock_id:
            stmt = select(DockRecord.sub_dock_price).where(DockRecord.id == dock_record.parent_dock_id)
            result = await self.session.execute(stmt)
            sub_dock_price = result.scalar()
            if sub_dock_price:
                return self._to_decimal(sub_dock_price)
        return card_price

    async def _calc_fee(self, sale_price: Decimal) -> Decimal:
        """按系统配置计算手续费金额

        distribution.fee_type: fixed-固定金额 / percent-百分比
        distribution.fee_rate: 数值（百分比时为百分数，如 5 表示 5%）
        """
        fee_type = 'fixed'
        fee_rate = Decimal('0')
        try:
            type_stmt = select(SystemSetting.value).where(SystemSetting.key == 'distribution.fee_type')
            fee_type = (await self.session.execute(type_stmt)).scalar() or 'fixed'

            rate_stmt = select(SystemSetting.value).where(SystemSetting.key == 'distribution.fee_rate')
            fee_rate = self._to_decimal((await self.session.execute(rate_stmt)).scalar())
        except Exception as e:
            logger.warning(f"获取分销手续费配置失败，按 0 处理: {e}")
            return Decimal('0')

        if fee_type == 'percent':
            return (sale_price * fee_rate / Decimal('100')).quantize(Decimal('0.01'))
        return fee_rate

    def _compute_net_deltas(
        self,
        *,
        dock_level: int,
        dealer_user_id: int,
        level1_user_id: Optional[int],
        owner_user_id: Optional[int],
        card_price: Decimal,
        level2_cost: Decimal,
        fee_amount: Decimal,
        fee_payer: Optional[str],
    ) -> dict[int, Decimal]:
        """计算本笔提货对各参与方余额的净变动（与 SettlementService 结算规则一致）

        返回 {user_id: 净变动金额}，负数表示净支出。校验时要求 余额 + 净变动 >= 0。

        一级提货：
          - dealer(发起方) 付货主 card_price；dealer 承担手续费时再扣 fee
          - owner 收 card_price；distributor 承担手续费时扣 fee
        二级提货：
          - dealer(发起方,即二级) 付一级 level2_cost；dealer 承担手续费时再扣 fee
          - level1 收 level2_cost、付货主 card_price（净 = level2_cost - card_price）
          - owner 收 card_price；distributor 承担手续费时扣 fee
        """
        deltas: dict[int, Decimal] = {}

        def add(uid: Optional[int], amount: Decimal):
            if uid:
                deltas[uid] = deltas.get(uid, Decimal('0')) + amount

        fee = fee_amount if fee_amount and fee_amount > 0 else Decimal('0')

        if dock_level == 1:
            # 发起方（分销商）支付卡券成本给货主
            add(dealer_user_id, -card_price)
            add(owner_user_id, card_price)
            if fee_payer == 'dealer':
                add(dealer_user_id, -fee)
            else:  # distributor / 其他默认货主承担
                add(owner_user_id, -fee)
        else:
            # 二级提货
            add(dealer_user_id, -level2_cost)
            add(level1_user_id, level2_cost)
            add(level1_user_id, -card_price)
            add(owner_user_id, card_price)
            if fee_payer == 'dealer':
                add(dealer_user_id, -fee)
            else:
                add(owner_user_id, -fee)

        return deltas

    async def _check_parties_balance(
        self,
        net_deltas: dict[int, Decimal],
    ) -> Optional[tuple[int, Decimal, Decimal]]:
        """校验各参与方结算后余额不会为负（带行锁，防止并发超扣 + 防死锁）

        对本笔提货涉及的所有账户（含收入方）的余额行，按 user_id 升序统一执行
        SELECT ... FOR UPDATE。这样做有两个目的：
        1. 防超扣：锁持有至事务结束，串行化任何并发操作这些余额行的提货/结算，
           消除“预检通过但实际扣成负数”的竞态。
        2. 防死锁：在结算开始前以全局一致的顺序（user_id 升序）拿全部锁，
           避免结算阶段 _deduct/_add 以不同顺序加锁导致跨事务交叉等待。

        仅对净支出账户（delta<0）做余额是否充足的判断；收入方只加锁不判断。

        Returns:
            None 表示全部充足；否则返回 (不足的user_id, 当前余额, 本单净支出绝对值)
        """
        insufficient: Optional[tuple[int, Decimal, Decimal]] = None
        # 按 user_id 升序锁定所有相关账户（含收入方），建立全局一致加锁顺序
        for uid in sorted(net_deltas.keys()):
            delta = net_deltas[uid]
            balance = await self._lock_and_read_balance(uid)
            # 仅净支出账户判断是否会变负；记录首个不足者（仍继续加锁以保持顺序一致）
            if delta < 0 and insufficient is None and balance + delta < Decimal('0'):
                insufficient = (uid, balance, -delta)
        return insufficient

    async def _lock_and_read_balance(self, user_id: int) -> Decimal:
        """对用户余额行加行锁并读取当前余额（行锁持有至事务结束）

        Args:
            user_id: 用户ID

        Returns:
            当前余额（无记录视为 0）
        """
        stmt = select(UserSetting).where(
            UserSetting.user_id == user_id,
            UserSetting.key == BALANCE_KEY,
        ).with_for_update()
        result = await self.session.execute(stmt)
        setting = result.scalar_one_or_none()
        if not setting:
            return Decimal('0')
        return self._to_decimal(setting.value)

    @staticmethod
    def _role_label(uid: int, dealer_user_id: int, level1_user_id: Optional[int], owner_user_id: Optional[int]) -> str:
        """根据 user_id 返回中文角色名（用于余额不足提示）"""
        if uid == dealer_user_id:
            return "您的"
        if level1_user_id and uid == level1_user_id:
            return "上级分销商"
        if owner_user_id and uid == owner_user_id:
            return "货主"
        return "相关账户"

    @staticmethod
    def _generate_order_no(dock_record_id: int) -> str:
        """生成提货虚拟订单号"""
        return f"PICKUP{dock_record_id}_{uuid.uuid4().hex[:16]}"

    @staticmethod
    def _format_for_plain_text(content: str) -> str:
        """将发货内容转换为适合纯文本展示的形式

        自动发货使用 ###### 作为"拆分多条消息"的分隔符；提货为纯文本一次性返回，
        因此把 ###### 统一替换为换行符显示。仅处理返回文本，不改动入库内容，
        不影响 websocket 自动发货按 ###### 拆分发送的逻辑。

        Args:
            content: 原始发货内容

        Returns:
            分隔符替换为换行后的文本
        """
        if not content:
            return content
        if '######' in content:
            # 拆分后去除每段首尾空白，用换行拼接，避免分隔符两侧出现多余空行
            segments = [seg.strip() for seg in content.split('######')]
            return '\n'.join(seg for seg in segments if seg)
        return content

    @staticmethod
    def _to_decimal(value) -> Decimal:
        """安全转 Decimal"""
        try:
            return Decimal(str(value or '0'))
        except (InvalidOperation, ValueError, TypeError):
            return Decimal('0')
