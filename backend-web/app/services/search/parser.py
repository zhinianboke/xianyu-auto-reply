"""
商品数据解析器

解析闲鱼API返回的商品数据
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger


class ItemParser:
    """商品数据解析器"""

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
        """解析单个商品数据"""
        try:
            # Goofish 搜索接口返回结构可能存在变体：
            # - data.item.main.exContent
            # - data.item.main
            # - item.main(.exContent)
            # - main(.exContent)
            def pick_first_dict(*candidates: Any) -> Dict[str, Any]:
                for candidate in candidates:
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

            # 解析商品标题
            title = await self.safe_get(main_data, "title", default="未知标题")

            # 解析价格
            price = await self._parse_price(main_data)

            # 解析标签（只提取"想要人数"）
            fish_tags_content = await self._parse_fish_tags(main_data)

            # 其他字段
            area = await self.safe_get(main_data, "area", default="地区未知")
            seller = await self.safe_get(main_data, "userNickName", default="匿名卖家")
            raw_link = await self.safe_get(main_data, "targetUrl", default="")
            if not raw_link:
                raw_link = await self.safe_get(
                    item_data, "data", "item", "main", "targetUrl", default=""
                )
            image_url = await self.safe_get(main_data, "picUrl", default="")
            item_id = await self.safe_get(click_params, "item_id", default="未知ID")
            if not item_id or item_id == "未知ID":
                item_id = await self.safe_get(click_params, "itemId", default=item_id)
                item_id = await self.safe_get(click_params, "id", default=item_id)

            # 处理发布时间
            publish_time = await self._parse_publish_time(click_params)

            # 提取"人想要"的数字用于排序
            want_count = self.extract_want_count(fish_tags_content)

            return {
                "item_id": item_id,
                "title": title,
                "price": price,
                "seller_name": seller,
                "item_url": raw_link.replace("fleamarket://", "https://www.goofish.com/"),
                "main_image": f"https:{image_url}" if image_url and not image_url.startswith("http") else image_url,
                "publish_time": publish_time,
                "tags": [fish_tags_content] if fish_tags_content else [],
                "area": area,
                "want_count": want_count,
                "raw_data": item_data
            }

        except Exception as e:
            logger.warning(f"解析商品数据失败: {str(e)}")
            return None

    async def _parse_price(self, main_data: Dict[str, Any]) -> str:
        """解析价格"""
        price_parts = await self.safe_get(main_data, "price", default=[])
        price = "价格异常"

        if isinstance(price_parts, list):
            price = "".join([
                str(p.get("text", "")) for p in price_parts if isinstance(p, dict)
            ])
            price = price.replace("当前价", "").strip()

            if price and price != "价格异常":
                clean_price = price.replace('¥', '').strip()

                if "万" in clean_price:
                    try:
                        numeric_price = clean_price.replace('万', '').strip()
                        price_value = float(numeric_price) * 10000
                        price = f"¥{price_value:.0f}"
                    except Exception:
                        price = f"¥{clean_price}"
                else:
                    if clean_price and (clean_price[0].isdigit() or clean_price.replace('.', '').isdigit()):
                        price = f"¥{clean_price}"
                    else:
                        price = clean_price if clean_price else "价格异常"

        return price

    async def _parse_fish_tags(self, main_data: Dict[str, Any]) -> str:
        """解析商品标签，只提取"想要人数"标签"""
        fish_tags_content = ""
        fish_tags = await self.safe_get(main_data, "fishTags", default={})

        for tag_type, tag_data in fish_tags.items():
            if isinstance(tag_data, dict) and "tagList" in tag_data:
                tag_list = tag_data.get("tagList", [])
                for tag_item in tag_list:
                    if isinstance(tag_item, dict) and "data" in tag_item:
                        content = tag_item["data"].get("content", "")
                        if content and "人想要" in content:
                            fish_tags_content = content
                            break
                if fish_tags_content:
                    break

        return fish_tags_content

    async def _parse_publish_time(self, click_params: Dict[str, Any]) -> str:
        """解析发布时间"""
        publish_time = "未知时间"
        publish_timestamp = click_params.get("publishTime", "")

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
