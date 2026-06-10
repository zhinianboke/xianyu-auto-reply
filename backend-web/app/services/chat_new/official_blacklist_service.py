"""闲鱼官方会话黑名单操作（拉黑/取消拉黑/查询）"""
from __future__ import annotations

import json
import time
from typing import Any

import aiohttp

from common.utils.xianyu_utils import generate_sign, trans_cookies


API_VERSIONS = {
    "query": ("mtop.taobao.idlemessage.pc.blacklist.query", "1.0"),
    "add": ("mtop.taobao.idlemessage.pc.blacklist.add", "2.0"),
    "remove": ("mtop.taobao.idlemessage.pc.blacklist.remove", "1.0"),
}


async def official_blacklist_request(cookies_str: str, session_id: str, action: str) -> dict[str, Any]:
    api, version = API_VERSIONS[action]
    data_val = json.dumps({"sessionId": str(session_id)}, separators=(",", ":"))
    timestamp = str(int(time.time() * 1000))
    cookies = trans_cookies(cookies_str)
    token = cookies.get("_m_h5_tk", "").split("_")[0]
    params = {
        "jsv": "2.7.2",
        "appKey": "34839810",
        "t": timestamp,
        "sign": generate_sign(timestamp, token, data_val),
        "v": version,
        "type": "originaljson",
        "accountSite": "xianyu",
        "dataType": "json",
        "timeout": "20000",
        "api": api,
        "sessionOption": "AutoLoginOnly",
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/x-www-form-urlencoded",
        "cookie": cookies_str.replace("\n", "").replace("\r", ""),
        "origin": "https://www.goofish.com",
        "referer": "https://www.goofish.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/146.0.0.0 Safari/537.36",
    }
    url = f"https://h5api.m.goofish.com/h5/{api}/{version}/"
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url, params=params, data={"data": data_val}, headers=headers,
            timeout=aiohttp.ClientTimeout(total=20),
        ) as response:
            result = await response.json()
    ret = result.get("ret", [])
    if not any("SUCCESS" in str(item) for item in ret):
        raise RuntimeError(str(ret[0] if ret else "闲鱼黑名单接口调用失败"))
    return result.get("data", {}) or {}
