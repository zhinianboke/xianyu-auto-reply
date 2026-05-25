"""
路径配置模块

功能：
1. 统一管理项目中的文件路径
2. 提供上传目录、静态文件目录等配置
3. 确保目录存在
"""
from __future__ import annotations

import os
from pathlib import Path

# 项目根目录 (backend-web/)
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 静态文件根目录 - 优先使用环境变量 STATIC_DIR（Docker共享卷），本地回退到 backend-web/static
_static_dir_env = os.environ.get("STATIC_DIR", "")
if _static_dir_env:
    STATIC_ROOT = Path(_static_dir_env)
    if not STATIC_ROOT.is_absolute():
        STATIC_ROOT = Path.cwd() / STATIC_ROOT
else:
    STATIC_ROOT = PROJECT_ROOT / "static"

# 上传文件目录 - 统一使用 static/uploads/
UPLOADS_ROOT = STATIC_ROOT / "uploads"

# 上传子目录
UPLOADS_IMAGES = UPLOADS_ROOT / "images"      # 图片上传目录
UPLOADS_KEYWORDS = UPLOADS_ROOT / "keywords"  # 关键词图片目录
UPLOADS_FACE = UPLOADS_ROOT / "face"          # 人脸验证截图目录
UPLOADS_PRODUCTS = UPLOADS_ROOT / "products"  # 商品发布图片目录


def ensure_upload_dirs() -> None:
    """确保所有上传目录存在"""
    dirs = [
        STATIC_ROOT,
        UPLOADS_ROOT,
        UPLOADS_IMAGES,
        UPLOADS_KEYWORDS,
        UPLOADS_FACE,
        UPLOADS_PRODUCTS,
    ]
    for dir_path in dirs:
        dir_path.mkdir(parents=True, exist_ok=True)


def get_upload_path(subdir: str = "images") -> Path:
    """获取上传目录路径
    
    Args:
        subdir: 子目录名称 (images/keywords/face)
        
    Returns:
        上传目录路径
    """
    ensure_upload_dirs()
    
    subdirs = {
        "images": UPLOADS_IMAGES,
        "keywords": UPLOADS_KEYWORDS,
        "face": UPLOADS_FACE,
        "products": UPLOADS_PRODUCTS,
    }
    return subdirs.get(subdir, UPLOADS_ROOT)


def get_static_url(filepath: str) -> str:
    """将文件路径转换为静态URL
    
    Args:
        filepath: 文件路径（相对于static目录）
        
    Returns:
        静态文件URL
    """
    # 移除可能的前缀
    filepath = filepath.replace("\\", "/")
    if filepath.startswith("static/"):
        filepath = filepath[7:]
    elif filepath.startswith("/static/"):
        filepath = filepath[8:]
    
    return f"/static/{filepath}"


__all__ = [
    "PROJECT_ROOT",
    "STATIC_ROOT", 
    "UPLOADS_ROOT",
    "UPLOADS_IMAGES",
    "UPLOADS_KEYWORDS",
    "UPLOADS_FACE",
    "UPLOADS_PRODUCTS",
    "ensure_upload_dirs",
    "get_upload_path",
    "get_static_url",
]
