"""
密码登录状态管理

功能：
1. 记录正在处理密码登录的账号
2. 防止同一账号重复触发密码登录
3. 自动清理超时的状态记录
"""
from __future__ import annotations

import threading
import time
from typing import Dict

from loguru import logger


class PasswordLoginStateManager:
    """密码登录状态管理器"""
    
    _instance = None
    _lock = threading.Lock()
    
    # 正在处理中的账号: account_id -> 开始时间戳
    _processing_accounts: Dict[str, float] = {}
    
    # 处理超时时间（秒），超过此时间自动清理状态
    PROCESSING_TIMEOUT = 300  # 5分钟
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def is_processing(self, account_id: str) -> bool:
        """
        检查账号是否正在处理密码登录
        
        Args:
            account_id: 账号ID
            
        Returns:
            True 表示正在处理中，False 表示空闲
        """
        with self._lock:
            # 先清理超时的记录
            self._cleanup_expired()
            
            return account_id in self._processing_accounts
    
    def start_processing(self, account_id: str) -> bool:
        """
        标记账号开始处理密码登录
        
        Args:
            account_id: 账号ID
            
        Returns:
            True 表示成功标记（之前未在处理中），False 表示已在处理中
        """
        with self._lock:
            # 先清理超时的记录
            self._cleanup_expired()
            
            if account_id in self._processing_accounts:
                logger.info(f"【密码登录状态】账号 {account_id} 已在处理中，丢弃本次请求")
                return False
            
            self._processing_accounts[account_id] = time.time()
            logger.info(f"【密码登录状态】账号 {account_id} 开始处理密码登录")
            return True
    
    def finish_processing(self, account_id: str) -> None:
        """
        标记账号完成密码登录处理
        
        Args:
            account_id: 账号ID
        """
        with self._lock:
            if account_id in self._processing_accounts:
                del self._processing_accounts[account_id]
                logger.info(f"【密码登录状态】账号 {account_id} 密码登录处理完成")
    
    def _cleanup_expired(self) -> None:
        """清理超时的处理状态（内部方法，需要在锁内调用）"""
        current_time = time.time()
        expired = [
            acc_id for acc_id, start_time in self._processing_accounts.items()
            if current_time - start_time > self.PROCESSING_TIMEOUT
        ]
        for acc_id in expired:
            del self._processing_accounts[acc_id]
            logger.warning(f"【密码登录状态】账号 {acc_id} 处理超时，自动清理状态")
    
    def get_processing_count(self) -> int:
        """获取正在处理的账号数量"""
        with self._lock:
            self._cleanup_expired()
            return len(self._processing_accounts)


# 全局单例
password_login_state = PasswordLoginStateManager()
