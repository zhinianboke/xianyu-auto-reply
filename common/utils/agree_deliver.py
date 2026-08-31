"""
同意后发货工具

功能：
1. 拼接「同意后发货」发给买家的提货信息（通知信息 + 提货URL）
2. 在提货URL上以 GET 参数追加订单号与订单表主键，与原URL已有参数合并
3. 推荐本系统提货页地址（供账号管理「提货URL」填写提示使用）
"""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# 提货URL上追加的订单参数名：orderNo=闲鱼订单号，orderId=订单表 xy_orders 主键
PICKUP_ORDER_NO_PARAM = "orderNo"
PICKUP_ORDER_ID_PARAM = "orderId"

# 本系统内置提货页的前端路由（与 frontend/src/App.tsx 的公开路由保持一致）
PICKUP_PAGE_PATH = "/agree-pickup"

# 公网部署时用于配置买家可访问地址的环境变量名（backend-web/.env）
PICKUP_PUBLIC_URL_ENV = "FRONTEND_PUBLIC_URL"

# 本机/内网地址特征：买家在公网无法访问，不能作为提货URL推荐给商家
_LOCAL_HOST_PREFIXES = (
    "localhost",
    "127.",
    "0.0.0.0",
    "::1",
    "[::1]",
    "192.168.",
    "10.",
    "169.254.",
)


def is_local_address(url: str | None) -> bool:
    """判断地址是否为本机/内网地址（买家在公网访问不到）

    Args:
        url: 待判断的地址（形如 http://host:port，可带路径）
    Returns:
        属于本机/内网地址返回 True；空值按 True 处理（不可用于对外）
    """
    text = (url or "").strip().lower()
    if not text:
        return True
    # 去掉协议与路径，只留 host[:port]
    if "://" in text:
        text = text.split("://", 1)[1]
    host = text.split("/", 1)[0].split("@")[-1]
    if host.startswith(_LOCAL_HOST_PREFIXES):
        return True
    # 172.16.0.0 ~ 172.31.255.255 为内网段
    if host.startswith("172."):
        parts = host.split(".")
        if len(parts) >= 2 and parts[1].isdigit() and 16 <= int(parts[1]) <= 31:
            return True
    return False


def resolve_pickup_page_url(
    configured_public_url: str | None,
    request_origin: str | None,
) -> tuple[str, str]:
    """推荐本系统提货页地址，并给出需要商家注意的提示语。

    取值优先级（买家在公网打开，必须给公网可达地址）：
    1. 环境变量 FRONTEND_PUBLIC_URL 配置的公网地址（非本机/内网时优先，最权威）
    2. 商家当前访问后台的地址（环境变量未配置或仍指向本机时兜底）
    3. 两者都是本机/内网地址：仍返回一个地址，但提示必须配置环境变量

    Args:
        configured_public_url: 环境变量 FRONTEND_PUBLIC_URL 的值
        request_origin: 商家当前访问后台的地址（由请求头 Origin/Referer 推导）
    Returns:
        (推荐提货URL, 提示语)。提示语为空字符串表示地址可直接使用
    """
    configured = (configured_public_url or "").strip().rstrip("/")
    origin = (request_origin or "").strip().rstrip("/")

    if configured and not is_local_address(configured):
        return f"{configured}{PICKUP_PAGE_PATH}", ""

    if origin and not is_local_address(origin):
        return (
            f"{origin}{PICKUP_PAGE_PATH}",
            f"当前使用你正在访问后台的地址。公网部署请在 backend-web/.env 配置"
            f" {PICKUP_PUBLIC_URL_ENV} 为买家可访问的公网地址，避免地址失效。",
        )

    # 两者都不可对外：优先回显商家当前实际访问的地址（至少对其本人是通的），并强提示配置环境变量
    base = origin or configured
    if not base:
        return (
            "",
            f"未能识别本系统公网地址，请在 backend-web/.env 配置 {PICKUP_PUBLIC_URL_ENV}"
            f" 为买家可访问的公网地址（例如 https://你的域名），保存后重启服务。",
        )
    return (
        f"{base}{PICKUP_PAGE_PATH}",
        f"当前地址为本机/内网地址，买家在公网无法打开。请在 backend-web/.env 把"
        f" {PICKUP_PUBLIC_URL_ENV} 改为买家可访问的公网地址（例如 https://你的域名），保存后重启服务。",
    )


def build_pickup_url(pickup_url: str | None, order_no: str | None, order_id: int | str | None) -> str:
    """在提货URL上追加订单号与订单表主键两个 GET 参数。

    原提货URL由用户自行配置，可能本来就带查询参数（如 ?src=xy），此时按 & 合并追加、
    不会重复出现 ?；原URL没有查询参数时才补 ?。原有同名参数以本次订单的值为准（覆盖），
    其余参数、路径与 #fragment 一律原样保留。

    调用方必须先确保订单号与主键都已取到：取不到主键属于发货失败，不应发出缺参数的提货链接。

    Args:
        pickup_url: 用户配置的原始提货URL
        order_no: 闲鱼订单号
        order_id: 订单表 xy_orders 主键
    Returns:
        追加参数后的提货URL；pickup_url 为空时返回空字符串
    Raises:
        ValueError: 订单号或主键为空（防止把 orderNo=、orderId=None 这类脏参数发给买家）
    """
    url = (pickup_url or "").strip()
    if not url:
        return ""
    order_no_value = str(order_no or "").strip()
    order_id_value = str(order_id if order_id is not None else "").strip()
    if not order_no_value or not order_id_value:
        raise ValueError("拼接提货URL失败：订单号或订单主键为空")
    parts = urlsplit(url)
    # keep_blank_values=True 保留原URL上形如 a= 的空值参数，避免合并后把它丢掉
    merged = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key not in (PICKUP_ORDER_NO_PARAM, PICKUP_ORDER_ID_PARAM)
    ]
    merged.append((PICKUP_ORDER_NO_PARAM, order_no_value))
    merged.append((PICKUP_ORDER_ID_PARAM, order_id_value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(merged), parts.fragment))


def build_agree_deliver_message(notify_message: str | None, pickup_url: str | None) -> str:
    """拼接同意后发货的提货信息。

    通知信息在上、提货URL在下，用换行拼接；任一为空则跳过该行。

    Args:
        notify_message: 通知用户信息（可为空）
        pickup_url: 提货URL（可为空）
    Returns:
        拼接后的消息文本；两者均为空时返回空字符串
    """
    parts: list[str] = []
    msg = (notify_message or "").strip()
    url = (pickup_url or "").strip()
    if msg:
        parts.append(msg)
    if url:
        parts.append(url)
    return "\n".join(parts)
