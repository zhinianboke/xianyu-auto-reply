"""
群二维码路由

提供群二维码的获取和上传功能
"""
from pathlib import Path

from fastapi import APIRouter, File, UploadFile, Depends
from loguru import logger

from app.api.deps import get_current_admin_user
from common.models.user import User
from common.schemas.common import ApiResponse

router = APIRouter(prefix="/qrcode", tags=["群二维码"])

# 群二维码图片存储目录 - 使用统一的静态文件根目录（兼容Docker共享卷）
from app.core.paths import STATIC_ROOT
QRCODE_DIR = STATIC_ROOT / "qrcode"
QRCODE_DIR.mkdir(parents=True, exist_ok=True)


@router.get("/{qrcode_type}")
async def get_qrcode(qrcode_type: str):
    """
    获取群二维码图片路径（公开接口）
    qrcode_type: wechat、qq 或 wechat_official
    """
    if qrcode_type not in ["wechat", "qq", "wechat_official", "telegram", "reward"]:
        return ApiResponse(success=False, message="无效的二维码类型")
    
    # wechat_official 使用 wechat-official 作为文件名前缀
    file_prefix = qrcode_type.replace("_", "-")
    
    # 查找文件
    for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]:
        filepath = QRCODE_DIR / f"{file_prefix}-group{ext}"
        if filepath.exists():
            return ApiResponse(
                success=True,
                data={"image_url": f"/static/qrcode/{file_prefix}-group{ext}"}
            )
    
    return ApiResponse(success=False, message="二维码未配置")


@router.post("/{qrcode_type}", response_model=ApiResponse)
async def upload_qrcode(
    qrcode_type: str,
    image: UploadFile = File(...),
    current_user: User = Depends(get_current_admin_user)
):
    """
    上传群二维码图片（仅管理员）
    qrcode_type: wechat、qq 或 wechat_official
    """
    if qrcode_type not in ["wechat", "qq", "wechat_official", "telegram", "reward"]:
        return ApiResponse(success=False, message="无效的二维码类型，只支持 wechat、qq、wechat_official、telegram 或 reward")
    
    try:
        # 验证图片文件
        if not image.content_type or not image.content_type.startswith('image/'):
            return ApiResponse(success=False, message="请上传图片文件")
        
        # 读取图片数据
        image_data = await image.read()
        
        # 限制文件大小 2MB
        if len(image_data) > 2 * 1024 * 1024:
            return ApiResponse(success=False, message="图片大小不能超过2MB")
        
        # 获取文件扩展名
        ext = Path(image.filename).suffix.lower() if image.filename else ".png"
        if ext not in [".png", ".jpg", ".jpeg", ".gif", ".webp"]:
            ext = ".png"
        
        # 保存文件，固定文件名
        # wechat_official 使用 wechat-official 作为文件名前缀
        file_prefix = qrcode_type.replace("_", "-")
        filename = f"{file_prefix}-group{ext}"
        filepath = QRCODE_DIR / filename
        
        # 删除旧文件（可能扩展名不同）
        for old_file in QRCODE_DIR.glob(f"{file_prefix}-group.*"):
            old_file.unlink()
        
        # 写入新文件
        with open(filepath, "wb") as f:
            f.write(image_data)
        
        logger.info(f"群二维码上传成功: {filename}, user_id={current_user.id}")
        
        return ApiResponse(
            success=True,
            message="上传成功",
            data={"image_url": f"/static/qrcode/{filename}"}
        )
    except Exception as e:
        logger.error(f"群二维码上传失败: {e}")
        return ApiResponse(success=False, message=f"上传失败: {str(e)}")
