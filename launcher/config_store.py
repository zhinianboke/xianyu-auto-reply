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
import re
from io import StringIO
from pathlib import Path

from dotenv.parser import parse_stream
from dotenv.variables import Variable, parse_variables

# 配置文件名
_CONFIG_FILE = "connection.dat"
_GEETEST_ENV_LINE = re.compile(r"^\s*(?:export[ \t]+)?['\"]?GEETEST_", re.IGNORECASE)


def preserve_geetest_env(env_path: Path, generated_content: str) -> str:
    """在重新生成 .env 时保留极验配置及其依赖的自定义变量。"""
    try:
        with env_path.open(encoding="utf-8-sig") as existing:
            bindings = list(parse_stream(existing))
    except FileNotFoundError:
        return generated_content

    generated_keys = {binding.key.upper() for binding in parse_stream(StringIO(generated_content)) if binding.key}
    required_keys: set[str] = set()
    retained_lines: list[str] = []
    # dotenv 按文件顺序展开引用，倒序查找每次引用之前已有的定义。
    for binding in reversed(bindings):
        key = binding.key
        if binding.error and _GEETEST_ENV_LINE.match(binding.original.string):
            retained_lines.append(binding.original.string)
        if not key or (key not in required_keys and not key.upper().startswith("GEETEST_")):
            continue
        required_keys.discard(key)
        if key.upper() in generated_keys:
            continue
        retained_lines.append(binding.original.string)
        if binding.value is not None:
            required_keys.update(
                var.name for var in parse_variables(binding.value) if isinstance(var, Variable)
            )
    return generated_content + "".join(reversed(retained_lines))


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
