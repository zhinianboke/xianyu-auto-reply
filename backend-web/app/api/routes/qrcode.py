"""公开读取群二维码地址，管理员可以上传替换图片。"""
from typing import Annotated

from fastapi import APIRouter, Depends, File, Response, UploadFile
from loguru import logger
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_current_admin_user
from app.core.qrcode_files import (
    MAX_QRCODE_BYTES,
    NO_STORE,
    QRCODE_TYPES,
    read_qrcode,
    save_qrcode,
)
from common.models.user import User
from common.schemas.common import ApiResponse
from common.utils.local_image_upload import (
    ImageUploadError,
    validate_image_content_type,
)

router = APIRouter(prefix="/qrcode", tags=["群二维码"])


@router.get("/{qrcode_type}")
async def get_qrcode(qrcode_type: str, response: Response) -> ApiResponse:
    """返回指定类型当前生效的公开图片地址。"""
    response.headers.update(NO_STORE)
    if qrcode_type not in QRCODE_TYPES:
        return ApiResponse(success=False, message="无效的二维码类型")

    try:
        image = await run_in_threadpool(read_qrcode, qrcode_type)
    except (OSError, ValueError):
        logger.exception("群二维码读取失败: type={}", qrcode_type)
        return ApiResponse(success=False, message="二维码读取失败，请稍后重试")
    if image is None:
        return ApiResponse(success=False, message="二维码未配置")
    return ApiResponse(success=True, data={"image_url": image.url(qrcode_type)})


@router.post("/{qrcode_type}", response_model=ApiResponse)
async def upload_qrcode(
    qrcode_type: str,
    image: Annotated[UploadFile, File()],
    current_user: Annotated[User, Depends(get_current_admin_user)],
) -> ApiResponse:
    """校验管理员上传的图片，保存成功后返回当前图片地址。"""
    if qrcode_type not in QRCODE_TYPES:
        return ApiResponse(success=False, message="无效的二维码类型")

    try:
        validate_image_content_type(image)
        content = await image.read(MAX_QRCODE_BYTES + 1)
        if len(content) > MAX_QRCODE_BYTES:
            return ApiResponse(success=False, message="图片大小不能超过2MB")
        saved_image = await run_in_threadpool(save_qrcode, qrcode_type, content)
    except ImageUploadError as exc:
        return ApiResponse(success=False, message=exc.message)
    except OSError:
        logger.exception("群二维码上传失败: type={}, user_id={}", qrcode_type, current_user.id)
        return ApiResponse(success=False, message="二维码保存失败，请稍后重试")

    logger.info("群二维码上传成功: type={}, user_id={}", qrcode_type, current_user.id)
    return ApiResponse(success=True, message="上传成功", data={"image_url": saved_image.url(qrcode_type)})
