"""
商品数据解析器

解析闲鱼API返回的商品数据
"""
from __future__ import annotations

import re
import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from loguru import logger


class ItemParser:
    """商品数据解析器"""

    _ITEM_ID_KEYS = {
        "item_id", "itemid", "item_id_str", "id", "auctionid", "auction_id",
        "productid", "product_id", "offerid", "offer_id",
    }
    _TITLE_KEYS = {"title", "raw_title", "itemtitle", "item_title", "name", "subject"}
    _PRICE_KEYS = {
        "price", "pricetext", "price_text", "displayprice", "display_price",
        "soldprice", "sold_price", "viewprice", "view_price", "currentprice",
    }
    _URL_KEYS = {
        "item_url", "itemurl", "targeturl", "target_url", "url", "detailurl",
        "detail_url", "jumpurl", "jump_url", "clickurl", "click_url",
    }
    _IMAGE_KEYS = {
        "picurl", "pic_url", "image", "imageurl", "image_url", "mainimage",
        "main_image", "imgurl", "img_url",
    }
    _SELLER_KEYS = {"usernickname", "user_nick_name", "sellername", "seller_name", "nickname"}
    _AREA_KEYS = {"area", "location", "city", "region"}
    _COUNT_KEYS = {
        "wantcount", "want_count", "likecount", "like_count", "favcount",
        "favoritecount", "collectcount", "collect_count",
    }
    _PUBLISH_TIME_KEYS = {"publishtime", "publish_time", "createdtime", "created_time"}

    @staticmethod
    def _coerce_json(value: Any) -> Any:
        """Unwrap nested JSON/JSONP strings returned by MTOP variants."""
        if not isinstance(value, str):
            return value
        current: Any = value
        # A search card may be wrapped as a JSON string (or JSONP) inside the
        # result list.  Decode a small, bounded number of layers, but leave
        # ordinary text values untouched.
        for _ in range(3):
            if not isinstance(current, str):
                return current
            text = current.strip()
            if len(text) < 2:
                return current

            json_text = text
            if text[0] not in "[{\"":
                jsonp = re.match(r"^[A-Za-z_$][\w$\.]*\((.*)\);?$", text, re.DOTALL)
                if not jsonp:
                    return current
                json_text = jsonp.group(1).strip()

            try:
                decoded = json.loads(json_text)
            except (TypeError, ValueError, json.JSONDecodeError):
                return current
            if isinstance(decoded, str) and decoded == current:
                return current
            current = decoded

        return current

    @classmethod
    def _walk_dicts(cls, value: Any) -> Any:
        """Yield nested dictionaries while tolerating wrapper/list/string variants."""
        stack: list[Any] = [cls._coerce_json(value)]
        seen: set[int] = set()
        visited = 0
        while stack and visited < 2000:
            current = cls._coerce_json(stack.pop())
            visited += 1
            if isinstance(current, dict):
                identity = id(current)
                if identity in seen:
                    continue
                seen.add(identity)
                yield current
                stack.extend(current.values())
            elif isinstance(current, list):
                stack.extend(current)

    @classmethod
    def _find_first_value(cls, root: Any, keys: set[str]) -> Any:
        """Find a non-empty value by key anywhere in a response wrapper."""
        normalized_keys = {key.lower() for key in keys}
        for mapping in cls._walk_dicts(root):
            for key, value in mapping.items():
                if str(key).lower() not in normalized_keys:
                    continue
                value = cls._coerce_json(value)
                if value not in (None, "", [], {}):
                    return value
        return None

    @classmethod
    def _scalar_text(cls, value: Any, default: str = "") -> str:
        """Convert scalar/dict wrapper values to display text."""
        value = cls._coerce_json(value)
        if value in (None, "", [], {}):
            return default
        if isinstance(value, (str, int, float)):
            return str(value).strip()
        if isinstance(value, list):
            parts = [cls._scalar_text(item) for item in value]
            return "".join(part for part in parts if part)
        if isinstance(value, dict):
            for key in ("text", "value", "content", "url", "href", "name"):
                if key in value:
                    result = cls._scalar_text(value[key])
                    if result:
                        return result
        return default

    @staticmethod
    def _item_id_from_url(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        try:
            query = parse_qs(urlparse(text).query or "")
            for key in ("id", "item_id", "itemId"):
                if query.get(key) and query[key][0]:
                    return str(query[key][0]).strip()
        except Exception:
            pass
        match = re.search(r"(?:[?&]id=|/item/)([A-Za-z0-9_-]+)", text)
        return match.group(1) if match else ""

    @staticmethod
    def _canonical_item_url(item_id: Any) -> str:
        """Return a stable public item URL only for a valid Goofish item ID."""
        normalized_id = str(item_id or "").strip()
        if not re.fullmatch(r"\d{6,32}", normalized_id):
            return ""
        return f"https://www.goofish.com/item?id={normalized_id}"

    @staticmethod
    async def safe_get(data: Any, *keys, default: Any = "暂无") -> Any:
        """安全获取嵌套字典值"""
        for key in keys:
            try:
                data = data[key]
            except (KeyError, TypeError, IndexError):
                return default
        return data

    @staticmethod
    def extract_want_count(tags_content: str) -> int:
        """从标签内容中提取"人想要"的数字"""
        try:
            if not tags_content or "人想要" not in tags_content:
                return 0

            # 匹配类似 "123人想要" 或 "1.2万人想要" 的格式
            pattern = r'(\d+(?:\.\d+)?(?:万)?)\s*人想要'
            match = re.search(pattern, tags_content)

            if match:
                number_str = match.group(1)
                if '万' in number_str:
                    number = float(number_str.replace('万', '')) * 10000
                    return int(number)
                else:
                    return int(float(number_str))

            return 0
        except Exception as e:
            logger.warning(f"提取想要人数失败: {str(e)}")
            return 0

    async def parse_item(self, item_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """解析单个商品数据，并兼容闲鱼搜索卡片的多种包装结构。"""
        try:
            item_data = self._coerce_json(item_data)
            if not isinstance(item_data, (dict, list)):
                return None

            def pick_first_dict(*candidates: Any) -> Dict[str, Any]:
                for candidate in candidates:
                    candidate = self._coerce_json(candidate)
                    if isinstance(candidate, dict) and candidate:
                        return candidate
                return {}

            data_item_main = await self.safe_get(item_data, "data", "item", "main", default={})
            item_main = await self.safe_get(item_data, "item", "main", default={})
            root_main = await self.safe_get(item_data, "main", default={})
            main_data = pick_first_dict(
                await self.safe_get(data_item_main, "exContent", default={}),
                data_item_main,
                await self.safe_get(item_main, "exContent", default={}),
                item_main,
                await self.safe_get(root_main, "exContent", default={}),
                root_main,
            )

            click_param = pick_first_dict(
                await self.safe_get(data_item_main, "clickParam", default={}),
                await self.safe_get(item_main, "clickParam", default={}),
                await self.safe_get(item_data, "clickParam", default={}),
            )
            click_params = pick_first_dict(
                await self.safe_get(click_param, "args", default={}),
                click_param,
            )

            title = self._scalar_text(
                await self.safe_get(main_data, "title", default=None),
            ) or self._scalar_text(
                self._find_first_value(item_data, self._TITLE_KEYS),
                default="未知标题",
            )

            price = await self._parse_price(main_data)
            if price == "价格异常":
                price = await self._parse_price(
                    {"price": self._find_first_value(item_data, self._PRICE_KEYS)}
                )

            fish_tags_content = await self._parse_fish_tags(main_data)
            if not fish_tags_content:
                fish_tags_content = await self._parse_fish_tags(item_data)

            area = self._scalar_text(
                await self.safe_get(main_data, "area", default=None),
            ) or self._scalar_text(
                self._find_first_value(item_data, self._AREA_KEYS),
                default="地区未知",
            )
            seller = self._scalar_text(
                await self.safe_get(main_data, "userNickName", default=None),
            ) or self._scalar_text(
                self._find_first_value(item_data, self._SELLER_KEYS),
                default="匿名卖家",
            )
            raw_link = self._scalar_text(
                await self.safe_get(main_data, "targetUrl", default=None),
            ) or self._scalar_text(
                self._find_first_value(item_data, self._URL_KEYS),
            )
            image_url = self._scalar_text(
                await self.safe_get(main_data, "picUrl", default=None),
            ) or self._scalar_text(
                self._find_first_value(item_data, self._IMAGE_KEYS),
            )

            item_id = self._scalar_text(
                self._find_first_value(click_params, self._ITEM_ID_KEYS),
            ) or self._scalar_text(
                self._find_first_value(item_data, self._ITEM_ID_KEYS),
            )
            if not item_id:
                item_id = self._item_id_from_url(raw_link)
            if not item_id:
                # Keep a stable card-level fallback so schema changes do not
                # turn a non-empty search response into a total parse failure.
                item_id = f"search-{abs(hash((title, raw_link, image_url, price)))}"

            publish_time = await self._parse_publish_time(click_params)
            if publish_time == "未知时间":
                publish_time = await self._parse_publish_time(item_data)

            want_count = self.extract_want_count(fish_tags_content)
            if not want_count:
                count_value = self._find_first_value(item_data, self._COUNT_KEYS)
                if isinstance(count_value, (int, float)):
                    want_count = int(count_value)
                elif count_value:
                    want_count = self.extract_want_count(f"{count_value}人想要")

            return {
                "item_id": str(item_id),
                "title": title or "未知标题",
                "price": price,
                "unit_price": self._parse_unit_price(price),
                "seller_name": seller or "匿名卖家",
                # Search responses also contain URLs for page assets (for example
                # DynamicX ZIP bundles).  Never expose those as a product link;
                # use the item ID to construct the stable Goofish detail URL.
                "item_url": self._canonical_item_url(item_id),
                "main_image": f"https:{image_url}" if image_url.startswith("//") else image_url,
                "publish_time": publish_time,
                "tags": [fish_tags_content] if fish_tags_content else [],
                "area": area or "地区未知",
                "want_count": want_count,
                "raw_data": item_data,
            }

        except Exception as e:
            logger.warning(f"解析商品数据失败: {str(e)}")
            return None

    async def _parse_price(self, main_data: Dict[str, Any]) -> str:
        """解析价格，兼容文本、数字、字典和列表包装。"""
        price_value = await self.safe_get(main_data, "price", default=None)
        if price_value in (None, "", [], {}):
            return "价格异常"

        if isinstance(price_value, (int, float)):
            amount = float(price_value)
            if amount.is_integer() and amount >= 100:
                amount /= 100
            return f"¥{amount:g}"

        if isinstance(price_value, dict):
            for key in (
                "text", "priceText", "price_text", "displayPrice", "value",
                "amount", "currentPrice", "price",
            ):
                if key in price_value:
                    parsed = await self._parse_price({"price": price_value[key]})
                    if parsed != "价格异常":
                        return parsed
            return "价格异常"

        if isinstance(price_value, list):
            parts: list[str] = []
            for part in price_value:
                if isinstance(part, dict):
                    text = self._scalar_text(part.get("text") or part.get("value"))
                else:
                    text = self._scalar_text(part)
                if text:
                    parts.append(text)
            price_text = "".join(parts)
        else:
            price_text = self._scalar_text(price_value)

        price_text = price_text.replace("当前价", "").strip()
        if not price_text:
            return "价格异常"

        had_currency = "¥" in price_text or "￥" in price_text
        clean_price = price_text.replace("￥", "¥").replace("¥", "").strip()
        if "万" in clean_price:
            try:
                amount = float(clean_price.replace("万", "").strip()) * 10000
                return f"¥{amount:.0f}"
            except (TypeError, ValueError):
                return f"¥{clean_price}"

        if not had_currency:
            numeric_match = re.fullmatch(r"(\d+(?:\.\d+)?)(?:-(\d+(?:\.\d+)?))?", clean_price)
            if numeric_match:
                values = [float(group) for group in numeric_match.groups() if group is not None]
                if all(value.is_integer() and value >= 100 for value in values):
                    values = [value / 100 for value in values]
                    clean_price = "-".join(f"{value:g}" for value in values)

        if re.search(r"\d", clean_price):
            return f"¥{clean_price}"
        return clean_price or "价格异常"

    @staticmethod
    def _parse_unit_price(value: Any) -> float | None:
        """Return the first numeric amount in yuan from listing price text.

        Search cards often render a range (for example ``¥9.9-19.9``) or
        append text such as ``起``.  The research contract exposes the
        starting/listing unit price separately so callers never have to
        parse presentation text themselves.
        """
        if value is None:
            return None
        if isinstance(value, (int, float)):
            amount = float(value)
            if amount.is_integer() and amount >= 100:
                amount /= 100
            return round(amount, 2)
        text = str(value).replace(",", "").strip()
        has_currency = text.startswith(("¥", "￥"))
        match = re.search(r"(?<!\d)(\d+(?:\.\d+)?)(?!\d)", text)
        if not match:
            return None
        try:
            amount = float(match.group(1))
            # Some search payload variants expose a bare integer in fen while
            # the card text variant already contains the yuan symbol.
            if not has_currency and amount.is_integer() and amount >= 100:
                amount /= 100
            return round(amount, 2)
        except (TypeError, ValueError):
            return None

    async def _parse_fish_tags(self, main_data: Dict[str, Any]) -> str:
        """解析商品标签，只提取"想要人数"标签。"""
        fish_tags = await self.safe_get(main_data, "fishTags", default=None)
        if fish_tags in (None, "", [], {}):
            fish_tags = self._find_first_value(main_data, {"fishTags", "fish_tags"})
        if fish_tags in (None, "", [], {}):
            return ""

        for mapping in self._walk_dicts(fish_tags):
            for key in ("content", "text", "value"):
                content = self._scalar_text(mapping.get(key))
                if content and "人想要" in content:
                    return content
            tag_list = mapping.get("tagList")
            if isinstance(tag_list, list):
                for tag_item in tag_list:
                    content = self._scalar_text(
                        self._find_first_value(tag_item, {"content", "text", "value"})
                    )
                    if content and "人想要" in content:
                        return content

        text = self._scalar_text(fish_tags)
        return text if "人想要" in text else ""

    async def _parse_publish_time(self, click_params: Dict[str, Any]) -> str:
        """解析发布时间"""
        publish_time = "未知时间"
        publish_timestamp = self._find_first_value(click_params, self._PUBLISH_TIME_KEYS) or ""

        if publish_timestamp and str(publish_timestamp).isdigit():
            try:
                publish_time = datetime.fromtimestamp(
                    int(publish_timestamp) / 1000
                ).strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass

        return publish_time

    async def parse_items_batch(
        self, items: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """批量解析商品数据"""
        parsed_items = []
        for item in items:
            try:
                parsed = await self.parse_item(item)
                if parsed:
                    parsed_items.append(parsed)
            except Exception as e:
                logger.warning(f"解析单个商品失败: {str(e)}")
                continue
        return parsed_items

    @staticmethod
    def sort_by_want_count(items: List[Dict[str, Any]], reverse: bool = True) -> List[Dict[str, Any]]:
        """按想要人数排序"""
        return sorted(items, key=lambda x: x.get('want_count', 0), reverse=reverse)

