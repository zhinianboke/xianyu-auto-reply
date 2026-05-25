from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger


def _normalize_address_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or ""))


async def _read_promotion_address_text(container) -> str:
    candidate_selectors = [
        'div[title]',
        'span[title]',
        'div[class*="address"]',
        'span[class*="address"]',
        'div',
        'span',
    ]

    for selector in candidate_selectors:
        try:
            candidates = await container.query_selector_all(selector)
        except Exception:
            continue

        for candidate in candidates:
            try:
                if not await candidate.is_visible():
                    continue
                title_text = str(await candidate.get_attribute("title") or "").strip()
                inner_text = re.sub(r"\s+", " ", str(await candidate.inner_text() or "")).strip()
                text = title_text or inner_text
                normalized_text = _normalize_address_text(text)
                if not normalized_text:
                    continue
                if "宝贝所在地" in text:
                    continue
                if len(normalized_text) > 60:
                    continue
                return text
            except Exception:
                continue

    try:
        container_text = re.sub(r"\s+", " ", str(await container.inner_text() or "")).strip()
    except Exception:
        container_text = ""
    if "宝贝所在地" in container_text:
        container_text = container_text.replace("宝贝所在地", "").strip()
    return container_text


async def _find_promotion_address_entry(page):
    trigger_selectors = [
        'div[class*="addressWrp"]',
        'div[class*="address-wrp"]',
        'div[class*="addressWrap"]',
        'xpath=//*[contains(normalize-space(.), "宝贝所在地")]/following::div[contains(@class, "addressWrp")][1]',
        'xpath=//*[contains(normalize-space(.), "宝贝所在地")]/following::div[contains(@class, "address")][1]',
    ]

    for selector in trigger_selectors:
        try:
            candidates = await page.query_selector_all(selector)
        except Exception:
            continue

        for candidate in candidates:
            try:
                if not await candidate.is_visible():
                    continue
                box = await candidate.bounding_box()
                if not box or box.get("height", 0) < 20 or box.get("width", 0) < 80:
                    continue
                text = await _read_promotion_address_text(candidate)
                has_arrow = False
                try:
                    has_arrow = await candidate.query_selector('[class*="arrow"]') is not None
                except Exception:
                    has_arrow = False
                if not text and not has_arrow:
                    continue
                return candidate, text
            except Exception:
                continue

    return None, ""


async def set_promotion_item_address(
    publisher: Any,
    item_data: dict,
    fallback_set_item_address: Callable[[dict], Awaitable[None]],
) -> None:
    page = publisher.page
    if not page:
        raise Exception("浏览器页面未初始化")

    address = str(item_data.get("address") or "").strip()
    expected_text = str(item_data.get("address_expected_text") or "").strip()
    if not address:
        raise Exception("未获取到可用的宝贝所在地")

    if expected_text:
        logger.info(f"\n[步骤13] 📍 设置宝贝所在地，搜索关键词: {address}，期望文本: {expected_text}")
    else:
        logger.info(f"\n[步骤13] 📍 设置宝贝所在地，搜索关键词: {address}")

    target_texts: list[str] = []
    for value in [expected_text, address]:
        normalized_value = _normalize_address_text(value)
        if normalized_value and normalized_value not in target_texts:
            target_texts.append(normalized_value)

    trigger, current_text = await _find_promotion_address_entry(page)
    if not trigger:
        logger.warning("⚠️ 返佣页面未识别到卖家页地址入口，回退通用地址逻辑继续尝试")
        return await fallback_set_item_address(item_data)

    if current_text:
        logger.info(f"当前宝贝所在地: {current_text}")
        normalized_current_text = _normalize_address_text(current_text)
        if any(target in normalized_current_text or normalized_current_text in target for target in target_texts):
            logger.info("✅ 当前宝贝所在地已符合要求，跳过设置")
            return

    text_node = None
    try:
        text_node = await trigger.query_selector('[title], div[class*="address"], span[class*="address"]')
    except Exception:
        text_node = None

    click_targets = [trigger]
    if text_node:
        click_targets.insert(0, text_node)

    clicked = False
    for click_target in click_targets:
        try:
            await click_target.click(timeout=3000)
            clicked = True
            break
        except Exception:
            try:
                await click_target.click(timeout=3000, force=True)
                clicked = True
                break
            except Exception:
                continue

    if not clicked:
        raise Exception("未找到宝贝所在地设置入口")

    await asyncio.sleep(1.5)

    panel = None
    panel_selectors = [
        '.ant-modal-content',
        '.ant-modal-wrap',
        '.ant-drawer-content',
        '.ant-drawer-body',
        '[role="dialog"]',
        '[class*="drawer"]',
        '[class*="popover"]',
        '[class*="dropdown"]',
        '[class*="addressPanel"]',
    ]
    for selector in panel_selectors:
        try:
            panels = await page.query_selector_all(selector)
        except Exception:
            continue

        for current_panel in panels:
            try:
                if not await current_panel.is_visible():
                    continue
                panel_text = re.sub(r"\s+", " ", str(await current_panel.inner_text() or "")).strip()
                if any(text in panel_text for text in ["宝贝所在地", "常用地址", "附近地址", "精准地址", "小区", "写字楼", "学校", "搜索"]):
                    panel = current_panel
                    logger.info(f"✅ 已识别返佣地址选择层: {selector}")
                    break
            except Exception:
                continue

        if panel:
            break

    roots: list[tuple[str, Any]] = []
    if panel:
        roots.append(("地址选择层", panel))
    else:
        logger.info("ℹ️ 未识别到独立地址弹层，改为在当前页面继续查找地址搜索框")
    roots.append(("页面", page))

    input_selectors = [
        'input[placeholder*="请输入"]',
        'input[placeholder*="地址"]',
        'input[placeholder*="位置"]',
        'input[placeholder*="小区"]',
        'input[placeholder*="学校"]',
        'input[placeholder*="写字楼"]',
        'input[placeholder*="搜索"]',
        'input[aria-label*="地址"]',
        'input[aria-label*="搜索"]',
        'input',
    ]

    search_input = None
    input_box = None
    for root_name, root in roots:
        for selector in input_selectors:
            try:
                inputs = await root.query_selector_all(selector)
            except Exception:
                continue

            for current_input in inputs:
                try:
                    if not await current_input.is_visible():
                        continue
                    placeholder = str(await current_input.get_attribute("placeholder") or "")
                    aria_label = str(await current_input.get_attribute("aria-label") or "")
                    normalized_marker = _normalize_address_text(f"{placeholder}{aria_label}")
                    if selector == 'input' and panel is None and not any(keyword in normalized_marker for keyword in ["请输入", "地址", "位置", "搜索", "小区", "学校", "写字楼"]):
                        continue
                    box = await current_input.bounding_box()
                    if not box or box.get("height", 0) < 20 or box.get("width", 0) < 80:
                        continue
                    search_input = current_input
                    input_box = box
                    logger.info(f"✅ 在{root_name}中找到宝贝所在地搜索框: {selector}")
                    break
                except Exception:
                    continue

            if search_input:
                break

        if search_input:
            break

    if not search_input:
        _, refreshed_text = await _find_promotion_address_entry(page)
        if refreshed_text:
            normalized_refreshed_text = _normalize_address_text(refreshed_text)
            if any(target in normalized_refreshed_text or normalized_refreshed_text in target for target in target_texts):
                logger.info("✅ 点击地址入口后已自动匹配到目标地址")
                return
        raise Exception("未找到宝贝所在地搜索框")

    await search_input.click()
    await asyncio.sleep(0.3)
    try:
        await search_input.fill("")
    except Exception:
        try:
            await search_input.press("Control+A")
            await search_input.press("Backspace")
        except Exception:
            pass
    await asyncio.sleep(0.4)
    await search_input.type(address, delay=150)
    await asyncio.sleep(2.5)

    option_selectors = [
        '[class*="item"]',
        '[class*="option"]',
        '[role="option"]',
        'li',
        'div',
        'span',
        'button',
        'a',
    ]
    best_option = None
    best_text = ""
    best_score = None
    normalized_expected = _normalize_address_text(expected_text)
    normalized_address = _normalize_address_text(address)

    for root_name, root in roots:
        for selector in option_selectors:
            try:
                options = await root.query_selector_all(selector)
            except Exception:
                continue

            for option in options:
                try:
                    if not await option.is_visible():
                        continue
                    option_text = re.sub(r"\s+", " ", str(await option.inner_text() or "")).strip()
                    normalized_option_text = _normalize_address_text(option_text)
                    if not normalized_option_text:
                        continue
                    if any(text in option_text for text in ["宝贝所在地", "搜索", "清空", "常用地址", "附近地址", "选择精准地址", "帮你推给更多同城买家"]):
                        continue
                    if len(normalized_option_text) < 2 or len(normalized_option_text) > 80:
                        continue
                    if not any(target in normalized_option_text or normalized_option_text in target for target in target_texts):
                        continue
                    box = await option.bounding_box()
                    if not box or box.get("height", 0) < 18 or box.get("width", 0) < 40:
                        continue
                    if input_box:
                        if box.get("y", 0) + box.get("height", 0) <= input_box.get("y", 0):
                            continue
                        if box.get("y", 0) - input_box.get("y", 0) > 700:
                            continue
                        if box.get("x", 0) + box.get("width", 0) < input_box.get("x", 0) - 120:
                            continue
                        if box.get("x", 0) > input_box.get("x", 0) + input_box.get("width", 0) + 360:
                            continue

                    match_level = 4
                    if normalized_expected:
                        if normalized_option_text == normalized_expected:
                            match_level = 0
                        elif normalized_expected in normalized_option_text:
                            match_level = 1
                    if match_level == 4 and normalized_address:
                        if normalized_option_text == normalized_address:
                            match_level = 2
                        elif normalized_address in normalized_option_text:
                            match_level = 3

                    score = (match_level, len(option_text), box.get("y", 0), box.get("x", 0), 0 if root_name == "地址选择层" else 1)
                    if best_score is None or score < best_score:
                        best_option = option
                        best_text = option_text
                        best_score = score
                except Exception:
                    continue

    if not best_option:
        raise Exception(f"未找到“{address}”对应的宝贝所在地候选")

    logger.info(f"🎯 选择返佣宝贝所在地候选: {best_text}")
    await best_option.click()
    await asyncio.sleep(1)

    confirm_selectors = [
        '.ant-modal-footer button.ant-btn-primary',
        '.ant-modal-footer button',
        'button:has-text("确定")',
        'button:has-text("确认")',
        'button:has-text("完成")',
        '[role="button"]:has-text("确定")',
        '[role="button"]:has-text("确认")',
    ]
    for root_name, root in roots:
        confirmed = False
        for selector in confirm_selectors:
            try:
                confirm_button = await root.query_selector(selector)
                if confirm_button and await confirm_button.is_visible() and await confirm_button.is_enabled():
                    await confirm_button.click()
                    await asyncio.sleep(1)
                    logger.info(f"✅ 已在{root_name}中确认宝贝所在地")
                    confirmed = True
                    break
            except Exception:
                continue
        if confirmed:
            break

    await asyncio.sleep(1)
    _, selected_text = await _find_promotion_address_entry(page)
    if selected_text:
        logger.info(f"当前已选择宝贝所在地: {selected_text}")
        normalized_selected_text = _normalize_address_text(selected_text)
        if any(target in normalized_selected_text or normalized_selected_text in target for target in target_texts):
            logger.info("✅ 宝贝所在地设置完成")
            return

    raise Exception(f"宝贝所在地设置后校验失败，当前显示: {selected_text or '空'}")
