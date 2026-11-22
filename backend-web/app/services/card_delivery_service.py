"""卡券内容消费与发货辅助服务，禁止读取或消费软删除卡券。"""
from __future__ import annotations

import json
from typing import Optional
import httpx
from loguru import logger
from sqlalchemy import select, update

from common.models.card import Card
from common.models.xy_account import XYAccount
from common.utils.response_field import extract_card_api_response_content


class CardDeliveryMixin:
    """提供卡券发货辅助方法，由 CardService 统一持有数据库会话。"""

    async def consume_batch_data(self, card_id: int) -> Optional[str]:
        """消费批量数据卡券的一条数据

        从卡券的 data_content 中取出第一行数据并删除。

        并发安全设计（CAS 乐观锁，不依赖行锁与事务隔离级别）：
            采用「读取当前内容 → 用单条 UPDATE 原子替换」的比较并交换方式：
            ``UPDATE xy_cards SET data_content=<去掉首行后的剩余内容>
              WHERE id=:card_id AND data_content=<读取到的旧内容>``。
            MySQL（InnoDB）保证对同一行的单条 UPDATE 串行执行，并发的多个消费
            请求中只有一个能匹配旧内容并成功（rowcount=1），其余 rowcount=0 后
            自动重读重试，从根本上避免同一条卡密被重复派发。

        Args:
            card_id: 卡券ID

        Returns:
            消费的数据内容或None
        """
        # CAS 失败（被其他并发请求抢先消费）时的最大重试次数，避免极端竞争下死循环
        max_cas_retries = 50

        for _ in range(max_cas_retries):
            # 1. 读取当前卡券内容
            stmt = select(Card.data_content).where(Card.id == card_id, Card.is_deleted.is_(False))
            result = await self.session.execute(stmt)
            current_content = result.scalar_one_or_none()

            if current_content is None:
                logger.warning(f"卡券 {card_id} 不存在或没有批量数据")
                return None

            # 2. 计算首行与剩余内容
            lines = [line.strip() for line in current_content.split('\n') if line.strip()]
            if not lines:
                logger.warning(f"卡券 {card_id} 批量数据已用完")
                return None

            consumed_data = lines[0]
            remaining_lines = lines[1:]
            new_content = '\n'.join(remaining_lines) if remaining_lines else ''

            # 3. CAS 原子替换：仅当 data_content 仍等于刚读取到的旧值时才更新
            cas_stmt = (
                update(Card)
                .where(Card.id == card_id, Card.is_deleted.is_(False), Card.data_content == current_content)
                .values(data_content=new_content)
            )
            cas_result = await self.session.execute(cas_stmt)
            await self.session.commit()

            if cas_result.rowcount == 1:
                logger.info(f"卡券 {card_id} 消费数据成功，剩余 {len(remaining_lines)} 条")
                return consumed_data

            # rowcount=0：内容已被其他并发请求改写，重读重试
            logger.warning(f"卡券 {card_id} 消费存在并发竞争，重试中...")

        logger.error(f"卡券 {card_id} 消费失败：并发竞争超过最大重试次数 {max_cas_retries}")
        return None

    async def increment_delivery_count(self, card_id: int) -> bool:
        """增加卡券的发货次数
        
        Args:
            card_id: 卡券ID
            
        Returns:
            是否更新成功
        """
        stmt = select(Card).where(Card.id == card_id, Card.is_deleted.is_(False))
        result = await self.session.execute(stmt)
        card = result.scalars().first()
        
        if not card:
            return False
        
        card.delivery_count = (card.delivery_count or 0) + 1
        await self.session.commit()
        return True

    async def get_available_card(
        self,
        account_pk: int,
        item_id: Optional[str] = None,
    ) -> Optional[Card]:
        """获取可用卡券
        
        Args:
            account_pk: 账号主键
            item_id: 商品ID（可选，用于匹配多规格卡券）
            
        Returns:
            可用的卡券或None
        """
        try:
            # 获取账号信息
            account_stmt = select(XYAccount).where(XYAccount.id == account_pk)
            account_result = await self.session.execute(account_stmt)
            account = account_result.scalars().first()
            
            if not account:
                return None
            
            # 查找启用的卡券
            stmt = select(Card).where(
                Card.user_id == account.owner_id,
                Card.is_deleted.is_(False),
                Card.enabled == True,
            )
            
            # 如果有商品ID，优先匹配多规格卡券
            if item_id:
                spec_stmt = stmt.where(
                    Card.is_multi_spec == True,
                    Card.spec_value == item_id,
                )
                spec_result = await self.session.execute(spec_stmt)
                spec_card = spec_result.scalars().first()
                if spec_card:
                    return spec_card
            
            # 返回第一个可用的卡券
            stmt = stmt.order_by(Card.created_at.asc()).limit(1)
            result = await self.session.execute(stmt)
            return result.scalars().first()
            
        except Exception as e:
            logger.error(f"获取可用卡券失败: {e}")
            return None

    async def mark_card_used(self, card_id: int, order_no: Optional[str] = None) -> bool:
        """标记卡券已使用
        
        对于数据类型卡券，可能需要从data_content中移除已使用的内容
        
        Args:
            card_id: 卡券ID
            order_no: 订单号（可选）
            
        Returns:
            是否成功
        """
        try:
            stmt = select(Card).where(Card.id == card_id, Card.is_deleted.is_(False))
            result = await self.session.execute(stmt)
            card = result.scalars().first()
            
            if not card:
                return False
            
            # 对于数据类型卡券，移除第一行数据
            if card.type == "data" and card.data_content:
                lines = card.data_content.strip().split("\n")
                if len(lines) > 1:
                    card.data_content = "\n".join(lines[1:])
                else:
                    # 数据用完，禁用卡券
                    card.data_content = ""
                    card.enabled = False
                
                await self.session.commit()
            
            logger.info(f"卡券 {card_id} 已标记使用，订单: {order_no}")
            return True
            
        except Exception as e:
            logger.error(f"标记卡券使用失败: {e}")
            await self.session.rollback()
            return False

    async def get_card_content(self, card_id: int) -> Optional[str]:
        """获取卡券内容
        
        根据卡券类型返回相应的内容
        
        Args:
            card_id: 卡券ID
            
        Returns:
            卡券内容或None
        """
        try:
            stmt = select(Card).where(Card.id == card_id, Card.is_deleted.is_(False))
            result = await self.session.execute(stmt)
            card = result.scalars().first()
            
            if not card or not card.enabled:
                return None
            
            if card.type == "text":
                return card.text_content
            elif card.type == "data":
                # 返回第一行数据
                if card.data_content:
                    lines = card.data_content.strip().split("\n")
                    return lines[0] if lines else None
            elif card.type == "image":
                return card.image_url
            elif card.type == "api":
                # API类型需要调用外部接口
                return await self._call_card_api(card)
            
            return None
            
        except Exception as e:
            logger.error(f"获取卡券内容失败: {e}")
            return None

    async def _call_card_api(self, card: Card) -> Optional[str]:
        """调用卡券API获取内容
        
        参数:
            card: 卡券对象
            
        返回:
            API返回的内容或None
        """
        try:
            if not card.api_config:
                return None
            
            config = json.loads(card.api_config) if isinstance(card.api_config, str) else card.api_config
            
            url = config.get("url")
            method = config.get("method", "GET").upper()
            headers = config.get("headers", {})
            params = config.get("params", {})
            body = config.get("body", {})
            
            if not url:
                return None
            
            async with httpx.AsyncClient(timeout=30) as client:
                if method == "GET":
                    response = await client.get(url, headers=headers, params=params)
                else:
                    response = await client.post(url, headers=headers, json=body)
                
                response.raise_for_status()
                response_field = config.get("response_field") or config.get("responseField")
                return extract_card_api_response_content(response.text, response_field)
                    
        except Exception as e:
            logger.error(f"调用卡券API失败: {e}")
            return None
