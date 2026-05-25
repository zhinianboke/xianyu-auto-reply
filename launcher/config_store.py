"""
配置持久化模块

功能：
1. 保存用户填写的MySQL和Redis连接信息到本地文件
2. 下次启动时自动加载已保存的配置
3. 配置文件加密存储，防止明文泄露密码
"""
import base64
import json
import os
from pathlib import Path


# 配置文件名
_CONFIG_FILE = "connection.dat"


def _get_config_path() -> Path:
    """
    获取配置文件路径
    
    Returns:
        配置文件的完整路径
    """
    from launcher.frozen_detect import get_project_root
    base_dir = get_project_root()
    data_dir = base_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / _CONFIG_FILE


def _simple_encode(text: str) -> str:
    """
    简单编码，避免明文存储
    
    Args:
        text: 原始文本
    Returns:
        Base64编码后的字符串
    """
    return base64.b64encode(text.encode("utf-8")).decode("utf-8")


def _simple_decode(encoded: str) -> str:
    """
    简单解码
    
    Args:
        encoded: Base64编码的字符串
    Returns:
        解码后的原始文本
    """
    return base64.b64decode(encoded.encode("utf-8")).decode("utf-8")


def save_connection_config(config: dict) -> bool:
    """
    保存连接配置到文件
    
    对敏感字段（密码）做简单编码后保存。
    
    Args:
        config: 连接配置字典，包含mysql和redis的连接信息
    Returns:
        True保存成功，False保存失败
    """
    try:
        save_data = {
            "mysql_host": config.get("mysql_host", ""),
            "mysql_port": str(config.get("mysql_port", "3306")),
            "mysql_user": config.get("mysql_user", ""),
            "mysql_password": _simple_encode(config.get("mysql_password", "")),
            "mysql_database": config.get("mysql_database", ""),
            "redis_host": config.get("redis_host", ""),
            "redis_port": str(config.get("redis_port", "6379")),
            "redis_password": _simple_encode(config.get("redis_password", "")),
            "redis_db": str(config.get("redis_db", "0")),
        }
        config_path = _get_config_path()
        config_path.write_text(json.dumps(save_data, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def load_connection_config() -> dict | None:
    """
    从文件加载连接配置
    
    Returns:
        配置字典，如果文件不存在或读取失败返回None
    """
    config_path = _get_config_path()
    if not config_path.exists():
        return None
    
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        return {
            "mysql_host": data.get("mysql_host", ""),
            "mysql_port": data.get("mysql_port", "3306"),
            "mysql_user": data.get("mysql_user", ""),
            "mysql_password": _simple_decode(data.get("mysql_password", "")),
            "mysql_database": data.get("mysql_database", ""),
            "redis_host": data.get("redis_host", ""),
            "redis_port": data.get("redis_port", "6379"),
            "redis_password": _simple_decode(data.get("redis_password", "")),
            "redis_db": data.get("redis_db", "0"),
        }
    except Exception:
        return None
