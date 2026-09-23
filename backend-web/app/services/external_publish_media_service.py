"""
公开接口发布媒体服务。

功能：
1. 将公开接口上传的图片、视频和规格图片按用户及闲鱼账号隔离保存。
2. 生成只能在所属账号下解析的 media_id，避免公开发布接口接收本地路径。
3. 将 media_id 转换为现有闲鱼接口发布器可读取的静态文件地址。
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.paths import STATIC_ROOT
from common.models.xy_account import XYAccount
from common.utils.local_image_upload import ImageUploadError, save_uploaded_image
from common.utils.local_video_upload import VideoUploadError, save_uploaded_video


MEDIA_TYPES = {"image", "spec_image", "video"}
MEDIA_ID_PATTERN = re.compile(r"^(image|spec_image|video)_[0-9a-f]{32}$")


class ExternalPublishMediaError(RuntimeError):
    """公开发布媒体保存或解析失败时抛出的业务异常。"""


class ExternalPublishMediaService:
    """管理公开发布接口的临时媒体文件。"""

    @staticmethod
    def _normalize_media_type(media_type: str) -> str:
        """
        校验媒体类型。

        Args:
            media_type: 调用方传入的媒体类型。
        Returns:
            规范化后的媒体类型。
        Raises:
            ExternalPublishMediaError: 类型不受支持时抛出。
        """
        normalized = media_type.strip().lower()
        if normalized not in MEDIA_TYPES:
            raise ExternalPublishMediaError("media_type仅支持image、spec_image或video")
        return normalized

    @staticmethod
    def _media_dir(account: XYAccount, media_type: str) -> Path:
        """
        返回账号隔离后的媒体目录。

        Args:
            account: 已通过秘钥校验的闲鱼账号。
            media_type: 已规范化的媒体类型。
        Returns:
            媒体目录绝对路径。
        """
        return (
            STATIC_ROOT
            / "uploads"
            / "external_publish"
            / str(account.owner_id)
            / str(account.id)
            / media_type
        )

    @staticmethod
    def _static_url(filepath: Path) -> str:
        """
        将静态目录内文件转为发布器可读取的静态 URL。

        Args:
            filepath: 静态目录内的媒体文件路径。
        Returns:
            以 /static/ 开头的相对地址。
        Raises:
            ExternalPublishMediaError: 文件不在静态目录内时抛出。
        """
        try:
            relative_path = filepath.resolve().relative_to(STATIC_ROOT.resolve())
        except ValueError as exc:
            raise ExternalPublishMediaError("公开发布媒体路径无效") from exc
        return f"/static/{relative_path.as_posix()}"

    async def save_media(
        self,
        account: XYAccount,
        media_type: str,
        file: UploadFile,
    ) -> dict[str, str | int]:
        """
        保存一份公开发布媒体并返回 media_id。

        Args:
            account: 已通过秘钥校验的闲鱼账号。
            media_type: image、spec_image 或 video。
            file: 上传文件。
        Returns:
            包含 media_id、media_type、文件名和字节数的数据。
        Raises:
            ExternalPublishMediaError: 上传文件校验或落盘失败时抛出。
        """
        normalized_type = self._normalize_media_type(media_type)
        media_id = f"{normalized_type}_{uuid.uuid4().hex}"
        media_dir = self._media_dir(account, normalized_type)
        media_dir.mkdir(parents=True, exist_ok=True)

        try:
            if normalized_type == "video":
                filepath, _, size = await save_uploaded_video(file, media_dir)
            else:
                filepath, _, content = await save_uploaded_image(file, media_dir)
                size = len(content)
        except (ImageUploadError, VideoUploadError) as exc:
            raise ExternalPublishMediaError(exc.message) from exc
        except OSError as exc:
            raise ExternalPublishMediaError(f"保存媒体文件失败：{exc}") from exc

        target_path = media_dir / f"{media_id}{filepath.suffix.lower()}"
        try:
            filepath.replace(target_path)
        except OSError as exc:
            raise ExternalPublishMediaError(f"保存媒体文件失败：{exc}") from exc
        return {
            "media_id": media_id,
            "media_type": normalized_type,
            "name": target_path.name,
            "size": size,
        }

    def resolve_media(
        self,
        account: XYAccount,
        media_id: str,
        expected_type: str,
    ) -> str:
        """
        按账号和预期类型解析 media_id 对应的静态地址。

        Args:
            account: 已通过秘钥校验的闲鱼账号。
            media_id: 公开上传接口返回的媒体 ID。
            expected_type: 发布字段允许的媒体类型。
        Returns:
            可传给闲鱼发布器的 /static/ 相对地址。
        Raises:
            ExternalPublishMediaError: 媒体 ID 非法、类型不匹配或不属于指定账号时抛出。
        """
        normalized_id = media_id.strip().lower()
        match = MEDIA_ID_PATTERN.fullmatch(normalized_id)
        if not match:
            raise ExternalPublishMediaError("media_id格式不正确")
        actual_type = match.group(1)
        if actual_type != expected_type:
            raise ExternalPublishMediaError(f"media_id必须是{expected_type}类型")

        media_dir = self._media_dir(account, actual_type)
        files = [path for path in media_dir.glob(f"{normalized_id}.*") if path.is_file()]
        if len(files) != 1:
            raise ExternalPublishMediaError("media_id不存在、不属于该闲鱼账号或已失效")
        return self._static_url(files[0])

    def resolve_media_list(
        self,
        account: XYAccount,
        media_ids: list[str],
        expected_type: str,
    ) -> list[str]:
        """
        批量解析媒体 ID 并拒绝重复引用。

        Args:
            account: 已通过秘钥校验的闲鱼账号。
            media_ids: 媒体 ID 列表。
            expected_type: 发布字段允许的媒体类型。
        Returns:
            对应的静态地址列表。
        Raises:
            ExternalPublishMediaError: 包含重复或无效媒体 ID 时抛出。
        """
        normalized_ids = [value.strip().lower() for value in media_ids]
        if len(set(normalized_ids)) != len(normalized_ids):
            raise ExternalPublishMediaError("同一媒体不能重复引用")
        return [self.resolve_media(account, media_id, expected_type) for media_id in normalized_ids]


__all__ = ["ExternalPublishMediaError", "ExternalPublishMediaService"]
