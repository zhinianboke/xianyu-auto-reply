"""自动发货共用的禁止发货预检查及关单动作；API关键词使用严格异常检查。"""
from __future__ import annotations

from loguru import logger

from app.services.xianyu.delivery_rules.rule_engine import execute_rules
from common.db.session import async_session_maker
from common.utils.cookie_refresh import get_account_by_identity
from common.utils.fish_nick_utils import get_buyer_fish_nick
from common.utils.xianyu_utils import trans_cookies


class DeliveryPrecheckMixin:
    """复用各发货入口的规则和拦截动作，严格模式的错误交由调用方展示。"""

    async def pre_delivery_check_and_close(
        self,
        websocket,
        order_no: str,
        buyer_id: str,
        chat_id: str | None = None,
        log_prefix: str = '',
        item_id: str | None = None,
        *, strict: bool = False,
    ) -> dict:
        """禁止发货预检查 + 主动关闭订单（统一收口入口）

        所有发货入口（手动发货 / 定时补发货 / 消息触发自动发货 / 卡片更新 / 小刀
        卡片 / 重发货关键字）调用此方法即可获得一致的拦截行为。

        流程（规则引擎化）：
          1. 从 xy_delivery_block_rules 表加载该账号所有已启用规则（按 priority 排序）
          2. 无已启用规则 → 直接放行 action='allow'
          3. 逐条执行规则检查：
             - 每条规则先检查自己的排除商品列表，命中则跳过本规则
             - 规则检查通过 → 继续下一条
             - 规则命中 → 执行拦截动作（发消息/写fail_reason/关单）
          4. 首条命中即停，用该规则自己的配置决定后续动作
          5. 全部通过 → 放行 action='allow'

        Args:
            websocket: 用于向买家发送禁止发货提示消息的 WebSocket 连接
            order_no: 订单号
            buyer_id: 买家用户ID
            chat_id: 聊天会话ID（缺失时不发消息但仍拦截 + 关闭订单）
            log_prefix: 日志前缀
            item_id: 当前订单对应的商品ID
            strict: API关键词使用严格检查，账号/规则读取或执行失败时抛出中文错误。

        Returns:
            {
                'action': 'allow' | 'block' | 'card_only',
                'blocked': bool,             # 仅在 action=='block' 时为 True
                'reason_text': str,          # 配置的禁止发货原因
                'fail_record': str,          # 写入 delivery_fail_reason 的文案
                'auto_close_enabled': bool,  # 是否开启了主动关闭订单
                'order_closed': bool,        # 关闭订单是否成功
                'only_card_enabled': bool,   # 是否开启"关闭订单后继续发货"
                'total_count': int,          # 兼容字段（-1 表示未使用旧逻辑）
                'rule_code': str | None,     # 命中的规则编码
                'rule_name': str | None,     # 命中的规则名称
            }
        """
        pf = log_prefix or f'【{self.cookie_id}】'

        # 获取买家闲鱼昵称（明文），存到实例属性供后续写入订单
        self._current_buyer_fish_nick = None
        if chat_id:
            try:
                latest_cookies = self.cookies_str
                try:
                    async with async_session_maker() as db_session:
                        account = await get_account_by_identity(self.cookie_id, session=db_session)
                        if account and account.cookie:
                            latest_cookies = account.cookie
                            if latest_cookies != self.cookies_str:
                                self.cookies_str = latest_cookies
                                self.cookies = trans_cookies(latest_cookies)
                except Exception as db_e:  # noqa: BLE001 -- 昵称使用内存Cookie，不参与发货准入
                    logger.warning(f'{pf}从数据库获取最新Cookie失败，使用内存Cookie: {db_e}')

                self._current_buyer_fish_nick = await get_buyer_fish_nick(
                    latest_cookies, chat_id, self.cookie_id
                )
            except Exception as nick_e:  # noqa: BLE001 -- 昵称缺失不影响规则检查
                logger.warning(f'{pf}获取买家闲鱼昵称失败（不影响发货流程）: {nick_e}')

        # 查询账号所属用户ID与主键（供按用户维度判断的规则使用，如"买家在同用户其他账号已有订单"）
        account_owner_id = None
        account_pk = None
        try:
            async with async_session_maker() as owner_session:
                _acc = await get_account_by_identity(self.cookie_id, session=owner_session)
                if _acc:
                    account_owner_id = _acc.owner_id
                    account_pk = _acc.id
                elif strict:
                    raise ValueError("账号信息已失效，无法执行禁止发货检查")
        except Exception as owner_e:
            if strict:
                logger.exception("{}禁止发货账号信息读取失败", pf)
                raise ValueError("禁止发货账号信息读取失败，已停止API同步发货") from owner_e
            logger.warning(f'{pf}查询账号owner_id失败（不影响按账号维度的规则）: {self._safe_str(owner_e)}')

        # 调用规则引擎执行检查
        try:
            engine_result = await execute_rules(
                cookie_id=self.cookie_id,
                cookies_str=self.cookies_str,
                order_no=order_no,
                buyer_id=buyer_id,
                item_id=item_id,
                chat_id=chat_id,
                log_prefix=pf,
                account_pk=account_pk,
                owner_id=account_owner_id,
                strict=strict,
            )
        except Exception as e:
            if strict:
                logger.exception("{}禁止发货规则检查失败", pf)
                raise ValueError(f"禁止发货规则检查失败，已停止API同步发货：{e}") from e
            logger.error(f'{pf}规则引擎执行异常: {self._safe_str(e)}，放行')
            return {
                'action': 'allow',
                'blocked': False,
                'reason_text': '',
                'fail_record': '',
                'auto_close_enabled': False,
                'order_closed': False,
                'only_card_enabled': False,
                'total_count': -1,
                'rule_code': None,
                'rule_name': None,
                'buyer_fish_nick': self._current_buyer_fish_nick,
            }

        # 未命中任何规则 → 放行
        if not engine_result.get('hit'):
            return {
                'action': 'allow',
                'blocked': False,
                'reason_text': '',
                'fail_record': '',
                'auto_close_enabled': False,
                'order_closed': False,
                'only_card_enabled': False,
                'total_count': -1,
                'rule_code': None,
                'rule_name': None,
                'buyer_fish_nick': self._current_buyer_fish_nick,
            }

        # 命中规则 → 执行拦截动作
        rule_code = engine_result.get('rule_code', '')
        rule_name = engine_result.get('rule_name', '')
        block_reason = engine_result.get('block_reason', '')
        auto_close_enabled = engine_result.get('auto_close_order', False)
        only_card_enabled = engine_result.get('only_card_after_close', False)
        hit_reason = engine_result.get('reason', '')

        # 1. 发送禁止发货提示消息给买家
        if block_reason and chat_id:
            try:
                await self._send_msg_with_retry(websocket, chat_id, buyer_id, block_reason)
            except Exception as send_err:  # noqa: BLE001 -- 提示失败仍保留拦截结果
                logger.error(f'{pf}发送禁止发货提示消息异常: {self._safe_str(send_err)}')
        elif not block_reason:
            logger.info(f'{pf}规则 [{rule_name}] 未配置禁止发货原因，跳过发送消息: order_no={order_no}')
        elif not chat_id:
            logger.warning(f'{pf}缺少 chat_id，无法发送禁止发货提示: order_no={order_no}')

        # 2. 写订单 delivery_fail_reason
        fail_record = block_reason if block_reason else hit_reason
        try:
            await self._update_delivery_fail_reason(order_no, fail_record)
        except Exception as record_err:  # noqa: BLE001 -- 落库失败仍保留拦截结果
            logger.warning(f'{pf}记录禁止发货原因到订单表失败: {self._safe_str(record_err)}')

        # 3. 按开关关闭订单
        order_closed = False
        if auto_close_enabled:
            try:
                order_closed = await self.close_order_by_seller(order_no)
                if not order_closed:
                    logger.warning(f'{pf}禁止发货后关闭订单失败：order_no={order_no}')
            except Exception as close_err:  # noqa: BLE001 -- 关单失败仍返回禁止发货
                logger.error(f'{pf}禁止发货后关闭订单异常: {self._safe_str(close_err)}')
        else:
            logger.info(f'{pf}规则 [{rule_name}] 未开启"主动关闭订单"，跳过关闭: order_no={order_no}')

        # 4. 决定最终动作
        if auto_close_enabled and order_closed and only_card_enabled:
            action = 'card_only'
            logger.warning(
                f'{pf}❌ 命中规则 [{rule_name}] + 关闭订单成功 + 只发卡券：'
                f'order_no={order_no}, buyer_id={buyer_id}, reason={fail_record}'
            )
        else:
            action = 'block'
            logger.warning(
                f'{pf}❌ 命中规则 [{rule_name}]：order_no={order_no}, buyer_id={buyer_id}, '
                f'reason={fail_record}, auto_close={auto_close_enabled}, '
                f'order_closed={order_closed}, only_card={only_card_enabled}'
            )

        return {
            'action': action,
            'blocked': action == 'block',
            'reason_text': block_reason,
            'fail_record': fail_record,
            'auto_close_enabled': auto_close_enabled,
            'order_closed': order_closed,
            'only_card_enabled': only_card_enabled,
            'total_count': -1,
            'rule_code': rule_code,
            'rule_name': rule_name,
            'buyer_fish_nick': self._current_buyer_fish_nick,
        }

