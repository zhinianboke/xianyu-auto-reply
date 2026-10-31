"""广告查询的连接断开重试，先回滚失败会话再复用统一连接池；付款不自动重试外部扣款。"""
from __future__ import annotations

from functools import wraps

from common.db.retry import is_db_disconnect_error, with_db_retry


def retry_ad_read(method):
    """装饰只读广告服务方法；仅连接断开可重试，失败事务必须先回滚。"""
    @with_db_retry(max_retries=2, initial_delay=0.2)
    @wraps(method)
    async def query(self, *args, **kwargs):
        try:
            return await method(self, *args, **kwargs)
        except Exception as exc:
            if is_db_disconnect_error(exc):
                await self.session.rollback()
            raise
    return query
