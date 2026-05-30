"""
平台日切换任务服务

功能：
1. 每60秒执行一次
2. 检查Redis中的平台日与服务器当前日期是否一致
3. 如果不一致，先将商品信息表中的is_polished全部更新为False
4. 然后更新Redis中的平台日为服务器当前日期
"""
from datetime import datetime
from typing import Optional

from loguru import logger
from sqlalchemy import text

from common.db.session import async_session_maker
from common.db.redis_client import get_redis_client
from common.utils.time_utils import get_beijing_now_naive


class DaySwitchTaskService:
    """平台日切换任务服务"""
    
    # Redis中平台日的key
    PLATFORM_DAY_KEY = "platform:day"
    
    def __init__(self):
        self.task_name = "平台日切换"
    
    async def execute(self):
        """执行平台日切换任务"""
        logger.info(f"【{self.task_name}】开始执行")
        start_time = datetime.now()
        
        try:
            # 1. 获取服务器当前日期（北京时间，格式：yyyy-MM-dd）
            current_day = get_beijing_now_naive().strftime("%Y-%m-%d")
            logger.debug(f"【{self.task_name}】服务器当前日期: {current_day}")
            
            # 2. 从Redis获取平台日
            platform_day = await self._get_platform_day()
            logger.debug(f"【{self.task_name}】Redis中的平台日: {platform_day}")
            
            # 3. 比对日期
            if platform_day == current_day:
                logger.debug(f"【{self.task_name}】平台日与服务器日期一致，无需切换")
                return
            
            logger.info(
                f"【{self.task_name}】检测到日期变化: {platform_day} -> {current_day}，开始执行日切换"
            )
            
            # 4. 重置商品擦亮状态
            reset_count = await self._reset_item_polish_status()
            logger.info(f"【{self.task_name}】已重置 {reset_count} 个商品的擦亮状态")
            
            # 5. 更新Redis中的平台日
            await self._update_platform_day(current_day)
            logger.info(f"【{self.task_name}】已更新Redis中的平台日为: {current_day}")
            
            # 6. 记录执行结果
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(
                f"【{self.task_name}】日切换完成，"
                f"重置商品数: {reset_count}, "
                f"耗时: {elapsed:.2f}秒"
            )
            
        except Exception as e:
            logger.error(f"【{self.task_name}】执行失败: {e}", exc_info=True)
            raise
    
    async def _get_platform_day(self) -> Optional[str]:
        """
        从Redis获取平台日
        
        Returns:
            平台日字符串（yyyy-MM-dd格式），如果不存在返回None
        """
        try:
            redis_client = await get_redis_client()
            platform_day = await redis_client.get(self.PLATFORM_DAY_KEY)
            return platform_day
        except Exception as e:
            logger.error(f"【{self.task_name}】从Redis获取平台日失败: {e}")
            return None
    
    async def _update_platform_day(self, new_day: str) -> bool:
        """
        更新Redis中的平台日
        
        Args:
            new_day: 新的平台日（yyyy-MM-dd格式）
            
        Returns:
            是否更新成功
        """
        try:
            redis_client = await get_redis_client()
            await redis_client.set(self.PLATFORM_DAY_KEY, new_day)
            logger.debug(f"【{self.task_name}】Redis平台日已更新: {new_day}")
            return True
        except Exception as e:
            logger.error(f"【{self.task_name}】更新Redis平台日失败: {e}")
            return False
    
    async def _reset_item_polish_status(self) -> int:
        """
        重置所有商品的擦亮状态为False
        
        Returns:
            受影响的行数
        """
        try:
            async with async_session_maker() as session:
                # 更新所有商品的is_polished为False
                result = await session.execute(
                    text("""
                        UPDATE xy_catalog_items 
                        SET is_polished = 0 
                        WHERE is_polished = 1
                    """)
                )
                await session.commit()
                
                affected_rows = result.rowcount
                logger.debug(f"【{self.task_name}】已重置 {affected_rows} 个商品的擦亮状态")
                return affected_rows
                
        except Exception as e:
            logger.error(f"【{self.task_name}】重置商品擦亮状态失败: {e}")
            raise


# 创建全局实例
day_switch_task_service = DaySwitchTaskService()
