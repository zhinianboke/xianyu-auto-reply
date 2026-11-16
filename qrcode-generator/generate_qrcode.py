#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成带闲鱼 logo 的固定二维码
二维码内容固定为跳转页地址，目标链接从后端 API 动态获取
"""

import qrcode
from PIL import Image, ImageDraw, ImageFont
import os

# 二维码内容：固定为跳转页地址（不带参数）
QRCODE_URL = "https://xianyu.jinan.me/redirect.html"

# 输出路径
OUTPUT_PATH = "/workspace/qrcode-generator/xianyu_qrcode_with_logo.png"

def create_xianyu_logo(size):
    """创建闲鱼风格 logo（黄橙渐变圆角方块 + 鱼形 emoji）"""
    logo = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(logo)

    # 白色圆角背景
    radius = int(size * 0.22)
    draw.rounded_rectangle([0, 0, size, size], radius=radius, fill=(255, 255, 255, 255))

    # 黄橙渐变圆角方块
    inner_pad = int(size * 0.10)
    inner_size = size - inner_pad * 2
    inner_radius = int(inner_size * 0.20)

    # 创建渐变
    gradient = Image.new("RGBA", (inner_size, inner_size), (0, 0, 0, 0))
    grad_draw = ImageDraw.Draw(gradient)
    for i in range(inner_size):
        ratio = i / inner_size
        r = int(255 * (1 - ratio) + 255 * ratio)
        g = int(216 * (1 - ratio) + 138 * ratio)
        b = int(61 * (1 - ratio) + 0 * ratio)
        grad_draw.line([(0, i), (inner_size, i)], fill=(r, g, b, 255))

    # 用圆角蒙版裁剪渐变
    mask = Image.new("L", (inner_size, inner_size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([0, 0, inner_size, inner_size], radius=inner_radius, fill=255)

    logo.paste(gradient, (inner_pad, inner_pad), mask)

    # 鱼形 emoji 文字
    try:
        font_size = int(size * 0.50)
        font = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf", font_size)
    except (IOError, OSError):
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
        except (IOError, OSError):
            font = ImageFont.load_default()

    text = "🐟"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    text_x = (size - text_w) / 2 - bbox[0]
    text_y = (size - text_h) / 2 - bbox[1]
    draw.text((text_x, text_y), text, fill=(255, 255, 255, 255), font=font)

    return logo

def generate_qrcode_with_logo():
    # 生成高纠错级别的二维码（H 级别，可遮挡 30%）
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(QRCODE_URL)
    qr.make(fit=True)

    # 生成二维码图片
    qr_img = qr.make_image(fill_color="#1a1a1a", back_color="white").convert("RGB")

    # 计算 logo 尺寸（二维码的 22%）
    qr_size = qr_img.size[0]
    logo_size = int(qr_size * 0.22)

    # 创建闲鱼 logo
    logo = create_xianyu_logo(logo_size)

    # 计算居中位置
    pos = ((qr_size - logo_size) // 2, (qr_size - logo_size) // 2)

    # 白色背景圆角（logo 周围的白色边距）
    bg_size = logo_size + 16
    bg = Image.new("RGBA", (bg_size, bg_size), (255, 255, 255, 0))
    bg_draw = ImageDraw.Draw(bg)
    bg_draw.rounded_rectangle([0, 0, bg_size, bg_size], radius=bg_size // 5, fill=(255, 255, 255, 255))

    # 合并到二维码
    qr_img = qr_img.convert("RGBA")
    bg_pos = ((qr_size - bg_size) // 2, (qr_size - bg_size) // 2)
    qr_img.paste(bg, bg_pos, bg)
    qr_img.paste(logo, pos, logo)

    # 保存
    qr_img = qr_img.convert("RGB")
    qr_img.save(OUTPUT_PATH, quality=95)
    print(f"✅ 二维码已生成：{OUTPUT_PATH}")
    print(f"   尺寸：{qr_size}x{qr_size}")
    print(f"   内容：{QRCODE_URL}")
    print(f"   Logo 尺寸：{logo_size}x{logo_size}")

if __name__ == "__main__":
    generate_qrcode_with_logo()
