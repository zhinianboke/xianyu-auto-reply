"""
配置文件初始化模块

功能：
启动时自检 data 目录，若缺少配置文件则自动生成模板文件，
用户只需修改其中的值即可。

自动生成的配置文件：
- data/update_config.json  在线更新服务器地址
"""
import json
import sys
from pathlib import Path


def _get_data_dir() -> Path:
    """获取 data 目录路径，不存在则自动创建"""
    from launcher.frozen_detect import get_project_root
    base_dir = get_project_root()
    data_dir = base_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


# 需要自动生成的配置文件及其默认内容
_CONFIG_TEMPLATES = {
    "update_config.json": {
        "update_url": "https://xy-update.zhinianboke.com"
    },
}


def init_config_files():
    """
    自检并初始化所有配置文件

    遍历 _CONFIG_TEMPLATES，如果对应文件不存在则自动生成模板。
    已存在的文件不会被覆盖，不影响历史数据。
    """
    data_dir = _get_data_dir()
    for filename, default_content in _CONFIG_TEMPLATES.items():
        config_path = data_dir / filename
        if not config_path.exists():
            try:
                config_path.write_text(
                    json.dumps(default_content, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception:
                pass
