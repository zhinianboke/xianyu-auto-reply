"""
本地视频上传工具。

功能：
1. 校验视频 MIME 类型和扩展名
2. 限制单个视频大小
3. 使用随机文件名保存到静态上传目录
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Optional, Tuple, Union

from fastapi import UploadFile


SAFE_VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm", ".flv", ".wmv"}
DEFAULT_VIDEO_EXT = ".mp4"
DEFAULT_VIDEO_MAX_SIZE = 100 * 1024 * 1024


class VideoUploadError(Exception):
    """视频上传校验异常。"""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def safe_video_ext(filename: Optional[str], default: str = DEFAULT_VIDEO_EXT) -> str:
    """提取视频文件的安全扩展名。"""
    if not filename:
        return default
    ext = os.path.splitext(filename)[1].lower()
    return ext if ext in SAFE_VIDEO_EXTS else default


async def save_uploaded_video(
    video: UploadFile,
    upload_dir: Union[str, Path],
    *,
    max_size: int = DEFAULT_VIDEO_MAX_SIZE,
) -> Tuple[Path, str, int]:
    """校验并保存一个视频文件。

    Args:
        video: FastAPI 上传文件对象
        upload_dir: 保存目录
        max_size: 单文件最大字节数
    Returns:
        本地绝对路径、随机文件名、文件字节数
    Raises:
        VideoUploadError: 文件类型或大小不符合要求
    """
    extension = safe_video_ext(video.filename)
    content_type = (video.content_type or "").lower()
    original_ext = os.path.splitext(video.filename or "")[1].lower()
    if not content_type.startswith("video/") and original_ext not in SAFE_VIDEO_EXTS:
        raise VideoUploadError("只支持上传视频文件")

    content = await video.read()
    if max_size > 0 and len(content) > max_size:
        raise VideoUploadError(f"视频大小不能超过{max_size // (1024 * 1024)}MB")

    upload_path = Path(upload_dir)
    upload_path.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{extension}"
    filepath = upload_path / filename
    with filepath.open("wb") as output:
        output.write(content)
    return filepath, filename, len(content)


__all__ = ["SAFE_VIDEO_EXTS", "VideoUploadError", "safe_video_ext", "save_uploaded_video"]
