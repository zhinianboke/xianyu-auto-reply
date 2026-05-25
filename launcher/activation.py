"""
激活码验证模块

功能：
1. 根据机器码 + 到期时间生成带有效期的激活码
2. 验证激活码是否匹配当前机器码且未过期
3. 保存/读取激活验证文件（含到期时间）
4. 提供到期时间查询接口供GUI显示
"""
import hashlib
import json
import os
import secrets
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 激活码生成用的密钥盐值
_SECRET_SALT = "XianyuAutoReply@2024#Lic"

# 验证文件名
_LICENSE_FILE = "license.dat"

# 北京时间时区
_BJ_TZ = timezone(timedelta(hours=8))


def _get_license_path() -> Path:
    """
    获取验证文件路径

    验证文件保存在exe同级目录，或项目根目录下的data文件夹中

    Returns:
        验证文件的完整路径
    """
    from launcher.frozen_detect import get_project_root
    base_dir = get_project_root()
    data_dir = base_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / _LICENSE_FILE


def _now_bj() -> datetime:
    """获取当前北京时间"""
    return datetime.now(_BJ_TZ)


def calc_expire_time(unit: str, amount: int) -> int:
    """
    根据维度和数量计算到期时间戳（北京时间）

    Args:
        unit: 时间维度，h=小时 d=天 m=月 y=年
        amount: 数量，必须为正整数
    Returns:
        到期时间的Unix时间戳（秒）
    """
    now = _now_bj()
    if unit == "h":
        expire = now + timedelta(hours=amount)
    elif unit == "d":
        expire = now + timedelta(days=amount)
    elif unit == "m":
        # 月份简单处理：每月按30天
        expire = now + timedelta(days=amount * 30)
    elif unit == "y":
        expire = now + timedelta(days=amount * 365)
    else:
        raise ValueError(f"不支持的时间维度: {unit}，可选: h/d/m/y")
    return int(expire.timestamp())


def generate_activation_code(machine_id: str, expire_ts: int) -> str:
    """
    根据机器码和到期时间戳生成激活码

    激活码格式: {到期时间戳hex大写}-{签名16位大写}
    签名 = SHA256(机器码:到期时间戳:盐) 取前16位

    Args:
        machine_id: 32位大写机器码
        expire_ts: 到期时间的Unix时间戳（秒）
    Returns:
        激活码字符串，格式如 "67E3A1B0-A1B2C3D4E5F67890"
    """
    expire_hex = format(expire_ts, "X")
    sig = hashlib.sha256(
        f"{machine_id}:{expire_ts}:{_SECRET_SALT}".encode("utf-8")
    ).hexdigest()[:16].upper()
    return f"{expire_hex}-{sig}"


def verify_activation_code(machine_id: str, activation_code: str) -> dict:
    """
    验证激活码是否匹配机器码，并提取到期时间

    Args:
        machine_id: 32位大写机器码
        activation_code: 激活码字符串
    Returns:
        字典包含:
        - valid: bool 签名是否有效
        - expire_ts: int 到期时间戳（签名无效时为0）
        - expired: bool 是否已过期
    """
    code = activation_code.strip().upper()
    parts = code.split("-")
    if len(parts) != 2:
        return {"valid": False, "expire_ts": 0, "expired": True}

    try:
        expire_ts = int(parts[0], 16)
    except ValueError:
        return {"valid": False, "expire_ts": 0, "expired": True}

    expected_sig = hashlib.sha256(
        f"{machine_id}:{expire_ts}:{_SECRET_SALT}".encode("utf-8")
    ).hexdigest()[:16].upper()

    if parts[1] != expected_sig:
        return {"valid": False, "expire_ts": 0, "expired": True}

    now_ts = int(_now_bj().timestamp())
    return {
        "valid": True,
        "expire_ts": expire_ts,
        "expired": now_ts > expire_ts,
    }


def save_license(machine_id: str, activation_code: str,
                 expire_ts: int, used_renew_codes: list = None,
                 last_renew_ts: int = 0) -> bool:
    """
    保存激活信息到验证文件

    Args:
        machine_id: 32位大写机器码
        activation_code: 激活码
        expire_ts: 到期时间戳
        used_renew_codes: 已使用的续期码列表（可选）
        last_renew_ts: 上次续期时间戳（可选，用于一天只能续期一次的校验）
    Returns:
        True保存成功，False保存失败
    """
    try:
        check_hash = hashlib.sha256(
            f"{machine_id}:{activation_code}:{expire_ts}:{_SECRET_SALT}"
            .encode("utf-8")
        ).hexdigest()[:16].upper()

        data = {
            "machine_id": machine_id,
            "activation_code": activation_code.upper(),
            "expire_ts": expire_ts,
            "check_hash": check_hash,
            "used_renew_codes": used_renew_codes or [],
            "last_renew_ts": last_renew_ts,
        }
        license_path = _get_license_path()
        license_path.write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )
        return True
    except Exception:
        return False


def load_and_verify_license(current_machine_id: str) -> dict:
    """
    加载验证文件并校验激活状态

    检查内容：文件存在性、防篡改哈希、机器码匹配、
    激活码签名、是否已过期。

    Args:
        current_machine_id: 当前机器的机器码
    Returns:
        字典包含:
        - valid: bool 是否激活有效（签名正确且未过期）
        - message: str 状态说明
        - machine_changed: bool 机器码是否发生变化
        - expire_ts: int 到期时间戳（0表示未知）
        - expired: bool 是否已过期
    """
    license_path = _get_license_path()
    _fail = {"valid": False, "machine_changed": False,
             "expire_ts": 0, "expired": False}

    if not license_path.exists():
        return {**_fail, "message": "未找到激活文件，请输入激活码"}

    try:
        data = json.loads(license_path.read_text(encoding="utf-8"))
    except Exception:
        return {**_fail, "message": "激活文件损坏，请重新激活"}

    stored_mid = data.get("machine_id", "")
    stored_code = data.get("activation_code", "")
    stored_expire = data.get("expire_ts", 0)
    stored_hash = data.get("check_hash", "")

    # 校验文件完整性（防篡改）
    expected_hash = hashlib.sha256(
        f"{stored_mid}:{stored_code}:{stored_expire}:{_SECRET_SALT}"
        .encode("utf-8")
    ).hexdigest()[:16].upper()

    if stored_hash != expected_hash:
        return {**_fail, "message": "激活文件已被篡改，请重新激活"}

    # 检查机器码（同机兼容：允许不同生成方式下得到的候选机器码）
    try:
        from launcher.hardware_id import generate_machine_id_candidates
        candidates = set(generate_machine_id_candidates())
        candidates.add(current_machine_id)
    except Exception:
        candidates = {current_machine_id}

    if stored_mid not in candidates:
        return {**_fail, "message": "检测到硬件变更，机器码已变化，请重新激活",
                "machine_changed": True}

    # 验证激活码签名：必须用 license 中存储的 machine_id（激活码签名与之绑定）
    result = verify_activation_code(stored_mid, stored_code)
    if not result["valid"]:
        return {**_fail, "message": "激活码无效，请重新输入"}

    # 检查是否过期
    if result["expired"]:
        expire_str = format_expire_time(result["expire_ts"])
        return {**_fail, "message": f"激活码已过期（{expire_str}），可输入续期码继续进入系统",
                "expire_ts": result["expire_ts"], "expired": True}

    return {
        "valid": True,
        "message": "激活验证通过",
        "machine_changed": False,
        "expire_ts": result["expire_ts"],
        "expired": False,
    }


def calc_duration_seconds(unit: str, amount: int) -> int:
    """
    根据维度和数量计算时长（秒数）

    Args:
        unit: 时间维度，h=小时 d=天 m=月 y=年
        amount: 数量，必须为正整数
    Returns:
        时长秒数
    """
    if unit == "h":
        return amount * 3600
    elif unit == "d":
        return amount * 86400
    elif unit == "m":
        return amount * 30 * 86400
    elif unit == "y":
        return amount * 365 * 86400
    else:
        raise ValueError(f"不支持的时间维度: {unit}，可选: h/d/m/y")


def _build_renew_signature(machine_id: str, duration_seconds: int, issue_marker: str | None = None) -> str:
    if issue_marker is None:
        payload = f"{machine_id}:R:{duration_seconds}:{_SECRET_SALT}"
    else:
        payload = f"{machine_id}:R:{duration_seconds}:{issue_marker}:{_SECRET_SALT}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16].upper()


def generate_renew_code(machine_id: str, duration_seconds: int) -> str:
    """
    生成续期激活码（以R开头，区别于普通激活码）

    续期码格式: R{时长秒数hex大写}-{签名16位大写}
    签名 = SHA256(机器码:R:时长秒数:盐) 取前16位

    Args:
        machine_id: 32位大写机器码
        duration_seconds: 要续期的时长（秒）
    Returns:
        续期码字符串，格式如 "R278D00-A1B2C3D4E5F67890"
    """
    issue_marker = secrets.token_hex(8).upper()
    dur_hex = format(duration_seconds, "X")
    sig = _build_renew_signature(machine_id, duration_seconds, issue_marker)
    return f"R{dur_hex}-{issue_marker}-{sig}"


def verify_renew_code(machine_id: str, renew_code: str) -> dict:
    """
    验证续期激活码是否匹配机器码，并提取续期时长

    Args:
        machine_id: 32位大写机器码
        renew_code: 续期码字符串（以R开头）
    Returns:
        字典包含:
        - valid: bool 签名是否有效
        - duration_seconds: int 续期时长秒数（无效时为0）
    """
    code = renew_code.strip().upper()
    if not code.startswith("R"):
        return {"valid": False, "duration_seconds": 0}

    # 去掉R前缀
    body = code[1:]
    parts = body.split("-")
    if len(parts) not in (2, 3):
        return {"valid": False, "duration_seconds": 0}

    try:
        duration_seconds = int(parts[0], 16)
    except ValueError:
        return {"valid": False, "duration_seconds": 0}

    if len(parts) == 2:
        expected_sig = _build_renew_signature(machine_id, duration_seconds)
        actual_sig = parts[1]
    else:
        issue_marker = parts[1].strip().upper()
        if not issue_marker:
            return {"valid": False, "duration_seconds": 0}
        try:
            int(issue_marker, 16)
        except ValueError:
            return {"valid": False, "duration_seconds": 0}
        expected_sig = _build_renew_signature(machine_id, duration_seconds, issue_marker)
        actual_sig = parts[2]

    if actual_sig != expected_sig:
        return {"valid": False, "duration_seconds": 0}

    return {"valid": True, "duration_seconds": duration_seconds}


def _load_used_renew_codes() -> list:
    """
    从验证文件中加载已使用的续期码列表

    Returns:
        已使用续期码的字符串列表，文件不存在或解析失败返回空列表
    """
    license_path = _get_license_path()
    if not license_path.exists():
        return []
    try:
        data = json.loads(license_path.read_text(encoding="utf-8"))
        return data.get("used_renew_codes", [])
    except Exception:
        return []


def _load_last_renew_ts() -> int:
    """
    从验证文件中加载上次续期时间戳

    Returns:
        上次续期的Unix时间戳，文件不存在或无记录返回0
    """
    license_path = _get_license_path()
    if not license_path.exists():
        return 0
    try:
        data = json.loads(license_path.read_text(encoding="utf-8"))
        return data.get("last_renew_ts", 0)
    except Exception:
        return 0


def renew_license(machine_id: str, renew_code: str) -> dict:
    """
    使用续期码对现有激活进行续期（时长叠加到原到期时间）

    Args:
        machine_id: 32位大写机器码
        renew_code: 续期码字符串
    Returns:
        字典包含:
        - success: bool 续期是否成功
        - message: str 结果说明
        - new_expire_ts: int 新的到期时间戳（失败时为0）
    """
    # 验证续期码
    code_upper = renew_code.strip().upper()
    verify_result = verify_renew_code(machine_id, code_upper)
    if not verify_result["valid"]:
        return {"success": False, "message": "续期码无效，请检查是否输入正确",
                "new_expire_ts": 0}

    duration = verify_result["duration_seconds"]

    # 加载当前激活信息
    license_result = load_and_verify_license(machine_id)
    old_expire_ts = license_result.get("expire_ts", 0)

    # 检查续期码是否已经使用过
    used_codes = _load_used_renew_codes()
    if code_upper in used_codes:
        return {"success": False, "message": "该续期码已使用过，不能重复使用",
                "new_expire_ts": 0}

    # 检查一天只能续期一次
    last_renew = _load_last_renew_ts()
    if last_renew > 0:
        now_ts = int(_now_bj().timestamp())
        elapsed = now_ts - last_renew
        if elapsed < 86400:
            remaining_hours = (86400 - elapsed) // 3600
            remaining_mins = ((86400 - elapsed) % 3600) // 60
            return {"success": False,
                    "message": f"每天只能续期一次，请{remaining_hours}小时{remaining_mins}分钟后再试",
                    "new_expire_ts": 0}

    if old_expire_ts <= 0:
        # 没有有效激活记录，从当前时间开始计算
        base_ts = int(_now_bj().timestamp())
    elif license_result.get("expired", False):
        # 已过期，从当前时间开始计算
        base_ts = int(_now_bj().timestamp())
    else:
        # 未过期，叠加到原到期时间
        base_ts = old_expire_ts

    new_expire_ts = base_ts + duration

    # 生成新的普通激活码（用新的到期时间）
    new_code = generate_activation_code(machine_id, new_expire_ts)

    # 记录已使用的续期码和本次续期时间并保存
    used_codes.append(code_upper)
    current_ts = int(_now_bj().timestamp())
    if not save_license(machine_id, new_code, new_expire_ts, used_codes,
                        last_renew_ts=current_ts):
        return {"success": False, "message": "保存激活信息失败",
                "new_expire_ts": 0}

    expire_str = format_expire_time(new_expire_ts)
    return {"success": True,
            "message": f"续期成功，新到期时间: {expire_str}",
            "new_expire_ts": new_expire_ts}


def revoke_license() -> dict:
    """
    注销激活状态，删除激活验证文件

    Returns:
        字典包含:
        - success: bool 注销是否成功
        - message: str 结果说明
    """
    license_path = _get_license_path()
    if not license_path.exists():
        return {"success": False, "message": "当前没有激活记录"}
    try:
        license_path.unlink()
        return {"success": True, "message": "激活已注销，请重新激活"}
    except Exception as e:
        return {"success": False, "message": f"注销失败: {e}"}


def format_expire_time(expire_ts: int) -> str:
    """
    将到期时间戳格式化为北京时间字符串

    Args:
        expire_ts: Unix时间戳
    Returns:
        格式化字符串，如 "2026-03-30 18:00:00"
    """
    if expire_ts <= 0:
        return "未知"
    dt = datetime.fromtimestamp(expire_ts, tz=_BJ_TZ)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def get_remaining_text(expire_ts: int) -> str:
    """
    计算剩余时间并返回可读文本

    Args:
        expire_ts: 到期时间戳
    Returns:
        剩余时间文本，如 "剩余 3天12小时" 或 "已过期"
    """
    if expire_ts <= 0:
        return "未知"
    now_ts = int(_now_bj().timestamp())
    diff = expire_ts - now_ts
    if diff <= 0:
        return "已过期"

    days = diff // 86400
    hours = (diff % 86400) // 3600
    minutes = (diff % 3600) // 60

    if days > 0:
        return f"剩余 {days}天{hours}小时"
    elif hours > 0:
        return f"剩余 {hours}小时{minutes}分钟"
    else:
        return f"剩余 {minutes}分钟"
