"""
闲鱼登录密码加密（password2）

功能：
1. 复刻闲鱼登录页 JS 的 password2 生成算法（RSA PKCS#1 v1.5 公钥加密）
2. 纯 Python 实现，不依赖浏览器，供协议化账号密码登录使用

说明：
- 公钥模数/指数写死为常量（与登录页 JS 一致）；若闲鱼更新公钥导致登录失败，
  只需替换本文件的 HARD_CODED_MODULUS / HARD_CODED_EXPONENT。
- 算法参照 slider_test/standalone_no_json_login.py 实测验证通过的实现。
"""
from __future__ import annotations

import secrets

# 登录页 JS 内置 RSA 公钥（模数十六进制 + 指数）
HARD_CODED_MODULUS = (
    "d3bcef1f00424f3261c89323fa8cdfa12bbac400d9fe8bb627e8d27a44bd5d59"
    "dce559135d678a8143beb5b8d7056c4e1f89c4e1f152470625b7b41944a97f"
    "02da6f605a49a93ec6eb9cbaf2e7ac2b26a354ce69eb265953d2c29e395d6d8"
    "c1cdb688978551aa0f7521f290035fad381178da0bea8f9e6adce39020f513133fb"
)
HARD_CODED_EXPONENT = "10001"


def _js_string_to_utf8_bytes(s: str) -> bytes:
    """
    模拟登录页 JS 的字符串转 UTF-8 字节逻辑（与 JS 端逐字节一致）

    Args:
        s: 明文密码
    Returns:
        UTF-8 字节序列
    """
    out = bytearray()
    for ch in s:
        c = ord(ch)
        if c < 128:
            out.append(c)
        elif c < 2048:
            out.append((c >> 6) | 192)
            out.append((c & 63) | 128)
        else:
            out.append((c >> 12) | 224)
            out.append(((c >> 6) & 63) | 128)
            out.append((c & 63) | 128)
    return bytes(out)


def generate_password2(
    password: str,
    modulus_hex: str = HARD_CODED_MODULUS,
    exponent_hex: str = HARD_CODED_EXPONENT,
) -> str:
    """
    生成 login.do 所需的 password2（RSA PKCS#1 v1.5 加密后的十六进制串）

    Args:
        password: 明文登录密码
        modulus_hex: RSA 公钥模数（十六进制），默认使用内置公钥
        exponent_hex: RSA 公钥指数（十六进制），默认 10001
    Returns:
        加密后的十六进制字符串（长度为偶数）
    """
    n = int(modulus_hex.strip().lower().removeprefix("0x"), 16)
    e = int(exponent_hex.strip().lower().removeprefix("0x"), 16)
    key_bytes = (n.bit_length() + 7) // 8
    msg = _js_string_to_utf8_bytes(password)
    if key_bytes < len(msg) + 11:
        raise ValueError("密码过长，超出 RSA 公钥可加密长度")

    # PKCS#1 v1.5 填充：0x00 0x02 [非零随机填充] 0x00 [明文]
    ps_len = key_bytes - len(msg) - 3
    ps = bytearray()
    while len(ps) < ps_len:
        b = secrets.randbelow(255) + 1  # 1..255，保证非零
        ps.append(b)
    padded = bytes([0, 2]) + bytes(ps) + bytes([0]) + msg

    c = pow(int.from_bytes(padded, "big"), e, n)
    h = format(c, "x")
    # 补齐为偶数长度（与 JS 端一致）
    return ("0" + h) if len(h) % 2 else h
