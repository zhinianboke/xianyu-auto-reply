"""
清理被禁用账号浏览器数据任务

功能：
1. 每10分钟执行一次
2. 查询数据库中status='disabled'且更新时间在10天之前的账号
3. 删除对应的browser_data/user_{account_id}目录
4. 只清理被禁用且超过10天未变更的账号数据，启用状态或近期变更的数据不删除
"""
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger
from sqlalchemy import select

from common.db.session import async_session_maker
from common.models.xy_account import XYAccount
from common.utils.time_utils import get_beijing_now_naive

# 禁用账号超过该天数（基于更新时间）后才清理其浏览器数据
DISABLED_RETENTION_DAYS = 10


class CleanupBrowserDataTaskService:
    """清理被禁用账号浏览器数据任务服务"""
    
    def __init__(self):
        self.task_name = "清理被禁用账号浏览器数据"
        # browser_data目录位于websocket项目中
        # scheduler/app/services/scheduler/cleanup_browser_data_task.py -> 项目根目录
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent.parent.parent.parent
        self.browser_data_dir = project_root / "websocket" / "browser_data"
    
    async def execute(self):
        """执行清理任务"""
        logger.info(f"【{self.task_name}】开始执行")
        start_time = datetime.now()
        
        try:
            # 1. 检查browser_data目录是否存在
            if not self.browser_data_dir.exists():
                logger.info(f"【{self.task_name}】browser_data目录不存在，跳过清理")
                return
            
            # 2. 查询所有被禁用且超过保留天数未变更的账号
            disabled_accounts = await self._get_disabled_accounts()
            
            logger.info(
                f"【{self.task_name}】查询到 {len(disabled_accounts)} 个"
                f"被禁用且超过{DISABLED_RETENTION_DAYS}天未变更的账号"
            )
            
            if not disabled_accounts:
                logger.info(f"【{self.task_name}】没有需要清理的账号，任务结束")
                return
            
            # 3. 清理被禁用账号的浏览器数据
            cleaned_count = 0
            skipped_count = 0
            failed_count = 0
            total_size = 0
            
            for account_id in disabled_accounts:
                try:
                    size = await self._cleanup_account_browser_data(account_id)
                    if size > 0:
                        cleaned_count += 1
                        total_size += size
                    elif size == 0:
                        skipped_count += 1
                    else:
                        failed_count += 1
                except Exception as e:
                    failed_count += 1
                    logger.error(f"【{self.task_name}】清理账号 {account_id} 的浏览器数据失败: {e}")
            
            # 4. 记录执行结果
            elapsed = (datetime.now() - start_time).total_seconds()
            size_mb = total_size / (1024 * 1024)
            
            logger.info(
                f"【{self.task_name}】清理完成，"
                f"已删除: {cleaned_count}, 目录不存在: {skipped_count}, 失败: {failed_count}, "
                f"释放空间: {size_mb:.2f}MB, "
                f"耗时: {elapsed:.2f}秒"
            )
            
        except Exception as e:
            logger.error(f"【{self.task_name}】执行失败: {e}", exc_info=True)
            raise
    
    async def _get_disabled_accounts(self) -> list[str]:
        """
        获取所有被禁用且超过保留天数未变更的账号ID列表
        
        判断条件：status='disabled' 且 updated_at <= (当前北京时间 - 保留天数)
        即账号已被禁用，且更新日期已超过 DISABLED_RETENTION_DAYS 天没有变化
        
        Returns:
            符合条件的账号ID列表
        """
        try:
            # 计算截止时间：早于该时间的禁用账号才需要清理
            cutoff_time = get_beijing_now_naive() - timedelta(days=DISABLED_RETENTION_DAYS)
            
            async with async_session_maker() as session:
                # 查询status='disabled'且更新时间在截止时间之前的账号
                stmt = select(XYAccount.account_id).where(
                    XYAccount.status == "disabled",
                    XYAccount.updated_at <= cutoff_time,
                )
                result = await session.execute(stmt)
                account_ids = [row[0] for row in result.fetchall()]
                
                logger.debug(
                    f"【{self.task_name}】截止时间 {cutoff_time}，"
                    f"查询到 {len(account_ids)} 个符合清理条件的被禁用账号"
                )
                return account_ids
                
        except Exception as e:
            logger.error(f"【{self.task_name}】查询被禁用账号失败: {e}")
            return []
    
    async def _cleanup_account_browser_data(self, account_id: str) -> int:
        """
        清理指定账号的浏览器数据目录
        
        Args:
            account_id: 账号ID
            
        Returns:
            清理的目录大小（字节），如果目录不存在返回0，失败返回-1
        """
        try:
            # 构造目录路径: browser_data/user_{account_id}
            user_data_dir = self.browser_data_dir / f"user_{account_id}"
            
            # 检查目录是否存在
            if not user_data_dir.exists():
                logger.debug(f"【{self.task_name}】账号 {account_id} 的浏览器数据目录不存在: {user_data_dir}")
                return 0
            
            # 计算目录大小
            dir_size = self._get_directory_size(user_data_dir)
            size_mb = dir_size / (1024 * 1024)
            
            # 删除目录
            shutil.rmtree(user_data_dir, ignore_errors=False)
            
            logger.info(
                f"【{self.task_name}】✓ 已删除目录: {user_data_dir}, "
                f"账号: {account_id}, 释放空间: {size_mb:.2f}MB"
            )
            
            return dir_size
            
        except Exception as e:
            logger.error(f"【{self.task_name}】✗ 清理失败: {user_data_dir}, 账号: {account_id}, 错误: {e}")
            return -1
    
    def _get_directory_size(self, directory: Path) -> int:
        """
        计算目录大小
        
        Args:
            directory: 目录路径
            
        Returns:
            目录大小（字节）
        """
        total_size = 0
        try:
            for item in directory.rglob('*'):
                if item.is_file():
                    try:
                        total_size += item.stat().st_size
                    except (OSError, PermissionError):
                        # 忽略无法访问的文件
                        pass
        except Exception as e:
            logger.warning(f"【{self.task_name}】计算目录大小失败: {e}")
        
        return total_size


# 创建全局实例
cleanup_browser_data_task_service = CleanupBrowserDataTaskService()
