"""图片上传路由"""
from pathlib import Path

from fastapi import APIRouter, File, UploadFile, Depends
from loguru import logger

from app.api.deps import get_current_user
from common.models.user import User
from common.schemas.common import ApiResponse
from common.utils.image_utils import image_manager

router = APIRouter(tags=["upload"])


@router.post("/upload-image", response_model=ApiResponse)
async def upload_image(
    image: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """上传图片（用于卡券等功能）"""
    try:
        logger.info(f"接收到图片上传请求: filename={image.filename}, user_id={current_user.id}")

        # 验证图片文件
        if not image.content_type or not image.content_type.startswith('image/'):
            logger.warning(f"无效的图片文件类型: {image.content_type}")
            return ApiResponse(
                success=False,
                message="请上传图片文件"
            )

        # 读取图片数据
        image_data = await image.read()
        logger.info(f"读取图片数据成功，大小: {len(image_data)} bytes")

        # 保存图片
        image_url = image_manager.save_image(image_data, image.filename)
        if not image_url:
            logger.error("图片保存失败")
            return ApiResponse(
                success=False,
                message="图片保存失败"
            )

        logger.info(f"图片上传成功: {image_url}")

        return ApiResponse(
            success=True,
            message="图片上传成功",
            data={"image_url": image_url}
        )

    except Exception as e:
        logger.error(f"图片上传失败: {e}")
        return ApiResponse(
            success=False,
            message=f"图片上传失败: {str(e)}"
        )
