"""
买家信用度检查规则

功能：
1. 调用闲鱼评价接口检查买家被评价总数
2. 评价数 <= 阈值（默认0）时命中拦截
"""
from __future__ import annotations

import asyncio
import json
import time

import aiohttp
from loguru import logger

from app.services.xianyu.delivery_rules.base_rule import (
    BaseDeliveryRule,
    RuleCheckResult,
)
from app.services.xianyu.delivery_rules.context import DeliveryCheckContext


class BuyerCreditRule(BaseDeliveryRule):
    """买家信用度检查规则：评价数为0（或低于阈值）时拦截"""

    @property
    def rule_code(self) -> str:
        return "buyer_credit_zero"

    @property
    def rule_name(self) -> str:
        return "买家信用度检查"

    @property
    def rule_description(self) -> str:
        return "检查买家被评价总数，评价数为0（或低于设定阈值）时禁止发货"

    @property
    def default_config(self) -> dict:
        return {"threshold": 0}

    async def check(self, context: DeliveryCheckContext) -> RuleCheckResult:
        """检查买家评价数"""
        threshold = context.rule_config.get("threshold", 0)
        pf = context.log_prefix or f"【{context.cookie_id}】"

        total_count = await self._check_buyer_rate_count(
            context.cookies_str, context.buyer_id, context.cookie_id, pf
        )

        # 接口异常（-1）→ 不命中，放行
        if total_count < 0:
            logger.warning(
                f"{pf}[买家信用度规则] 评价接口异常，无法确认 buyer_id={context.buyer_id}，跳过本规则"
            )
            return RuleCheckResult(
                hit=False,
                rule_code=self.rule_code,
                rule_name=self.rule_name,
                extra_data={"total_count": total_count},
            )

        # 评价数 <= 阈值 → 命中
        if total_count <= threshold:
            reason = f"买家评价数为{total_count}（阈值{threshold}），已禁止发货"
            logger.info(
                f"{pf}[买家信用度规则] 命中：buyer_id={context.buyer_id}, "
                f"totalCount={total_count}, threshold={threshold}"
            )
            return RuleCheckResult(
                hit=True,
                rule_code=self.rule_code,
                rule_name=self.rule_name,
                reason=reason,
                extra_data={"total_count": total_count, "threshold": threshold},
            )

        # 评价数 > 阈值 → 不命中
        logger.info(
            f"{pf}[买家信用度规则] 通过：buyer_id={context.buyer_id}, "
            f"totalCount={total_count}, threshold={threshold}"
        )
        return RuleCheckResult(
            hit=False,
            rule_code=self.rule_code,
            rule_name=self.rule_name,
            extra_data={"total_count": total_count},
        )

    async def _check_buyer_rate_count(
        self,
        cookies_str: str,
        buyer_id: str,
        cookie_id: str,
        log_prefix: str,
        retry_count: int = 0,
    ) -> int:
        """调用闲鱼评价接口获取买家被评价总数

        Returns:
            >=0 表示实际评价数，-1 表示接口异常
        """
        max_retry = 3

        if not buyer_id:
            logger.warning(f"{log_prefix}[买家信用度规则] buyer_id 为空，跳过")
            return -1

        if not cookies_str:
            logger.warning(f"{log_prefix}[买家信用度规则] 未提供Cookie，跳过")
            return -1

        try:
            from common.utils.xianyu_utils import trans_cookies, generate_sign

            cookies = trans_cookies(cookies_str)
            timestamp = str(int(time.time() * 1000))
            data_payload = {
                "rateType": 0,
                "ratedUid": str(buyer_id),
                "raterType": 0,
                "rowsPerPage": 20,
                "pageNumber": 1,
                "foldFlag": 0,
                "fishAdCode": "330110",
                "extraTag": "",
            }
            data_val = json.dumps(data_payload, separators=(",", ":"), ensure_ascii=False)

            token = cookies.get("_m_h5_tk", "").split("_")[0] if cookies.get("_m_h5_tk") else ""
            sign = generate_sign(timestamp, token, data_val)

            params = {
                "jsv": "2.7.2",
                "appKey": "34839810",
                "t": timestamp,
                "sign": sign,
                "v": "1.0",
                "type": "originaljson",
                "accountSite": "xianyu",
                "dataType": "json",
                "timeout": "20000",
                "api": "mtop.idle.web.trade.rate.list",
                "sessionOption": "AutoLoginOnly",
                "spm_cnt": "a21ybx.personal.0.0",
            }

            headers = {
                "accept": "application/json",
                "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
                "cache-control": "no-cache",
                "content-type": "application/x-www-form-urlencoded",
                "pragma": "no-cache",
                "origin": "https://www.goofish.com",
                "referer": "https://www.goofish.com/",
                "user-agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/138.0.0.0 Safari/537.36"
                ),
                "cookie": cookies_str.replace("\n", "").replace("\r", ""),
            }

            api_url = "https://h5api.m.goofish.com/h5/mtop.idle.web.trade.rate.list/1.0/"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url,
                    params=params,
                    data={"data": data_val},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as response:
                    res_json = await response.json()
                    ret_list = res_json.get("ret", []) or []

                    if not any("SUCCESS" in ret for ret in ret_list):
                        if retry_count < max_retry - 1:
                            await asyncio.sleep(0.5)
                            return await self._check_buyer_rate_count(
                                cookies_str, buyer_id, cookie_id, log_prefix, retry_count + 1
                            )
                        logger.warning(
                            f"{log_prefix}[买家信用度规则] 接口多次失败：buyer_id={buyer_id}, ret={ret_list}"
                        )
                        return -1

                    data = res_json.get("data") or {}
                    total_count = data.get("totalCount")
                    if total_count is None:
                        return -1

                    try:
                        return int(total_count)
                    except (TypeError, ValueError):
                        return -1

        except asyncio.TimeoutError:
            if retry_count < max_retry - 1:
                await asyncio.sleep(0.5)
                return await self._check_buyer_rate_count(
                    cookies_str, buyer_id, cookie_id, log_prefix, retry_count + 1
                )
            return -1
        except Exception as e:
            if retry_count < max_retry - 1:
                await asyncio.sleep(0.5)
                return await self._check_buyer_rate_count(
                    cookies_str, buyer_id, cookie_id, log_prefix, retry_count + 1
                )
            logger.error(f"{log_prefix}[买家信用度规则] 异常: {e}")
            return -1
