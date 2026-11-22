"""卡券服务统一入口：组合查询、写入、关联及发货职责，保持原导入和方法兼容。"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.card_delivery_service import CardDeliveryMixin
from app.services.card_mutation_service import CardMutationMixin
from app.services.card_query_service import CardQueryMixin
from app.services.card_relation_service import CardRelationMixin
from app.services.card_serialization import CardSerializationMixin


class CardService(
    CardQueryMixin, CardMutationMixin, CardRelationMixin,
    CardDeliveryMixin, CardSerializationMixin,
):
    """统一使用调用方会话提供卡券服务。"""

    def __init__(self, session: AsyncSession):
        """保存当前请求的数据库会话；参数为异步会话，无返回值。"""
        self.session = session
