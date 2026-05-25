from __future__ import annotations

import asyncio
import json
import re
from urllib.parse import parse_qs, urlparse
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from loguru import logger

from app.services.search.browser import BrowserManager, PLAYWRIGHT_AVAILABLE
from app.services.search.parser import ItemParser
from app.services.search.slider_handler import SliderHandler


@dataclass(frozen=True)
class GoofishCompassConfig:
    headless: bool = True
    detail_concurrency: int = 3
    navigation_timeout_ms: int = 30000
    network_idle_timeout_ms: int = 15000
    detail_response_timeout_ms: int = 7000


class GoofishCompassService:
    """
    使用 Playwright 通过关键词搜索 Goofish，并可选抓取二级页面（商品详情）数据。
    """

    SEARCH_INPUT_SELECTORS = [
        'input[class*="search-input"]',
        'input[placeholder*="搜索"]',
        'input[placeholder*="搜"]',
        'input[type="text"]',
        ".search-input",
        "#search-input",
    ]

    NEXT_PAGE_SELECTORS = [
        ".search-page-tiny-arrow-right--oXVFaRao",
        '[class*="search-page-tiny-arrow-right"]',
        'button[aria-label="下一页"]',
        'button:has-text("下一页")',
        'a:has-text("下一页")',
        ".ant-pagination-next",
        "li.ant-pagination-next a",
        'a[aria-label="下一页"]',
    ]

    # Goofish 搜索接口存在不同版本/路径变体，使用关键字做宽松匹配
    SEARCH_API_URL_HINTS = (
        "mtop.taobao.idlemtopsearch",
        "idlemtopsearch",
    )
    MTOP_API_URL_HINTS = ("/h5/mtop.", "/h5/mtop", "mtop.")

    DETAIL_API_URL_HINTS = (
        "mtop.taobao.idle.detail",
        "mtop.taobao.idle.item.detail",
        "mtop.taobao.idle.item.pc.detail",
        "mtop.taobao.idlemtopdetail",
        "idlemtopdetail",
        "idle.detail",
        "detail",
        "item.detail",
    )

    def __init__(
        self,
        *,
        user_id: str,
        cookie_value: str,
        config: GoofishCompassConfig | None = None,
    ) -> None:
        self.user_id = user_id
        self.cookie_value = cookie_value
        self.config = config or GoofishCompassConfig()

        self.browser = BrowserManager()
        self.parser = ItemParser()
        self.slider_handler = SliderHandler(user_id)

        self._items: list[dict[str, Any]] = []
        self._api_total_available: int | None = None
        self._search_response_seen: bool = False
        self._search_error: str | None = None

    @classmethod
    def _is_search_api_url(cls, url: str) -> bool:
        return any(hint in (url or "") for hint in cls.SEARCH_API_URL_HINTS)

    @classmethod
    def _is_mtop_api_url(cls, url: str) -> bool:
        u = url or ""
        return any(h in u for h in cls.MTOP_API_URL_HINTS)

    @classmethod
    def _is_detail_api_url(cls, url: str) -> bool:
        u = url or ""
        if not cls._is_mtop_api_url(u):
            return False
        return any(hint in u for hint in cls.DETAIL_API_URL_HINTS)

    @staticmethod
    def _extract_item_id_from_url(url: str) -> str | None:
        if not url:
            return None
        try:
            parsed = urlparse(url)
            q = parse_qs(parsed.query or "")
            for key in ("id", "item_id", "itemId"):
                val = q.get(key)
                if val and val[0]:
                    return str(val[0]).strip()
        except Exception:
            pass

        m = re.search(r"(?:\\?|&)id=(\\d+)", url)
        if m:
            return m.group(1)
        m = re.search(r"/item/(\\d+)", url)
        if m:
            return m.group(1)
        return None

    @classmethod
    def _canonical_item_url(cls, item_id: str) -> str:
        return f"https://www.goofish.com/item?id={item_id}"

    @classmethod
    def _normalize_item_url(cls, *, item: dict[str, Any]) -> str:
        raw_url = str(item.get("item_url") or "").strip()
        item_id = str(item.get("item_id") or "").strip()

        if item_id:
            return cls._canonical_item_url(item_id)

        if raw_url.startswith("fleamarket://"):
            extracted = cls._extract_item_id_from_url(raw_url)
            if extracted:
                return cls._canonical_item_url(extracted)
            return ""

        extracted = cls._extract_item_id_from_url(raw_url)
        if extracted:
            return cls._canonical_item_url(extracted)
        return raw_url

    async def _on_search_response(self, response: Any) -> None:
        url = getattr(response, "url", "") or ""
        if not self._is_search_api_url(url):
            return

        try:
            if getattr(response, "status", 0) != 200:
                logger.warning(f"Search API status not OK: {response.status}")
                return

            try:
                result_json = await response.json()
            except Exception:
                logger.warning("Failed to parse search API JSON")
                return

            self._search_response_seen = True

            ret = (result_json or {}).get("ret")
            if isinstance(ret, list) and ret:
                non_success = [str(x) for x in ret if x and not str(x).startswith("SUCCESS")]
                if non_success:
                    self._search_error = "; ".join(non_success[:3])

            data = (result_json or {}).get("data") or {}
            if isinstance(data, dict):
                data_error = data.get("errorMsg") or data.get("error_message") or data.get("message")
                if data_error and not self._search_error:
                    self._search_error = str(data_error)

            total_available = (
                data.get("total")
                or data.get("totalResults")
                or data.get("totalCount")
                or data.get("total_count")
            )
            if isinstance(total_available, int):
                self._api_total_available = total_available
            elif isinstance(total_available, str) and total_available.isdigit():
                self._api_total_available = int(total_available)

            items = data.get("resultList")
            if not isinstance(items, list):
                candidate = self._deep_find_first(data, {"resultList", "itemList", "items", "list", "dataList"})
                items = candidate if isinstance(candidate, list) else []
            if not isinstance(items, list) or not items:
                return

            parsed_items = await self.parser.parse_items_batch(items)
            if items and not parsed_items and not self._search_error:
                self._search_error = "搜索接口返回存在结果，但解析失败（可能页面/接口结构已变更）"
            self._items.extend(parsed_items)
        except Exception as exc:
            logger.warning(f"Search response handler error: {exc}")

    async def _collect_search_responses(self, *, timeout_ms: int) -> None:
        if not self.browser.page or timeout_ms <= 0:
            return

        loop = asyncio.get_running_loop()
        deadline = loop.time() + (timeout_ms / 1000.0)
        while True:
            remaining_ms = int((deadline - loop.time()) * 1000)
            if remaining_ms <= 0:
                return
            try:
                resp = await self.browser.page.wait_for_response(
                    lambda r: self._is_search_api_url(getattr(r, "url", "") or ""),
                    timeout=remaining_ms,
                )
                await self._on_search_response(resp)
            except Exception:
                return

    async def _find_search_input(self) -> Any:
        if not self.browser.page:
            return None

        for selector in self.SEARCH_INPUT_SELECTORS:
            try:
                element = await self.browser.page.wait_for_selector(selector, timeout=5000)
                if element:
                    return element
            except Exception:
                continue
        return None

    async def _click_next_page(self, page_num: int) -> bool:
        if not self.browser.page:
            return False

        await asyncio.sleep(1)
        before_count = len(self._items)

        for selector in self.NEXT_PAGE_SELECTORS:
            try:
                next_button = self.browser.page.locator(selector).first
                if not await next_button.is_visible(timeout=3000):
                    continue

                is_disabled = await next_button.get_attribute("disabled")
                has_disabled_class = await next_button.evaluate(
                    "el => el.classList.contains('ant-pagination-disabled') || el.classList.contains('disabled')"
                )
                if is_disabled or has_disabled_class:
                    continue

                await next_button.scroll_into_view_if_needed()
                await asyncio.sleep(0.5)
                await next_button.click()
                await self.browser.wait_for_network_idle(timeout=self.config.network_idle_timeout_ms)
                await self._collect_search_responses(timeout_ms=min(3000, int(self.config.network_idle_timeout_ms)))
                await asyncio.sleep(1.5)

                after_count = len(self._items)
                if after_count > before_count:
                    logger.info(f"Fetched page {page_num}, +{after_count - before_count} items")
                    return True
                return False
            except Exception:
                continue

        return False

    @staticmethod
    def _dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for item in items:
            item_id = str(item.get("item_id") or "")
            if not item_id or item_id in seen:
                continue
            seen.add(item_id)
            deduped.append(item)
        return deduped

    @staticmethod
    def _parse_cn_number(value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if not isinstance(value, str):
            return None
        s = value.strip()
        if not s:
            return None
        s = s.replace(",", "")
        m = re.match(r"^(\d+(?:\.\d+)?)(?:\s*)(万|w|W)?$", s)
        if not m:
            digits = re.findall(r"\d+(?:\.\d+)?", s)
            if not digits:
                return None
            num = float(digits[0])
            if ("万" in s) or ("w" in s.lower()):
                num *= 10000
            return int(num)
        num = float(m.group(1))
        if (m.group(2) or "") in ("万", "w", "W"):
            num *= 10000
        return int(num)

    @staticmethod
    def _deep_find_first(obj: Any, keys: set[str]) -> Any:
        stack: list[Any] = [obj]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                for k, v in cur.items():
                    if k in keys and v not in (None, "", [], {}):
                        return v
                    stack.append(v)
            elif isinstance(cur, list):
                stack.extend(cur)
        return None

    @staticmethod
    def _normalize_price_text(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return f"¥{value:g}"
        if isinstance(value, str):
            s = re.sub(r"\s+", "", value)
            if not s:
                return None
            if s.startswith(("¥", "￥")):
                s = "¥" + s.lstrip("¥￥")
            elif re.match(r"^\d+(?:\.\d+)?$", s):
                s = f"¥{s}"
            return s
        if isinstance(value, list):
            parts: list[str] = []
            for v in value:
                if isinstance(v, dict) and "text" in v:
                    t = str(v.get("text") or "")
                    if t:
                        parts.append(t)
                elif isinstance(v, str):
                    parts.append(v)
            return GoofishCompassService._normalize_price_text("".join(parts))
        if isinstance(value, dict):
            for k in ("text", "priceText", "price_text", "value", "amount", "price", "currentPrice"):
                if k in value and value.get(k) not in (None, "", [], {}):
                    return GoofishCompassService._normalize_price_text(value.get(k))
        return None

    @classmethod
    def _extract_detail_from_payloads(cls, payloads: list[dict[str, Any]]) -> dict[str, Any]:
        if not payloads:
            return {}

        # pick the "best" payload: prefer having nested data
        best = payloads[-1]
        for payload in reversed(payloads):
            if isinstance(payload, dict) and payload.get("data"):
                best = payload
                break

        data = best.get("data") if isinstance(best, dict) else None
        if not isinstance(data, dict):
            data = best

        description = cls._deep_find_first(
            data,
            {
                "desc",
                "description",
                "itemDesc",
                "item_desc",
                "detail",
                "content",
                "text",
            },
        )
        if isinstance(description, dict):
            description = None
        if isinstance(description, list):
            description = None

        price_value = cls._deep_find_first(
            data,
            {
                "price",
                "currentPrice",
                "current_price",
                "sellPrice",
                "sell_price",
                "itemPrice",
                "item_price",
                "auctionPrice",
                "auction_price",
                "priceText",
                "price_text",
                "rawPrice",
                "raw_price",
            },
        )

        view_value = cls._deep_find_first(
            data,
            {
                "viewCount",
                "view_count",
                "browseCount",
                "browse_count",
                "pv",
                "pageView",
                "page_view",
                "readCount",
            },
        )
        want_value = cls._deep_find_first(
            data,
            {"wantCount", "want_count", "wantNum", "want_num", "likeCount", "like_count"},
        )

        view_count = cls._parse_cn_number(view_value)
        want_count = cls._parse_cn_number(want_value)
        price_text = cls._normalize_price_text(price_value)

        result: dict[str, Any] = {}
        if isinstance(description, str):
            desc_clean = re.sub(r"\s+", " ", description).strip()
            if desc_clean:
                result["description"] = desc_clean
        if price_text:
            result["price"] = price_text
        if view_count is not None:
            result["view_count"] = view_count
        if want_count is not None:
            result["want_count"] = want_count
        return result

    async def _extract_detail_from_dom(self, page: Any) -> dict[str, Any]:
        """
        Best-effort DOM extraction for detail fields when MTOP payload is missing/blocked.
        """
        result: dict[str, Any] = {}

        # 1) JSON-LD (structured data)
        try:
            scripts = page.locator('script[type="application/ld+json"]')
            count = await scripts.count()
            for i in range(min(int(count or 0), 6)):
                raw = await scripts.nth(i).text_content()
                if not raw:
                    continue
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                except Exception:
                    continue

                candidates: list[Any] = []
                if isinstance(data, list):
                    candidates.extend(data)
                else:
                    candidates.append(data)

                for obj in candidates:
                    if not isinstance(obj, dict):
                        continue
                    if "description" in obj and isinstance(obj.get("description"), str):
                        desc = re.sub(r"\s+", " ", obj["description"]).strip()
                        if desc:
                            result.setdefault("description", desc[:5000])
                    offers = obj.get("offers")
                    if isinstance(offers, dict):
                        price = offers.get("price") or offers.get("lowPrice") or offers.get("highPrice")
                        price_text = self._normalize_price_text(price)
                        if price_text:
                            result.setdefault("price", price_text)
        except Exception:
            pass

        # 2) Meta description
        try:
            meta_desc = await page.locator('meta[name="description"]').get_attribute("content")
            if meta_desc and isinstance(meta_desc, str):
                meta_desc = re.sub(r"\s+", " ", meta_desc).strip()
                if meta_desc:
                    result.setdefault("description", meta_desc[:5000])
        except Exception:
            pass

        # 3) Body text regex
        try:
            body_text = await page.locator("body").inner_text()
            if isinstance(body_text, str) and body_text:
                body_text = re.sub(r"\s+", " ", body_text)
                body_text = body_text[:20000]

                if "price" not in result:
                    m = re.search(r"(?:售价|价格|卖价|现价)[:：]?\s*([¥￥]?\s*\d+(?:\.\d+)?)", body_text)
                    if not m:
                        m = re.search(r"([¥￥]\s*\d+(?:\.\d+)?)", body_text)
                    if m:
                        price_text = self._normalize_price_text(m.group(1))
                        if price_text:
                            result["price"] = price_text

                if "want_count" not in result:
                    m = re.search(r"(\d+(?:\.\d+)?\s*万?)\s*人想要", body_text)
                    if m:
                        want = self._parse_cn_number(m.group(0))
                        if want is not None:
                            result["want_count"] = want

                if "view_count" not in result:
                    m = re.search(r"(?:浏览量|浏览)[:：]?\s*(\d+(?:\.\d+)?\s*万?)", body_text)
                    if not m:
                        m = re.search(r"(\d+(?:\.\d+)?\s*万?)\s*(?:浏览量|浏览)", body_text)
                    if m:
                        view = self._parse_cn_number(m.group(0))
                        if view is not None:
                            result["view_count"] = view
        except Exception:
            pass

        return result

    async def _fetch_single_detail(self, item: dict[str, Any]) -> dict[str, Any]:
        if not self.browser.context:
            return {}

        item_url = self._normalize_item_url(item=item)
        if not item_url:
            return {}

        detail_payloads: list[dict[str, Any]] = []

        page = await self.browser.context.new_page()

        async def on_response(resp: Any) -> None:
            url = getattr(resp, "url", "")
            if not self._is_detail_api_url(url):
                return
            try:
                if getattr(resp, "status", 0) != 200:
                    return
                payload = await resp.json()
                if isinstance(payload, dict):
                    detail_payloads.append(payload)
            except Exception:
                return

        page.on("response", on_response)

        async def collect_detail_responses(*, timeout_ms: int) -> None:
            if timeout_ms <= 0:
                return
            loop = asyncio.get_running_loop()
            deadline = loop.time() + (timeout_ms / 1000.0)
            while True:
                remaining_ms = int((deadline - loop.time()) * 1000)
                if remaining_ms <= 0:
                    return
                try:
                    resp = await page.wait_for_response(
                        lambda r: self._is_detail_api_url(getattr(r, "url", "") or ""),
                        timeout=remaining_ms,
                    )
                    await on_response(resp)
                except Exception:
                    return

        try:
            await page.goto(item_url, timeout=self.config.navigation_timeout_ms, wait_until="domcontentloaded")
            try:
                await page.wait_for_load_state("networkidle", timeout=self.config.network_idle_timeout_ms)
            except Exception:
                pass

            # Give the page a chance to request detail APIs early.
            await collect_detail_responses(timeout_ms=min(2500, int(self.config.detail_response_timeout_ms)))
            await asyncio.sleep(0.5)

            captcha_ok = await self.slider_handler.handle_verification(
                page=page,
                context=self.browser.context,
                max_retries=3,
                allow_manual=not bool(self.config.headless),
            )
            if not captcha_ok:
                return {"detail_error": "captcha_failed"}

            # After captcha, some pages re-trigger API calls.
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=8000)
            except Exception:
                pass
            await collect_detail_responses(timeout_ms=int(self.config.detail_response_timeout_ms))
            await asyncio.sleep(0.5)

            detail = self._extract_detail_from_payloads(detail_payloads)
            dom_detail: dict[str, Any] = {}
            if (
                not detail
                or detail.get("description") in (None, "")
                or detail.get("price") in (None, "")
                or detail.get("view_count") is None
                or detail.get("want_count") is None
            ):
                dom_detail = await self._extract_detail_from_dom(page)

            if dom_detail:
                merged = dict(detail or {})
                for k, v in dom_detail.items():
                    if v in (None, "", [], {}):
                        continue
                    if merged.get(k) in (None, "", 0, [], {}):
                        merged[k] = v
                detail = merged

            if detail:
                return detail

            # DOM fallback (best-effort)
            try:
                content = await page.content()
                text = re.sub(r"<[^>]+>", " ", content)
                text = re.sub(r"\s+", " ", text).strip()
                if text:
                    return {"description": text[:300], "detail_error": "detail_api_not_captured"}
            except Exception:
                return {}
            return {"detail_error": "detail_not_found"}
        finally:
            try:
                await page.close()
            except Exception:
                pass

    async def search(
        self,
        *,
        keyword: str,
        start_page: int = 1,
        pages: int = 1,
        page_size: int = 20,
        fetch_detail: bool = True,
        detail_limit: int = 20,
    ) -> dict[str, Any]:
        if not PLAYWRIGHT_AVAILABLE:
            return {"items": [], "total": 0, "error": "Playwright 不可用"}

        if not keyword.strip():
            return {"items": [], "total": 0, "error": "关键词不能为空"}

        pages = max(1, min(int(pages), 10))
        start_page = max(1, min(int(start_page), 50))
        page_size = max(1, min(int(page_size), 50))
        detail_limit = max(0, min(int(detail_limit), 50))

        try:
            await self.browser.init_browser(headless=self.config.headless)
            self._items = []
            self._api_total_available = None
            self._search_response_seen = False
            self._search_error = None

            await self.browser.navigate_to("https://www.goofish.com", timeout=self.config.navigation_timeout_ms)
            await self.browser.set_cookies(self.cookie_value)

            if self.browser.page:
                await self.browser.page.reload()
            await self.browser.wait_for_network_idle(timeout=self.config.network_idle_timeout_ms)

            search_input = await self._find_search_input()
            if not search_input:
                return {"items": [], "total": 0, "error": "未找到搜索框"}

            if self.browser.page:
                self.browser.page.on("response", self._on_search_response)

            await search_input.fill(keyword.strip())
            await self.browser.click('button[type="submit"]')
            await self.browser.wait_for_network_idle(timeout=self.config.network_idle_timeout_ms)
            await self._collect_search_responses(timeout_ms=min(3000, int(self.config.network_idle_timeout_ms)))
            await asyncio.sleep(2)

            captcha_ok = await self.slider_handler.handle_verification(
                page=self.browser.page,
                context=self.browser.context,
                max_retries=5,
                allow_manual=not bool(self.config.headless),
            )
            if not captcha_ok:
                return {"items": [], "total": 0, "error": "滑块验证失败（建议在账号管理中开启“显示浏览器”后重试）"}

            # jump to start_page
            current_page = 1
            while current_page < start_page:
                current_page += 1
                ok = await self._click_next_page(current_page)
                if not ok:
                    break

            # fetch additional pages
            for extra in range(1, pages):
                current_page += 1
                ok = await self._click_next_page(current_page)
                if not ok:
                    break

            items = self._dedupe_items(self._items)

            if not items and self._search_error:
                return {"items": [], "total": 0, "error": str(self._search_error)}

            if not items and not self._search_response_seen:
                return {
                    "items": [],
                    "total": 0,
                    "error": "未捕获到搜索接口返回（可能 Cookie 失效/被风控/页面结构变更）",
                }

            # best-effort: keep current page_size expectation in case API returns more
            if page_size and len(items) > page_size * pages:
                items = items[: page_size * pages]

            # fetch details
            if fetch_detail and detail_limit > 0 and items:
                sem = asyncio.Semaphore(max(1, int(self.config.detail_concurrency)))

                async def guarded(item: dict[str, Any]) -> tuple[str, dict[str, Any]]:
                    item_id = str(item.get("item_id") or "")
                    async with sem:
                        try:
                            detail = await self._fetch_single_detail(item)
                            return item_id, detail
                        except Exception as exc:
                            return item_id, {"detail_error": str(exc)}

                detail_targets = items[:detail_limit]
                pairs = await asyncio.gather(*(guarded(it) for it in detail_targets))
                detail_map = {item_id: detail for item_id, detail in pairs if item_id}

                for item in items:
                    item_id = str(item.get("item_id") or "")
                    detail = detail_map.get(item_id)
                    if detail:
                        # want_count 优先使用详情页（如果有）
                        if detail.get("want_count") is not None:
                            item["want_count"] = detail["want_count"]
                        item.update(detail)

            return {
                "items": items,
                "total": len(items),
                "total_available": self._api_total_available,
                "is_real_data": True,
                "source": "playwright",
            }
        except Exception as exc:
            logger.exception("Goofish compass search failed")
            return {"items": [], "total": 0, "error": str(exc)}
        finally:
            await self.browser.close_browser()
