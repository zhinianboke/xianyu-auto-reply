"""
图片处理工具

包含图片保存、压缩、格式转换等功能
"""
from __future__ import annotations

import hashlib
import os
import uuid
from io import BytesIO
from typing import Dict, Optional, Tuple

from loguru import logger
from PIL import Image


class ImageManager:
    """图片管理器，负责图片的保存、压缩和访问"""
    
    def __init__(self, upload_dir: str = None):
        # 优先使用STATIC_DIR环境变量（Docker共享卷），本地回退到相对路径
        if upload_dir is None:
            static_base = os.environ.get("STATIC_DIR", "static")
            upload_dir = os.path.join(static_base, "uploads", "images")
        self.upload_dir = upload_dir
        self.max_size = 5 * 1024 * 1024  # 5MB
        self.max_dimension = 4096  # 最大边长
        self.max_pixels = 8 * 1024 * 1024  # 8M像素
        self.allowed_formats = {'JPEG', 'PNG', 'GIF', 'WEBP'}
        self._ensure_upload_dir()
    
    def _ensure_upload_dir(self):
        """确保上传目录存在"""
        try:
            os.makedirs(self.upload_dir, exist_ok=True)
            logger.info(f"图片上传目录已准备: {self.upload_dir}")
        except Exception as e:
            logger.error(f"创建图片上传目录失败: {e}")
    
    def save_image(self, image_data: bytes, original_filename: str = None) -> Optional[str]:
        """保存图片文件"""
        try:
            logger.info(f"开始保存图片，数据大小: {len(image_data)} bytes")

            if not self._validate_image_data(image_data):
                logger.error("图片数据验证失败")
                return None
            
            file_hash = hashlib.md5(image_data).hexdigest()
            file_extension = self._get_image_extension(image_data)
            filename = f"{file_hash}_{uuid.uuid4().hex[:8]}.{file_extension}"
            file_path = os.path.join(self.upload_dir, filename)
            
            if os.path.exists(file_path):
                logger.info(f"图片文件已存在，跳过保存: {filename}")
                return self._get_relative_path(file_path)
            
            processed_image_data = self._process_image(image_data)
            
            with open(file_path, 'wb') as f:
                f.write(processed_image_data)
            
            logger.info(f"图片保存成功: {filename}")
            return self._get_relative_path(file_path)
            
        except Exception as e:
            logger.error(f"保存图片失败: {e}")
            return None
    
    def _validate_image_data(self, image_data: bytes) -> bool:
        """验证图片数据"""
        try:
            if len(image_data) > self.max_size:
                logger.warning(f"图片文件过大: {len(image_data)} bytes")
                return False
            
            with Image.open(BytesIO(image_data)) as img:
                if img.format not in self.allowed_formats:
                    logger.warning(f"不支持的图片格式: {img.format}")
                    return False
                
                width, height = img.size
                if width > self.max_dimension or height > self.max_dimension:
                    logger.warning(f"图片尺寸过大: {width}x{height}")
                    return False

                total_pixels = width * height
                if total_pixels > self.max_pixels:
                    logger.warning(f"图片像素总数过大: {total_pixels}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"图片验证失败: {e}")
            return False
    
    def _get_image_extension(self, image_data: bytes) -> str:
        """获取图片扩展名"""
        try:
            with Image.open(BytesIO(image_data)) as img:
                format_to_ext = {
                    'JPEG': 'jpg',
                    'PNG': 'png',
                    'GIF': 'gif',
                    'WEBP': 'webp'
                }
                return format_to_ext.get(img.format, 'jpg')
        except Exception:
            return 'jpg'
    
    def _process_image(self, image_data: bytes) -> bytes:
        """处理图片（压缩、调整尺寸等）"""
        try:
            with Image.open(BytesIO(image_data)) as img:
                # 转换为RGB模式
                if img.mode in ('RGBA', 'LA', 'P'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                    img = background
                elif img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # 调整尺寸
                width, height = img.size
                max_output_dimension = 2048

                if width > max_output_dimension or height > max_output_dimension:
                    ratio = min(max_output_dimension / width, max_output_dimension / height)
                    new_width = int(width * ratio)
                    new_height = int(height * ratio)
                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    logger.info(f"图片已调整尺寸: {width}x{height} -> {new_width}x{new_height}")
                
                output = BytesIO()
                img.save(output, format='JPEG', quality=85, optimize=True)
                return output.getvalue()
                
        except Exception as e:
            logger.error(f"图片处理失败: {e}")
            return image_data
    
    def _get_relative_path(self, file_path: str) -> str:
        """获取相对路径（以/开头，确保是绝对URL路径）"""
        rel_path = os.path.relpath(file_path)
        rel_path = rel_path.replace('\\', '/')
        # 确保路径以/开头，避免在子路由页面出现路径解析问题
        if not rel_path.startswith('/'):
            rel_path = '/' + rel_path
        return rel_path
    
    def delete_image(self, image_path: str) -> bool:
        """删除图片文件"""
        try:
            if not image_path.startswith(self.upload_dir):
                full_path = os.path.join(os.getcwd(), image_path)
            else:
                full_path = image_path
            
            if os.path.exists(full_path):
                os.remove(full_path)
                logger.info(f"图片删除成功: {image_path}")
                return True
            else:
                logger.warning(f"图片文件不存在: {image_path}")
                return False
                
        except Exception as e:
            logger.error(f"删除图片失败: {e}")
            return False
    
    def get_image_info(self, image_path: str) -> Optional[Dict]:
        """获取图片信息"""
        try:
            if not image_path.startswith(self.upload_dir):
                full_path = os.path.join(os.getcwd(), image_path)
            else:
                full_path = image_path
            
            if not os.path.exists(full_path):
                return None
            
            with Image.open(full_path) as img:
                return {
                    'width': img.width,
                    'height': img.height,
                    'format': img.format,
                    'mode': img.mode,
                    'size': os.path.getsize(full_path)
                }
                
        except Exception as e:
            logger.error(f"获取图片信息失败: {e}")
            return None

    def get_image_size(self, image_path: str) -> Tuple[Optional[int], Optional[int]]:
        """获取图片尺寸"""
        try:
            info = self.get_image_info(image_path)
            if info:
                return info['width'], info['height']
            return None, None
        except Exception as e:
            logger.error(f"获取图片尺寸失败: {e}")
            return None, None


# 全局图片管理器实例
image_manager = ImageManager()
