"""
AI铺货服务

负责AI铺货配置管理，并按配置生成商品素材。
"""
from __future__ import annotations

import base64
import asyncio
import json
import random
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Awaitable, Callable, TypeVar

import httpx
from loguru import logger
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.paths import get_upload_path
from app.services.ai_listing_task_status_service import AiListingTaskStatusService
from app.services.product_publish_service import ProductMaterialService
from common.models.ai_listing_config import AiListingConfig
from common.services.ai_provider_service import build_openai_url, clean_ai_text, ensure_success_response
from common.utils.time_utils import safe_isoformat


AI_LISTING_SYSTEM_PROMPT = """
你是闲鱼商品铺货文案助手。请根据用户给出的商品方向、参考文案和价格规则，生成自然、真实、适合二手/闲置平台发布的商品素材。
要求：
1. 只输出 JSON，不要输出 Markdown 或解释。
2. JSON 字段必须包含 title、description、price。
3. title 控制在 20 个中文字符以内，且要富有变化，有吸引力。
4. 如果用户提供了参考文案，description 必须尽量完整保留参考文案中的商品信息、卖点、状态、配件、场景、交易说明和表达重点，不要无故删减原有语义。
5. 可以做自然改写，但不要明显压缩内容，description 的字数尽量接近参考文案，字数波动不要太大，但是句式内容需要变换。
6. description 口吻自然真实，不要编造无法确认的官方承诺、保真承诺、售后承诺。
7. price 必须遵守用户给出的固定价格或价格范围，且价格范围内应该是合理的数，吉利的数字，最多1位小数，尽量常见的9.9,8.8,6.8等等为尾数。
8. 避免绝对化、违禁、虚假宣传表述。
""".strip()

AI_LISTING_IMAGE_POLISH_SYSTEM_PROMPT = """
你是闲鱼商品图片提示词润色助手。你的任务是在不改变原意的前提下，把用户给出的图片要求整理成更稳定、更适合图片生成模型的提示词。
要求：
1. 只输出 JSON，不要输出 Markdown 或解释
2. JSON 字段必须包含 prompts
3. prompts 必须是字符串数组，每个元素对应一张图片的提示词
4. 当用户要求生成 N 张图时，prompts 数组长度必须严格等于 N，不能缺少，不能合并，不能输出额外元素
5. 必须保留原提示词中的主体、卖点、场景、风格、材质、用途等关键信息，不要改变商品类型，不要改变原本想表达的含义
6. 可以补充少量有助于生图稳定性的商品展示描述，但不要删减关键语义，也不要把原提示词改成完全不同的内容
7. 每张图都要符合闲鱼商品展示图语境，真实、自然、适合展示售卖商品，商品可能是虚拟物品，也可能是实物商品，如果是虚拟物品则生成海报图，如果是实物生成实拍图。
""".strip()

AI_LISTING_IMAGE_GENERATION_PREFIX = """
闲鱼电商商品展示图，用于二手/闲置平台商品发布，商品可能是虚拟物品，也可能是实物商品。
画面要求真实自然、主体明确、构图干净、突出商品本身与售卖信息，适合生成商品展示图，不要加入无关杂乱元素、夸张海报字或平台水印。
""".strip()

AI_REQUEST_RETRY_TIMES = 3
AI_REQUEST_RETRY_BASE_DELAY_SECONDS = 1.0

T = TypeVar("T")


def _short_debug_text(value: Any, limit: int = 4000) -> str:
    """压缩调试日志文本，避免日志过长"""
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...(truncated {len(text) - limit} chars)"


def _format_exception_message(exc: Exception) -> str:
    text = str(exc or "").strip()
    if text:
        return text
    return f"{exc.__class__.__name__}: {repr(exc)}"


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    normalized = str(text or "").lower()
    return any(keyword in normalized for keyword in keywords)


class AiListingConfigService:
    """AI铺货配置 CRUD"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, user_id: int, data: dict[str, Any]) -> AiListingConfig:
        config = AiListingConfig(user_id=user_id, **self._normalize_config_payload(data))
        self.session.add(config)
        await self.session.commit()
        await self.session.refresh(config)
        return config

    async def list_configs(self, user_id: int) -> list[dict[str, Any]]:
        stmt = (
            select(AiListingConfig)
            .where(AiListingConfig.user_id == user_id)
            .order_by(desc(AiListingConfig.created_at))
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [ai_listing_config_to_dict(row) for row in rows]

    async def get(self, config_id: int, user_id: int) -> AiListingConfig | None:
        stmt = select(AiListingConfig).where(
            AiListingConfig.id == config_id,
            AiListingConfig.user_id == user_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def update(self, config_id: int, user_id: int, data: dict[str, Any]) -> AiListingConfig | None:
        config = await self.get(config_id, user_id)
        if not config:
            return None
        payload = self._normalize_config_payload(data, partial=True)
        for key, value in payload.items():
            setattr(config, key, value)
        await self.session.commit()
        await self.session.refresh(config)
        return config

    async def delete(self, config_id: int, user_id: int) -> bool:
        config = await self.get(config_id, user_id)
        if not config:
            return False
        await self.session.delete(config)
        await self.session.commit()
        return True

    def _normalize_config_payload(self, data: dict[str, Any], partial: bool = False) -> dict[str, Any]:
        fields = {
            "name",
            "prompt",
            "reference_text",
            "price_mode",
            "fixed_price",
            "price_min",
            "price_max",
            "text_api_url",
            "text_api_key",
            "text_model",
            "image_mode",
            "image_api_url",
            "image_api_key",
            "image_model",
            "image_prompt",
            "image_polish_enabled",
            "image_polish_sequential",
            "random_images",
            "random_image_count",
            "material_defaults",
        }
        payload = {key: data[key] for key in fields if key in data}
        if not partial:
            payload.setdefault("reference_text", None)
            payload.setdefault("price_mode", "fixed")
            payload.setdefault("image_mode", "random")
            payload.setdefault("image_polish_enabled", False)
            payload.setdefault("image_polish_sequential", False)
            payload.setdefault("random_images", [])
            payload.setdefault("random_image_count", 1)
            payload.setdefault("material_defaults", {})
        if "price_mode" in payload and payload["price_mode"] not in {"fixed", "range"}:
            payload["price_mode"] = "fixed"
        if "image_mode" in payload and payload["image_mode"] not in {"ai", "random"}:
            payload["image_mode"] = "random"
        if "random_image_count" in payload:
            payload["random_image_count"] = max(1, min(int(payload["random_image_count"] or 1), 9))
        if "image_polish_enabled" in payload:
            payload["image_polish_enabled"] = bool(payload["image_polish_enabled"])
        if "image_polish_sequential" in payload:
            payload["image_polish_sequential"] = bool(payload["image_polish_sequential"])
        image_mode = payload.get("image_mode")
        random_image_count = int(payload.get("random_image_count") or 1)
        if image_mode == "ai" and random_image_count > 1:
            payload["image_polish_enabled"] = True
        if "random_images" in payload:
            payload["random_images"] = [str(url) for url in (payload["random_images"] or []) if str(url).strip()]
        if "material_defaults" in payload:
            payload["material_defaults"] = dict(payload["material_defaults"] or {})
        return payload


class AiListingGenerationService:
    """AI铺货生成服务"""

    def __init__(self, session: AsyncSession | None = None):
        self.session = session

    async def _run_with_retries(
        self,
        step_name: str,
        action: Callable[[int, int], Awaitable[T]],
    ) -> T:
        total_attempts = AI_REQUEST_RETRY_TIMES + 1
        last_error: Exception | None = None
        for attempt in range(1, total_attempts + 1):
            try:
                if attempt > 1:
                    logger.warning(
                        "{} 重试开始 | attempt={}/{}",
                        step_name,
                        attempt,
                        total_attempts,
                    )
                return await action(attempt, total_attempts)
            except Exception as exc:
                last_error = exc if isinstance(exc, Exception) else RuntimeError(str(exc))
                logger.warning(
                    "{} 失败 | attempt={}/{} | error={}",
                    step_name,
                    attempt,
                    total_attempts,
                    _format_exception_message(last_error),
                )
                if attempt >= total_attempts:
                    break
                await asyncio.sleep(AI_REQUEST_RETRY_BASE_DELAY_SECONDS * attempt)
        assert last_error is not None
        raise last_error

    async def run_generation_task(
        self,
        user_id: int,
        config_id: int,
        task_id: str,
        count: int,
        concurrency: int = 1,
    ) -> None:
        config = await self._load_runtime_config(user_id, config_id)
        if not config:
            await AiListingTaskStatusService.finish(task_id, "failed", "AI铺货配置不存在")
            return

        concurrency = max(1, min(int(concurrency or 1), 10))
        await AiListingTaskStatusService.mark_running(task_id, f"正在生成素材，并发数 {concurrency}")
        semaphore = asyncio.Semaphore(concurrency)

        async def worker(index: int) -> None:
            async with semaphore:
                await self._generate_one(user_id, config, task_id, index, count)

        await asyncio.gather(*(worker(index) for index in range(count)))

        snapshot = await AiListingTaskStatusService.get_task_snapshot(task_id) or {}
        success = int(snapshot.get("success") or 0)
        failed = int(snapshot.get("failed") or 0)
        status = "success" if success > 0 and failed == 0 else "failed" if success == 0 else "partial_success"
        await AiListingTaskStatusService.finish(task_id, status, f"生成完成：成功 {success} 条，失败 {failed} 条")

    async def _load_runtime_config(self, user_id: int, config_id: int) -> Any | None:
        from common.db.session import async_session_maker

        if self.session is not None:
            config = await AiListingConfigService(self.session).get(config_id, user_id)
            if not config:
                return None
            return SimpleNamespace(**ai_listing_config_to_dict(config))

        async with async_session_maker() as session:
            config = await AiListingConfigService(session).get(config_id, user_id)
            if not config:
                return None
            return SimpleNamespace(**ai_listing_config_to_dict(config))

    async def _generate_one(
        self,
        user_id: int,
        config: AiListingConfig,
        task_id: str,
        index: int,
        total: int,
    ) -> None:
        try:
            await AiListingTaskStatusService.update_stage(
                task_id,
                "text",
                "正在生成文案",
                f"正在生成第 {index + 1}/{total} 个素材文案",
            )
            generated = await self._generate_text(config, index + 1, total)
            await AiListingTaskStatusService.update_stage(
                task_id,
                "text",
                "文案生成完成",
                f"第 {index + 1}/{total} 个素材文案已生成",
                increment=True,
            )
            price = self._resolve_price(config, generated.get("price"))
            images = await self._resolve_images(config, generated, price, task_id, index, total)
            defaults = dict(config.material_defaults or {})
            payload = {
                **defaults,
                "title": clean_ai_text(generated.get("title"))[:200],
                "description": str(generated.get("description") or "").strip(),
                "price": price,
                "images": images,
            }
            payload.setdefault("condition", "全新")
            if payload.get("delivery_method") not in {"express", "pickup"}:
                payload["delivery_method"] = "express"
            payload.pop("support_pickup", None)
            payload.setdefault("postage", 0)
            if payload["delivery_method"] == "pickup":
                payload["postage"] = 0
            if not payload["title"]:
                raise ValueError("AI未返回商品标题")
            if not payload["description"]:
                raise ValueError("AI未返回商品描述")
            if not payload["images"]:
                raise ValueError("未生成或选择商品图片")
            material = await self._create_material(user_id, payload)
            await AiListingTaskStatusService.add_success(
                task_id,
                material.id,
                f"已创建素材 {index + 1}/{total}",
            )
        except Exception as exc:
            error_text = _format_exception_message(exc)
            logger.warning(f"AI铺货生成第 {index + 1} 条失败: {error_text}")
            await AiListingTaskStatusService.add_failed(task_id, f"第 {index + 1} 条失败：{error_text}")

    async def _create_material(self, user_id: int, payload: dict[str, Any]):
        from common.db.session import async_session_maker

        async with async_session_maker() as session:
            return await ProductMaterialService(session).create(user_id, payload)

    async def _generate_text(self, config: AiListingConfig, index: int, total: int) -> dict[str, Any]:
        price_rule = self._build_price_rule(config)
        user_content = (
            f"商品生成提示词：\n{config.prompt}\n\n"
            f"参考文案：\n{config.reference_text or '无'}\n\n"
            f"价格规则：{price_rule}\n\n"
            "如果参考文案不为空，请以参考文案为主做保留式改写，尽量保留原有信息、语义重点和接近的字数。"
        )
        logger.info(
            "AI铺货文案生成开始 | index={}/{} | model={} | url={} | user_content={}",
            index,
            total,
            clean_ai_text(config.text_model),
            build_openai_url(config.text_api_url, "/chat/completions"),
            _short_debug_text(user_content),
        )
        return await self._chat_json(
            config,
            AI_LISTING_SYSTEM_PROMPT,
            user_content,
            "AI铺货文案接口",
            temperature=0.8,
            max_tokens=1200,
        )

    async def _chat_json(
        self,
        config: AiListingConfig,
        system_prompt: str,
        user_content: str,
        provider_name: str,
        temperature: float = 0.7,
        max_tokens: int = 1200,
    ) -> dict[str, Any]:
        url = build_openai_url(config.text_api_url, "/chat/completions")
        logger.info(
            "{} 请求 | url={} | model={} | temperature={} | max_tokens={} | system_prompt={} | user_content={}",
            provider_name,
            url,
            clean_ai_text(config.text_model),
            temperature,
            max_tokens,
            _short_debug_text(system_prompt),
            _short_debug_text(user_content),
        )

        async def do_request(attempt: int, total_attempts: int) -> dict[str, Any]:
            logger.info(
                "{} 执行请求 | attempt={}/{} | url={} | model={}",
                provider_name,
                attempt,
                total_attempts,
                url,
                clean_ai_text(config.text_model),
            )
            async with httpx.AsyncClient(timeout=90.0) as client:
                response = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {clean_ai_text(config.text_api_key)}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": clean_ai_text(config.text_model),
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_content},
                        ],
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                )
            ensure_success_response(response, provider_name)
            result = response.json()
            try:
                content = result["choices"][0]["message"]["content"]
            except Exception as exc:
                raise RuntimeError(f"{provider_name}响应格式错误: {str(result)[:500]}") from exc
            logger.info(
                "{} 响应 | attempt={}/{} | status_code={} | raw_content={}",
                provider_name,
                attempt,
                total_attempts,
                response.status_code,
                _short_debug_text(content),
            )
            parsed = self._parse_json_content(content)
            logger.info(
                "{} 解析结果 | attempt={}/{} | parsed_json={}",
                provider_name,
                attempt,
                total_attempts,
                _short_debug_text(json.dumps(parsed, ensure_ascii=False)),
            )
            return parsed

        return await self._run_with_retries(provider_name, do_request)

    def _parse_json_content(self, content: Any) -> dict[str, Any]:
        text = str(content or "").strip()
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()
        if "{" in text and "}" in text:
            text = text[text.find("{"): text.rfind("}") + 1]
        try:
            data = json.loads(text)
        except Exception as exc:
            raise ValueError("AI返回内容不是有效JSON") from exc
        if not isinstance(data, dict):
            raise ValueError("AI返回JSON不是对象")
        return data

    def _build_price_rule(self, config: AiListingConfig) -> str:
        if config.price_mode == "range":
            return f"价格必须在 {float(config.price_min or 0):.2f} 到 {float(config.price_max or 0):.2f} 元之间"
        return f"价格必须固定为 {float(config.fixed_price or 0):.2f} 元"

    def _resolve_price(self, config: AiListingConfig, ai_price: Any) -> float:
        if config.price_mode == "range":
            low = float(config.price_min or 0)
            high = float(config.price_max or 0)
            if low <= 0 or high <= 0 or high < low:
                raise ValueError("价格范围配置不正确")
            try:
                price = float(ai_price)
            except Exception:
                price = round(random.uniform(low, high), 2)
            if price < low or price > high:
                price = round(random.uniform(low, high), 2)
            return round(price, 2)
        price = float(config.fixed_price or 0)
        if price <= 0:
            raise ValueError("固定价格配置不正确")
        return round(price, 2)

    async def _resolve_images(
        self,
        config: AiListingConfig,
        generated: dict[str, Any],
        price: float,
        task_id: str,
        index: int,
        total: int,
    ) -> list[str]:
        count = max(1, min(int(config.random_image_count or 1), 9))
        if config.image_mode == "ai":
            return await self._generate_images(config, generated, price, count, task_id, index, total)
        images = [str(url) for url in (config.random_images or []) if str(url).strip()]
        if not images:
            raise ValueError("随机图库为空")
        if count > len(images):
            raise ValueError("随机选图数量不能大于图库图片数量")
        await AiListingTaskStatusService.update_stage(
            task_id,
            "image_generate",
            "正在准备图片",
            f"正在为第 {index + 1}/{total} 个素材随机选图",
        )
        await AiListingTaskStatusService.update_stage(
            task_id,
            "image_polish",
            "图片润色已跳过",
            f"第 {index + 1}/{total} 个素材使用随机图片，无需润色",
            increment=True,
        )
        await AiListingTaskStatusService.update_stage(
            task_id,
            "image_generate",
            "图片准备完成",
            f"第 {index + 1}/{total} 个素材随机选图完成",
            increment=True,
        )
        if count == len(images):
            return images[:]
        return random.sample(images, count)

    def _build_image_prompt_context(
        self,
        config: AiListingConfig,
        generated: dict[str, Any],
        price: float,
    ) -> dict[str, str]:
        return {
            "title": clean_ai_text(generated.get("title")),
            "description": str(generated.get("description") or "").strip(),
            "price": f"{price:.2f}",
        }

    def _render_image_prompt_template(
        self,
        template: str,
        context: dict[str, str],
    ) -> str:
        rendered = template
        for key, value in context.items():
            rendered = rendered.replace(f"{{{key}}}", value)
        return rendered.strip()

    def _compose_image_generation_prompt(self, prompt: str) -> str:
        prompt = str(prompt or "").strip()
        if not prompt:
            return AI_LISTING_IMAGE_GENERATION_PREFIX
        return f"{AI_LISTING_IMAGE_GENERATION_PREFIX}\n\n{prompt}"

    def _resolve_image_size(self, prompt: str) -> str:
        prompt_text = str(prompt or "")
        if _contains_any(prompt_text, ("正方形", "方图", "方形", "1:1", "1比1", "1：1", "square")):
            return "1024x1024"
        if _contains_any(prompt_text, ("竖图", "竖版", "长图", "海报", "9:16", "3:4", "4:5", "9比16", "3比4", "4比5", "9：16", "3：4", "4：5", "portrait", "vertical")):
            return "1024x1536"
        if _contains_any(prompt_text, ("横图", "横版", "宽图", "16:9", "4:3", "16比9", "4比3", "16：9", "4：3", "landscape", "horizontal")):
            return "1536x1024"
        return "1024x1024"

    async def _build_image_prompts(
        self,
        config: AiListingConfig,
        generated: dict[str, Any],
        price: float,
        count: int,
        task_id: str,
        index: int,
        total: int,
    ) -> list[str]:
        context = self._build_image_prompt_context(config, generated, price)
        template = (config.image_prompt or "").strip()
        base_prompt = self._render_image_prompt_template(template, context)
        logger.info(
            "AI铺货图片提示词渲染 | count={} | template={} | context={} | rendered_prompt={}",
            count,
            _short_debug_text(template),
            _short_debug_text(json.dumps(context, ensure_ascii=False)),
            _short_debug_text(base_prompt),
        )
        if not base_prompt:
            raise ValueError("图片提示词不能为空")

        if config.image_polish_enabled:
            prompt_count = count if count > 1 else 1
            await AiListingTaskStatusService.update_stage(
                task_id,
                "image_polish",
                "正在润色图片提示词",
                f"正在润色第 {index + 1}/{total} 个素材图片提示词",
            )
            sequential_instruction = (
                "多图关联要求：多张图需要保持同一个商品主体，在风格、色调和关键细节上统一，同时每张图的构图可以略有变化。"
                if config.image_polish_sequential and count > 1
                else "多图关联要求：默认每张图独立生成，不需要强制保持多张图之间的统一性。"
            )
            user_content = (
                f"原始图片提示词：\n{base_prompt}\n\n"
                f"需要生成 {prompt_count} 条图片提示词\n"
                f"{sequential_instruction}"
            )
            logger.info(
                "AI铺货图片润色开始 | count={} | sequential={} | user_content={}",
                prompt_count,
                config.image_polish_sequential and count > 1,
                _short_debug_text(user_content),
            )
            data = await self._chat_json(
                config,
                AI_LISTING_IMAGE_POLISH_SYSTEM_PROMPT,
                user_content,
                "AI铺货图片润色接口",
                temperature=0.7,
                max_tokens=1600,
            )
            prompts = self._normalize_prompt_list(data.get("prompts"), prompt_count, base_prompt)
            logger.info(
                "AI铺货图片润色完成 | prompt_count={} | prompts={}",
                len(prompts),
                _short_debug_text(json.dumps(prompts, ensure_ascii=False)),
            )
            await AiListingTaskStatusService.update_stage(
                task_id,
                "image_polish",
                "图片提示词润色完成",
                f"第 {index + 1}/{total} 个素材图片提示词已润色",
                increment=True,
            )
            return prompts

        logger.info(
            "AI铺货图片提示词直出 | count={} | prompt={}",
            count,
            _short_debug_text(base_prompt),
        )
        await AiListingTaskStatusService.update_stage(
            task_id,
            "image_polish",
            "图片润色已跳过",
            f"第 {index + 1}/{total} 个素材直接使用原始图片提示词",
            increment=True,
        )
        if count > 1:
            return [base_prompt]
        return [base_prompt]

    def _normalize_prompt_list(self, prompts: Any, min_count: int, fallback: str) -> list[str]:
        if isinstance(prompts, list):
            values = [str(item).strip() for item in prompts if str(item).strip()]
        elif isinstance(prompts, str) and prompts.strip():
            values = [prompts.strip()]
        else:
            values = []
        if not values:
            values = [fallback]
        while len(values) < min_count:
            values.append(values[-1])
        return values

    async def _request_image_generation(
        self,
        config: AiListingConfig,
        prompt: str,
        count: int,
    ) -> list[str]:
        if not config.image_api_url or not config.image_api_key or not config.image_model:
            raise ValueError("图片AI配置未填写完整")
        url = build_openai_url(config.image_api_url, "/images/generations")
        final_prompt = self._compose_image_generation_prompt(prompt)
        image_size = self._resolve_image_size(prompt)
        logger.info(
            "AI铺货图片生成请求 | url={} | model={} | count={} | size={} | raw_prompt={} | final_prompt={}",
            url,
            clean_ai_text(config.image_model),
            count,
            image_size,
            _short_debug_text(prompt),
            _short_debug_text(final_prompt),
        )

        async def do_request(attempt: int, total_attempts: int) -> list[str]:
            logger.info(
                "AI铺货图片生成执行请求 | attempt={}/{} | url={} | model={} | count={}",
                attempt,
                total_attempts,
                url,
                clean_ai_text(config.image_model),
                count,
            )
            async with httpx.AsyncClient(timeout=180.0) as client:
                response = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {clean_ai_text(config.image_api_key)}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": clean_ai_text(config.image_model),
                        "prompt": final_prompt,
                        "n": count,
                        "size": image_size,
                    },
                )
            ensure_success_response(response, "AI铺货图片接口")
            result = response.json()
            data = result.get("data") if isinstance(result, dict) else None
            if not isinstance(data, list) or not data:
                raise RuntimeError(f"图片AI响应格式错误: {str(result)[:500]}")
            logger.info(
                "AI铺货图片生成响应 | attempt={}/{} | status_code={} | image_items={}",
                attempt,
                total_attempts,
                response.status_code,
                len(data),
            )
            saved_urls: list[str] = []
            async with httpx.AsyncClient(timeout=90.0) as client:
                for item in data[:count]:
                    if not isinstance(item, dict):
                        continue
                    if item.get("url"):
                        saved_urls.append(await self._save_image_url(client, str(item["url"])))
                    elif item.get("b64_json"):
                        saved_urls.append(self._save_image_bytes(base64.b64decode(str(item["b64_json"])), ".png"))
            logger.info(
                "AI铺货图片保存完成 | attempt={}/{} | saved_count={} | saved_urls={}",
                attempt,
                total_attempts,
                len(saved_urls),
                _short_debug_text(json.dumps(saved_urls, ensure_ascii=False)),
            )
            return saved_urls

        return await self._run_with_retries("AI铺货图片接口", do_request)

    async def _generate_images(
        self,
        config: AiListingConfig,
        generated: dict[str, Any],
        price: float,
        count: int,
        task_id: str,
        index: int,
        total: int,
    ) -> list[str]:
        if count > 1 and not config.image_polish_enabled:
            raise ValueError("AI多图生成必须开启图片提示词AI润色")
        prompts = await self._build_image_prompts(config, generated, price, count, task_id, index, total)
        if not prompts:
            raise ValueError("图片提示词生成失败")
        logger.info(
            "AI铺货图片生成准备完成 | count={} | prompts={}",
            count,
            _short_debug_text(json.dumps(prompts, ensure_ascii=False)),
        )
        await AiListingTaskStatusService.update_stage(
            task_id,
            "image_generate",
            "正在生成图片",
            f"正在生成第 {index + 1}/{total} 个素材图片",
        )
        if len(prompts) == 1:
            saved_urls = await self._request_image_generation(config, prompts[0], count)
            await AiListingTaskStatusService.update_stage(
                task_id,
                "image_generate",
                "图片生成完成",
                f"第 {index + 1}/{total} 个素材已生成 {len(saved_urls)} 张图片",
                increment=True,
            )
            return saved_urls

        logger.info(
            "AI铺货多图并发生成开始 | material_index={}/{} | prompt_count={}",
            index + 1,
            total,
            min(len(prompts), count),
        )
        result_groups = await asyncio.gather(*[
            self._request_image_generation(config, prompt, 1)
            for prompt in prompts[:count]
        ])
        saved_urls = [url for group in result_groups for url in group]
        await AiListingTaskStatusService.update_stage(
            task_id,
            "image_generate",
            "图片生成完成",
            f"第 {index + 1}/{total} 个素材已生成 {len(saved_urls[:count])} 张图片",
            increment=True,
        )
        return saved_urls[:count]

    async def _save_image_url(self, client: httpx.AsyncClient, url: str) -> str:
        response = await client.get(url)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        ext = ".png"
        if "jpeg" in content_type or "jpg" in content_type:
            ext = ".jpg"
        elif "webp" in content_type:
            ext = ".webp"
        return self._save_image_bytes(response.content, ext)

    def _save_image_bytes(self, content: bytes, ext: str) -> str:
        upload_dir = get_upload_path("products")
        filename = f"ai_listing_{uuid.uuid4().hex}{ext}"
        filepath: Path = upload_dir / filename
        filepath.write_bytes(content)
        return f"/static/uploads/products/{filename}"


def ai_listing_config_to_dict(config: AiListingConfig) -> dict[str, Any]:
    """将AI铺货配置转为字典"""
    return {
        "id": config.id,
        "user_id": config.user_id,
        "name": config.name,
        "prompt": config.prompt,
        "reference_text": config.reference_text,
        "price_mode": config.price_mode,
        "fixed_price": float(config.fixed_price) if config.fixed_price is not None else None,
        "price_min": float(config.price_min) if config.price_min is not None else None,
        "price_max": float(config.price_max) if config.price_max is not None else None,
        "text_api_url": config.text_api_url,
        "text_api_key": config.text_api_key,
        "text_model": config.text_model,
        "image_mode": config.image_mode,
        "image_api_url": config.image_api_url,
        "image_api_key": config.image_api_key,
        "image_model": config.image_model,
        "image_prompt": config.image_prompt,
        "image_polish_enabled": bool(config.image_polish_enabled),
        "image_polish_sequential": bool(config.image_polish_sequential),
        "random_images": config.random_images or [],
        "random_image_count": int(config.random_image_count or 1),
        "material_defaults": config.material_defaults or {},
        "created_at": safe_isoformat(config.created_at),
        "updated_at": safe_isoformat(config.updated_at),
    }
