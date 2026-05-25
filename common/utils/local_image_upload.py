"""
本地图片上传通用工具

负责把 FastAPI ``UploadFile`` 落盘到本地静态目录（如 ``backend-web/static/uploads/<sub>``）的
共性流程：内容类型校验、可选大小校验、安全扩展名处理、唯一文件名生成、写文件。

与同目录下其他模块的区别：
- ``image_uploader.py``：把图片上传到闲鱼 CDN（远程），与本模块**无关**。
- ``image_utils.py``：基于 PIL 的图片格式/尺寸校验与压缩处理，``upload.py`` /
  ``user_settings.py`` 在用，本模块**不**做 PIL 处理，只负责简单的字节写盘。

设计原则：
- 工具只承担"底层能力"：类型校验、大小校验、扩展名安全、唯一名生成、写盘。
- 调用方仍负责：账号权限校验、业务保存、URL 拼接、失败回滚等业务逻辑。
- 出现校验失败时抛出 :class:`ImageUploadError`，由调用方按各自接口风格转换成
  ``HTTPException`` 或 ``ApiResponse``。

抽取背景见《重复代码分析报告.md》"图片上传处理逻辑重复"一节。
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Optional, Tuple, Union

from fastapi import UploadFile


# ====== 常量 ======

# 安全图片扩展名白名单（小写，含点）。白名单外的扩展名会回退到 :data:`DEFAULT_EXT`，
# 防止用户传入 ``.php`` / ``.exe`` 等危险后缀（防御任意文件落盘 / 静态目录被解析为脚本）。
SAFE_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

# 默认扩展名：原始文件名为空、无扩展名或扩展名不在白名单时的兜底。
DEFAULT_EXT = ".jpg"

# 默认最大字节数：5 MB，覆盖项目内多数上传接口的现状。
DEFAULT_MAX_SIZE = 5 * 1024 * 1024


# ====== 异常 ======


class ImageUploadError(Exception):
    """图片上传业务异常

    抛出此异常表示业务校验失败（类型不对、文件过大等），消息可直接呈现给前端用户。
    调用方根据接口风格决定转换为 ``HTTPException`` 还是 ``ApiResponse``。

    Attributes:
        message: 中文错误消息（已对前端用户友好）。
        status_code: 建议的 HTTP 状态码，仅供调用方参考；默认 400。
    """

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# ====== 子能力函数（按需直接调用） ======


def safe_image_ext(filename: Optional[str], default: str = DEFAULT_EXT) -> str:
    """从原始文件名中提取**安全**的扩展名（小写）。

    白名单（:data:`SAFE_IMAGE_EXTS`）外的扩展名会回退到 ``default``，
    避免用户上传可执行后缀。

    Args:
        filename: 原始文件名，可能为 ``None``。
        default: 不安全或缺失时的兜底扩展名（含点），默认 ``.jpg``。

    Returns:
        以 ``.`` 开头的小写扩展名。
    """
    if not filename:
        return default
    ext = os.path.splitext(filename)[1].lower()
    if ext in SAFE_IMAGE_EXTS:
        return ext
    return default


def validate_image_content_type(image: UploadFile) -> None:
    """校验 ``UploadFile.content_type`` 必须以 ``image/`` 开头。

    Raises:
        ImageUploadError: 内容类型缺失或不是图片。
    """
    if not image.content_type or not image.content_type.startswith("image/"):
        raise ImageUploadError("只支持上传图片文件")


async def read_image_with_size_check(
    image: UploadFile,
    max_size: int = DEFAULT_MAX_SIZE,
) -> bytes:
    """读取上传文件全部字节并按 ``max_size`` 校验大小。

    Args:
        image: FastAPI 上传文件对象。
        max_size: 最大字节数。``<= 0`` 表示不做大小校验
            （保留某些接口"只校验类型不限大小"的旧行为）。

    Returns:
        文件字节内容。

    Raises:
        ImageUploadError: 字节数超过 ``max_size``。
    """
    content = await image.read()
    if max_size and max_size > 0 and len(content) > max_size:
        size_mb = max_size / (1024 * 1024)
        # 对 5MB 这类整数做整型展示，避免 "5.0MB"
        size_text = f"{size_mb:.0f}" if size_mb.is_integer() else f"{size_mb:.1f}"
        raise ImageUploadError(f"图片大小不能超过{size_text}MB")
    return content


def build_unique_filename(
    original_filename: Optional[str],
    *,
    prefix: str = "",
    short_uuid: bool = False,
) -> str:
    """生成唯一且扩展名安全的文件名。

    Args:
        original_filename: 原始上传文件名，仅用于提取扩展名。
        prefix: 文件名前缀，可空。例如 ``"user_1"`` / ``"account_xxx_item_yyy"``，
            最终拼成 ``"{prefix}_{uuid}{ext}"``；为空时省略前缀及连接符。
        short_uuid: True 时使用 ``uuid.uuid4().hex[:8]``，否则使用完整 hex
            （对应不同接口的历史命名习惯）。

    Returns:
        新文件名（不含目录）。
    """
    ext = safe_image_ext(original_filename)
    uid = uuid.uuid4().hex[:8] if short_uuid else uuid.uuid4().hex
    if prefix:
        return f"{prefix}_{uid}{ext}"
    return f"{uid}{ext}"


# ====== 一站式入口 ======


async def save_uploaded_image(
    image: UploadFile,
    upload_dir: Union[str, Path],
    *,
    filename_prefix: str = "",
    max_size: int = DEFAULT_MAX_SIZE,
    short_uuid: bool = False,
    validate_size: bool = True,
) -> Tuple[Path, str, bytes]:
    """统一处理图片上传：类型校验 → 大小校验 → 生成唯一文件名 → 写盘。

    URL 拼接、失败回滚、业务保存等仍由调用方负责，函数只返回必要的中间结果。

    Args:
        image: FastAPI 上传文件对象。
        upload_dir: 保存目录（可传 :class:`pathlib.Path` 或字符串绝对/相对路径），
            目录不存在时会自动创建。
        filename_prefix: 文件名前缀，留空则只用 UUID。
        max_size: 最大字节数，默认 5 MB。
        short_uuid: True 时使用 8 位短 UUID，否则使用完整 32 位 hex。
        validate_size: 是否启用大小校验。设为 False 可保留某些接口"不校验大小"的旧行为。

    Returns:
        ``(filepath, filename, content)`` 三元组：

        - ``filepath``: 已落盘文件的绝对路径（:class:`pathlib.Path`），可直接用于
          需要本地路径的下游调用（例如 Playwright ``set_input_files``）。
        - ``filename``: 文件名（不含目录），调用方据此自行拼接 URL。
        - ``content``: 原始字节内容，调用方如需立即把字节写到其他地方可复用。

    Raises:
        ImageUploadError: 类型校验或大小校验失败。
    """
    validate_image_content_type(image)

    effective_max = max_size if validate_size else 0
    content = await read_image_with_size_check(image, effective_max)

    upload_dir_path = Path(upload_dir)
    upload_dir_path.mkdir(parents=True, exist_ok=True)

    filename = build_unique_filename(
        image.filename,
        prefix=filename_prefix,
        short_uuid=short_uuid,
    )
    filepath = upload_dir_path / filename

    with open(filepath, "wb") as f:
        f.write(content)

    return filepath, filename, content


__all__ = [
    "ImageUploadError",
    "SAFE_IMAGE_EXTS",
    "DEFAULT_EXT",
    "DEFAULT_MAX_SIZE",
    "safe_image_ext",
    "validate_image_content_type",
    "read_image_with_size_check",
    "build_unique_filename",
    "save_uploaded_image",
]
