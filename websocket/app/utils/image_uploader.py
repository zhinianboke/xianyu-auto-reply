"""
图片上传器

负责将图片上传到闲鱼CDN
"""
from __future__ import annotations

import json
import os
import tempfile
from io import BytesIO
from typing import Optional

import aiohttp
from loguru import logger
from PIL import Image


class ImageUploader:
    """图片上传器 - 上传图片到闲鱼CDN"""
    
    def __init__(self, cookies_str: str):
        self.cookies_str = cookies_str
        self.upload_url = "https://stream-upload.goofish.com/api/upload.api?floderId=0&appkey=xy_chat&_input_charset=utf-8"
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def create_session(self):
        """创建HTTP会话"""
        if not self.session:
            connector = aiohttp.TCPConnector(limit=100, limit_per_host=30)
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            )
    
    async def close_session(self):
        """关闭HTTP会话"""
        if self.session:
            await self.session.close()
            self.session = None
    
    def _compress_image(
        self,
        image_path: str,
        max_size: int = 5 * 1024 * 1024,
        quality: int = 85,
    ) -> Optional[str]:
        """压缩图片"""
        try:
            with Image.open(image_path) as img:
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
                original_width, original_height = img.size
                max_dimension = 1920
                if original_width > max_dimension or original_height > max_dimension:
                    if original_width > original_height:
                        new_width = max_dimension
                        new_height = int((original_height * max_dimension) / original_width)
                    else:
                        new_height = max_dimension
                        new_width = int((original_width * max_dimension) / original_height)
                    
                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    logger.info(f"图片尺寸调整: {original_width}x{original_height} -> {new_width}x{new_height}")
                
                # 创建临时文件
                temp_fd, temp_path = tempfile.mkstemp(suffix='.jpg')
                os.close(temp_fd)
                
                # 保存压缩后的图片
                img.save(temp_path, 'JPEG', quality=quality, optimize=True)
                
                # 检查文件大小
                file_size = os.path.getsize(temp_path)
                if file_size > max_size:
                    quality = max(30, quality - 20)
                    img.save(temp_path, 'JPEG', quality=quality, optimize=True)
                    file_size = os.path.getsize(temp_path)
                    logger.info(f"图片质量调整为 {quality}%，文件大小: {file_size / 1024:.1f}KB")
                
                logger.info(f"图片压缩完成: {file_size / 1024:.1f}KB")
                return temp_path
                
        except Exception as e:
            logger.error(f"图片压缩失败: {e}")
            return None
    
    async def upload_image(self, image_path: str) -> Optional[str]:
        """上传图片到闲鱼CDN"""
        import uuid
        
        temp_path = None
        try:
            if not self.session:
                await self.create_session()
            
            temp_path = self._compress_image(image_path)
            if not temp_path:
                logger.error("图片压缩失败")
                return None
            
            with open(temp_path, 'rb') as f:
                image_data = f.read()
            
            # 使用短随机文件名
            short_uuid = uuid.uuid4().hex[:12]
            filename = f"img_{short_uuid}.jpg"
            
            headers = {
                'cookie': self.cookies_str,
                'Referer': 'https://www.goofish.com/',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'x-requested-with': 'XMLHttpRequest',
                'Accept': 'application/json, text/javascript, */*; q=0.01',
            }
            
            data = aiohttp.FormData()
            data.add_field('file', image_data, filename=filename, content_type='image/jpeg')
            
            logger.info(f"开始上传图片到闲鱼CDN: {filename}")
            async with self.session.post(self.upload_url, data=data, headers=headers) as response:
                if response.status == 200:
                    response_text = await response.text()
                    logger.debug(f"上传响应: {response_text}")
                    
                    image_url = self._parse_upload_response(response_text)
                    if image_url:
                        logger.info(f"图片上传成功: {image_url}")
                        return image_url
                    else:
                        logger.error("解析上传响应失败")
                        return None
                else:
                    logger.error(f"图片上传失败: HTTP {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"图片上传异常: {e}")
            return None
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
    
    def _parse_upload_response(self, response_text: str) -> Optional[str]:
        """解析上传响应获取图片URL"""
        try:
            if '<!DOCTYPE html>' in response_text or '<html>' in response_text:
                logger.error("图片上传失败：Cookie已失效")
                return None
            
            response_data = json.loads(response_text)
            
            if 'data' in response_data and 'url' in response_data['data']:
                return response_data['data']['url']
            
            if 'object' in response_data and isinstance(response_data['object'], dict):
                obj = response_data['object']
                if 'url' in obj:
                    return obj['url']

            if 'url' in response_data:
                return response_data['url']

            if 'result' in response_data and 'url' in response_data['result']:
                return response_data['result']['url']

            if 'data' in response_data and isinstance(response_data['data'], dict):
                data = response_data['data']
                if 'fileUrl' in data:
                    return data['fileUrl']
                if 'file_url' in data:
                    return data['file_url']
            
            logger.error(f"无法从响应中提取图片URL: {response_data}")
            return None
            
        except json.JSONDecodeError:
            logger.error(f"响应不是有效的JSON格式: {response_text[:200]}...")
            return None
        except Exception as e:
            logger.error(f"解析上传响应异常: {e}")
            return None
    
    async def __aenter__(self):
        await self.create_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close_session()
