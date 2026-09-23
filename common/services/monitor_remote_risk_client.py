"""
商品监控 - 远程过风控接口客户端

功能：
1. 按远程过风控服务的接口协议发起请求：请求头 X-API-Key 携带秘钥，请求体传接口类型与滑块链接
2. 解析远程返回的 x5sec 等校验值，供调用方合并进账号 Cookie 后重试采集

接口协议：
    POST <远程URL>
    Headers: {"X-API-Key": "<32位秘钥>", "Content-Type": "application/json"}
    Body:    {"type": "x5sec_ali", "data": {"url": "<淘宝滑块页面完整链接>"}}
    Resp:    {"success": bool, "message": str,
              "data": {"x5sec": str, "bx-pp": str, "bx_et": str}}

说明：
- 使用 aiohttp（各服务均已依赖），避免为定时任务额外引入 HTTP 客户端依赖。
- 远程求解滑块耗时较长，总超时见 REMOTE_RISK_TIMEOUT_SECONDS；超时/网络异常按失败处理，
  由调用方回退原有换号冷却逻辑。
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import aiohttp
from loguru import logger

# 接口类型：固定填写接口编码（淘宝滑块过风控）
REMOTE_RISK_API_TYPE = "x5sec_ali"

# 远程过风控请求总超时（秒）：远程需真实打开滑块页面求解，留足时间。
# 注意商品监控的采集执行是串行加锁的（同一时刻只跑一个采集），单次调用挂太久会拖住后续监控任务，
# 因此这里不用滑块服务默认的 300 秒，取 120 秒折中；确需更久可调大此常量。
REMOTE_RISK_TIMEOUT_SECONDS = 120
# 连接超时（秒）：URL 填错/远程主机不可达时快速失败，不占用整段总超时
REMOTE_RISK_CONNECT_TIMEOUT_SECONDS = 8


async def solve_remote_risk(
    remote_url: str,
    secret_key: str,
    punish_url: str,
    account_id: str = "",
) -> Tuple[Optional[Dict[str, str]], str]:
    """
    调用远程过风控接口求解滑块，返回可合并进 Cookie 的校验值。

    Args:
        remote_url: 远程过风控服务完整地址
        secret_key: 当前用户为该接口生成的 32 位秘钥（放入 X-API-Key 请求头）
        punish_url: 闲鱼/淘宝下发的滑块页面完整链接（punish?x5secdata=...）
        account_id: 触发风控的账号ID，仅用于日志定位
    Returns:
        (cookies, message)
        cookies: 成功时为 {"x5sec": ...} 等待合并的 Cookie 字典；失败为 None
        message: 失败原因（成功时为远程返回的说明或空串）
    """
    url = (remote_url or "").strip()
    key = (secret_key or "").strip()
    target = (punish_url or "").strip()
    if not url or not key:
        return None, "未配置远程过风控服务URL或秘钥"
    if not target:
        return None, "缺少滑块验证链接，无法调用远程过风控"

    headers = {"X-API-Key": key, "Content-Type": "application/json"}
    payload: Dict[str, Any] = {"type": REMOTE_RISK_API_TYPE, "data": {"url": target}}

    try:
        timeout = aiohttp.ClientTimeout(
            total=REMOTE_RISK_TIMEOUT_SECONDS,
            connect=REMOTE_RISK_CONNECT_TIMEOUT_SECONDS,
        )
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                raw_text = await resp.text()
                if resp.status != 200:
                    logger.warning(
                        f"【{account_id}】远程过风控返回异常 HTTP {resp.status}: {raw_text[:300]}"
                    )
                    return None, f"远程过风控服务返回异常（HTTP {resp.status}）"
                try:
                    body = await resp.json(content_type=None)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"【{account_id}】远程过风控响应解析失败: {exc}，原始内容: {raw_text[:300]}")
                    return None, "远程过风控响应解析失败"
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"【{account_id}】远程过风控调用失败: {exc}")
        return None, f"远程过风控调用失败: {exc}"

    if not isinstance(body, dict):
        return None, "远程过风控响应格式不正确"

    message = str(body.get("message") or "").strip()
    if not body.get("success"):
        return None, message or "远程过风控未通过"

    data_node = body.get("data") if isinstance(body.get("data"), dict) else {}
    x5sec = str((data_node or {}).get("x5sec") or "").strip()
    if not x5sec:
        return None, message or "远程过风控成功但未返回 x5sec"

    # 远程同时返回的 bx-pp / bx_et 一并合并，缺失则忽略（不同远程实现可能只下发 x5sec）
    cookies: Dict[str, str] = {"x5sec": x5sec}
    for extra_key in ("bx-pp", "bx_et"):
        extra_value = str((data_node or {}).get(extra_key) or "").strip()
        if extra_value:
            cookies[extra_key] = extra_value

    logger.info(f"【{account_id}】远程过风控成功，取得校验值字段: {', '.join(cookies.keys())}")
    return cookies, message


__all__ = [
    "solve_remote_risk",
    "REMOTE_RISK_API_TYPE",
    "REMOTE_RISK_TIMEOUT_SECONDS",
    "REMOTE_RISK_CONNECT_TIMEOUT_SECONDS",
]
