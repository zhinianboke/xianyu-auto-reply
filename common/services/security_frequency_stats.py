"""安全频率统计：合并当日三类真实审计，每条一次，完整七档计数及非递归关联候选。"""
from __future__ import annotations

import ipaddress
import asyncio
from collections import Counter, defaultdict
from datetime import timedelta

from sqlalchemy import case, select, union_all

from common.models.email_log import XYEmailLog
from common.models.registration_log import RegistrationLog
from common.models.user import User
from common.models.user_login_log import XYUserLoginLog
from common.services.auth_security_policy import (
    AUTH_COMMON_SUFFIXES_KEY, AUTH_FREQUENCY_KEYS, AUTH_SECURITY_DEFAULTS, normalize_security_setting,
)
from common.services.email_domain_policy import normalize_domain, normalize_suffixes
from common.utils.email_utils import normalize_email_address


def event_identity(email, ip) -> tuple[str | None, str | None]:
    """合法邮箱转完整IDNA域名；合法IP共用ipaddress规范，未知内容保持空值。"""
    suffix = normalized_ip = None
    normalized_email, error = normalize_email_address(email)
    if not error and normalized_email:
        suffix = normalize_domain(normalized_email.rsplit('@', 1)[1])
    if isinstance(ip, str) and '%' not in ip:
        try:
            normalized_ip = str(ipaddress.ip_address(ip.strip()))
        except ValueError:
            normalized_ip = None
    return suffix, normalized_ip


def initialize_statistics(settings: dict, now, details: dict) -> None:
    """校验其他配置前保留七档快照，非法阈值保留原文并标记，不能伪装为0。"""
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    windows = []
    for minutes, key in AUTH_FREQUENCY_KEYS.items():
        raw = settings.get(key, AUTH_SECURITY_DEFAULTS[key][0])
        try:
            threshold, valid = int(normalize_security_setting(key, raw)), True
        except ValueError:
            threshold, valid = raw, False
        windows.append({
            'minutes': minutes, 'threshold': threshold, 'threshold_valid': valid,
            'start_at': max(midnight, now - timedelta(minutes=minutes)).isoformat(),
            'end_at': now.isoformat(), 'suffix_counts': {}, 'ip_counts': {},
            'hit_suffixes': [], 'hit_ips': [],
        })
    details.update(windows=windows, day_start=midnight.isoformat(),
                   event_count=0, statistics_complete=False)


async def collect_statistics(session, settings: dict, now, details: dict) -> None:
    """查询当天零点至执行开始，成功失败都统计；原地保留完整窗口及候选。"""
    if not details.get('windows'):
        initialize_statistics(settings, now, details)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    windows = {window['minutes']: window for window in details['windows']}
    if any(not window['threshold_valid'] for window in windows.values()):
        raise ValueError('安全频率配置无效，请管理员修正后重试')
    thresholds = {minutes: window['threshold'] for minutes, window in windows.items()}
    common = set(normalize_suffixes(settings[AUTH_COMMON_SUFFIXES_KEY]).split(',')) - {''}
    details['common_suffixes'] = sorted(common)
    # 账号密码日志只通过真实关联用户或真实用户名定位绑定邮箱；没有匹配则为空。
    bound_email = select(User.email).where(case(
        (XYUserLoginLog.owner_id.is_not(None), User.id == XYUserLoginLog.owner_id),
        else_=User.username == XYUserLoginLog.login_account,
    )).correlate(XYUserLoginLog).limit(1).scalar_subquery()
    login_email = case((XYUserLoginLog.login_method == 'username_password', bound_email),
                       else_=XYUserLoginLog.login_account)
    query = union_all(*[
        select(email.label('email'), model.client_ip.label('ip'), model.created_at.label('occurred_at'))
        .where(model.created_at >= midnight, model.created_at <= now)
        for model, email in ((RegistrationLog, RegistrationLog.email), (XYEmailLog, XYEmailLog.recipient_email),
                             (XYUserLoginLog, login_email))
    ])
    counts = {minutes: (Counter(), Counter()) for minutes in windows}
    suffix_ips, ip_suffixes = defaultdict(set), defaultdict(set)
    count = 0
    result = await session.stream(query.execution_options(yield_per=1000))
    try:
        async for email, ip, occurred_at in result:
            count += 1
            suffix, normalized_ip = event_identity(email, ip)
            if suffix and normalized_ip:
                suffix_ips[suffix].add(normalized_ip)
                ip_suffixes[normalized_ip].add(suffix)
            for minutes in windows:
                if occurred_at >= max(midnight, now - timedelta(minutes=minutes)):
                    suffix_counts, ip_counts = counts[minutes]
                    if suffix:
                        suffix_counts[suffix] += 1
                    if normalized_ip:
                        ip_counts[normalized_ip] += 1
            if count % 1000 == 0:
                # 大批量统计也交还事件循环，使扫描超时及关闭收尾可及时生效。
                await asyncio.sleep(0)
    finally:
        # 故障或超时也保留已经读取的真实计数，明确标记扫描未完成，不能冒充零条结果。
        details['event_count'] = count
        for minutes, window in windows.items():
            suffix_counts, ip_counts = counts[minutes]
            window['suffix_counts'], window['ip_counts'] = dict(sorted(suffix_counts.items())), dict(sorted(ip_counts.items()))
            threshold = thresholds[minutes]
            window['hit_suffixes'] = sorted(key for key, value in suffix_counts.items() if threshold and value >= threshold)
            window['hit_ips'] = sorted(key for key, value in ip_counts.items() if threshold and value >= threshold)
        await result.close()
    details['statistics_complete'] = True
    direct_suffixes = set().union(*(set(window['hit_suffixes']) - common for window in windows.values()))
    direct_ips = set().union(*(set(window['hit_ips']) for window in windows.values()))
    candidates_suffixes, candidates_ips = set(direct_suffixes), set(direct_ips)
    # 只对直接命中项关联一次，关联所得项不再向外扩散。
    for suffix in direct_suffixes:
        candidates_ips.update(suffix_ips[suffix])
    for ip in direct_ips:
        candidates_suffixes.update(ip_suffixes[ip] - common)
    details.update(event_count=count, direct_suffixes=sorted(direct_suffixes), direct_ips=sorted(direct_ips),
                   candidate_suffixes=sorted(candidates_suffixes), candidate_ips=sorted(candidates_ips),
                   suffix_ip_associations={key: sorted(suffix_ips[key]) for key in sorted(direct_suffixes)},
                   ip_suffix_associations={key: sorted(ip_suffixes[key]) for key in sorted(direct_ips)})
