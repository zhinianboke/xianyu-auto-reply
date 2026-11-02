#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成闲鱼风格 favicon 图标（浏览器地址栏/标签页小图标）"""

from PIL import Image, ImageDraw, ImageFont
import os

OUTPUT_PATH = "/workspace/qrcode-generator/favicon.png"
SIZE = 64  # favicon 尺寸（64x64，浏览器会自动缩放）

def create_favicon():
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 圆角半径
    radius = int(SIZE * 0.22)

    # 创建黄橙渐变
    gradient = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    grad_draw = ImageDraw.Draw(gradient)
    for i in range(SIZE):
        ratio = i / SIZE
        r = int(255 * (1 - ratio) + 255 * ratio)
        g = int(216 * (1 - ratio) + 138 * ratio)
        b = int(61 * (1 - ratio) + 0 * ratio)
        grad_draw.line([(0, i), (SIZE, i)], fill=(r, g, b, 255))

    # 圆角蒙版
    mask = Image.new("L", (SIZE, SIZE), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([0, 0, SIZE, SIZE], radius=radius, fill=255)

    # 粘贴渐变（带圆角蒙版）
    img.paste(gradient, (0, 0), mask)

    # 鱼形图标
    try:
        font_size = int(SIZE * 0.55)
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
    text_x = (SIZE - text_w) / 2 - bbox[0]
    text_y = (SIZE - text_h) / 2 - bbox[1]
    draw.text((text_x, text_y), text, fill=(255, 255, 255, 255), font=font)

    # 保存为 PNG
    img.save(OUTPUT_PATH, "PNG")
    print(f"✅ Favicon 已生成：{OUTPUT_PATH}（{SIZE}x{SIZE}）")

if __name__ == "__main__":
    create_favicon()
