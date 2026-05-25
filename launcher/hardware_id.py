"""
机器码生成模块

功能：
1. 采集主板序列号、CPU ID、硬盘序列号等硬件信息
2. 基于硬件信息生成唯一且不可变的机器码
3. 使用SHA256哈希确保机器码格式统一
"""
import hashlib
import platform
import subprocess
import re
import time
from typing import Callable, List


def _run_wmic(command: str) -> str:
    """
    执行WMIC命令并返回结果
    
    Args:
        command: WMIC命令字符串
    Returns:
        命令输出的文本内容，失败返回空字符串
    """
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            shell=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
        )
        output = result.stdout.strip()
        # 去掉第一行标题
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        if len(lines) > 1:
            return lines[1]
        return lines[0] if lines else ""
    except Exception:
        return ""


def _run_powershell_cim(wmi_class: str, prop: str) -> str:
    """使用 PowerShell CIM 查询硬件信息（作为 WMIC 的兜底）。

    WMIC 在部分 Windows 版本/精简环境下可能不可用或返回空。
    """
    if platform.system() != "Windows":
        return ""
    try:
        ps = (
            "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::UTF8; "
            f"(Get-CimInstance -ClassName {wmi_class} | Select-Object -First 1 -ExpandProperty {prop})"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return (result.stdout or "").strip()
    except Exception:
        return ""


def _normalize_hw_value(val: str) -> str:
    """规范化硬件字段，降低不同命令输出格式差异导致的波动。"""
    if not val:
        return ""
    v = val.strip()
    v = re.sub(r"\s+", " ", v)
    v = v.replace("\u0000", "").strip()
    return v


def _is_invalid_hw_value(val: str) -> bool:
    """判断硬件字段是否为无效/占位值。

    WMIC/CIM 在部分环境下可能返回字段名、空、或厂商占位字符串，导致机器码不稳定。
    """
    if not val:
        return True
    v = _normalize_hw_value(val)
    if not v:
        return True

    v_lower = v.lower()
    invalid_tokens = (
        "serialnumber",
        "processorid",
        "none",
        "null",
        "unknown",
        "not available",
        "to be filled",
        "to be filled by o.e.m.",
        "default string",
        "o.e.m.",
    )
    return any(t in v_lower for t in invalid_tokens)


def _first_non_empty(*vals: str) -> str:
    for v in vals:
        v2 = _normalize_hw_value(v)
        if v2 and not _is_invalid_hw_value(v2):
            return v2
    return ""


def _get_with_retries(getter: Callable[[], str], retries: int = 2) -> str:
    """多次读取同一硬件信息，取第一个非空结果，避免偶发空值。"""
    for _ in range(max(1, retries)):
        v = _normalize_hw_value(getter())
        if v and not _is_invalid_hw_value(v):
            return v
        time.sleep(0.2)
    return ""


def _get_windows_machine_guid() -> str:
    """读取 Windows MachineGuid（稳定兜底）。

    说明：当 WMIC/CIM 无法稳定读取硬件序列号时，用 MachineGuid 作为兜底，
    避免同一台机器每次启动机器码都变化。
    """
    if platform.system() != "Windows":
        return ""
    try:
        import winreg

        key_path = r"SOFTWARE\Microsoft\Cryptography"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            val, _ = winreg.QueryValueEx(key, "MachineGuid")
            return _normalize_hw_value(str(val))
    except Exception:
        return ""


def get_motherboard_serial() -> str:
    """
    获取主板序列号
    
    Returns:
        主板序列号字符串
    """
    wmic_val = _run_wmic("wmic baseboard get serialnumber")
    cim_val = _run_powershell_cim("Win32_BaseBoard", "SerialNumber")
    return _first_non_empty(wmic_val, cim_val)


def get_cpu_id() -> str:
    """
    获取CPU处理器ID
    
    Returns:
        CPU处理器ID字符串
    """
    wmic_val = _run_wmic("wmic cpu get processorid")
    cim_val = _run_powershell_cim("Win32_Processor", "ProcessorId")
    return _first_non_empty(wmic_val, cim_val)


def get_bios_serial() -> str:
    """
    获取BIOS序列号
    
    Returns:
        BIOS序列号字符串
    """
    wmic_val = _run_wmic("wmic bios get serialnumber")
    cim_val = _run_powershell_cim("Win32_BIOS", "SerialNumber")
    return _first_non_empty(wmic_val, cim_val)


def generate_machine_id() -> str:
    """
    根据多项硬件信息生成唯一机器码
    
    只使用CPU ID、主板序列号、BIOS序列号三个固定硬件信息，
    不使用硬盘序列号（因为外接设备插拔会导致wmic返回值变化）。
    拼接后做SHA256哈希，取前32位大写十六进制字符串作为机器码。
    
    Returns:
        32位大写十六进制机器码字符串
    """
    # EXE 环境下 WMIC/CIM 读取硬件序列号可能不稳定，优先使用 MachineGuid 生成稳定机器码
    guid_mid = _generate_machine_guid_machine_id()
    if guid_mid:
        return guid_mid
    mid = _generate_hw_machine_id_strict()
    if mid:
        return mid
    # 极端情况下都取不到，仍返回一个固定格式（但会导致激活不通过）
    raw = "UNKNOWN"
    hash_value = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return hash_value[:32].upper()


def _generate_machine_guid_machine_id() -> str:
    """基于 Windows MachineGuid 生成稳定机器码（兜底方案）。"""
    guid = _get_windows_machine_guid()
    if not guid or _is_invalid_hw_value(guid):
        return ""
    raw = f"MACHINEGUID|{guid}"
    hash_value = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return hash_value[:32].upper()


def _generate_hw_machine_id_strict() -> str:
    """严格使用主板/CPU/BIOS生成机器码。

    注意：任何一个字段无效/为空都返回空，避免在 EXE 环境下偶发空值导致机器码漂移。
    """
    parts = [
        _get_with_retries(get_motherboard_serial),
        _get_with_retries(get_cpu_id),
        _get_with_retries(get_bios_serial),
    ]
    if any(_is_invalid_hw_value(p) for p in parts):
        return ""
    raw = "|".join(parts)
    hash_value = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return hash_value[:32].upper()


def generate_machine_id_candidates() -> List[str]:
    """生成可能的机器码候选列表（用于激活校验兼容）。"""
    candidates: List[str] = []

    strict_hw = _generate_hw_machine_id_strict()
    if strict_hw:
        candidates.append(strict_hw)

    guid_mid = _generate_machine_guid_machine_id()
    if guid_mid:
        candidates.append(guid_mid)

    legacy = generate_legacy_machine_id()
    if legacy:
        candidates.append(legacy)

    # 去重保持顺序
    seen = set()
    uniq: List[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


def generate_legacy_machine_id() -> str:
    """
    生成旧版机器码（兼容已激活用户）
    
    旧版使用了硬盘序列号，此方法用于激活校验时兼容旧license.dat。
    注意：硬盘序列号通过wmic获取，只取第一个结果。
    
    Returns:
        32位大写十六进制机器码字符串（旧格式）
    """
    disk_serial = _run_wmic("wmic diskdrive get serialnumber")
    parts = [
        get_motherboard_serial(),
        get_cpu_id(),
        disk_serial,
        get_bios_serial(),
    ]
    raw = "|".join(parts)
    hash_value = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return hash_value[:32].upper()


if __name__ == "__main__":
    print("主板序列号:", get_motherboard_serial())
    print("CPU ID:", get_cpu_id())
    print("BIOS序列号:", get_bios_serial())
    print("新机器码:", generate_machine_id())
    print("旧机器码:", generate_legacy_machine_id())
