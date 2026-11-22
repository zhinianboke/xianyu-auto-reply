"""兼容卡券服务原导入路径，公共序列化由 common 统一维护。"""
from common.services.card_serialization import CardSerializationMixin

__all__ = ["CardSerializationMixin"]
