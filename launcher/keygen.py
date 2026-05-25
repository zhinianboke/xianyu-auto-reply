"""
激活码生成工具（交互式）

用法：
    python launcher/keygen.py

按提示依次输入机器码、时间维度、数量，即可生成激活码或续期码。
支持循环生成，输入 q 退出。
"""
import os
import sys

# 确保项目根目录在搜索路径中，支持直接运行本文件
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from launcher.activation import (
    calc_expire_time,
    calc_duration_seconds,
    generate_activation_code,
    generate_renew_code,
    format_expire_time,
)

# 维度中文映射
_UNIT_NAMES = {"h": "小时", "d": "天", "m": "月", "y": "年"}


def _input_machine_id():
    """输入并校验机器码，返回机器码或None（退出时）"""
    machine_id = input("请输入机器码（输入 q 退出）: ").strip().upper()
    if machine_id == "Q":
        return None
    if len(machine_id) != 32:
        print(f"错误: 机器码长度应为32位，当前{len(machine_id)}位，请重新输入")
        print()
        return "RETRY"
    try:
        int(machine_id, 16)
    except ValueError:
        print("错误: 机器码应为十六进制字符串（0-9, A-F）")
        print()
        return "RETRY"
    return machine_id


def _input_time_unit_and_amount():
    """输入时间维度和数量，返回(unit, amount)或None"""
    print("时间维度:  h=小时  d=天  m=月  y=年")
    unit = input("请输入时间维度: ").strip().lower()
    if unit not in _UNIT_NAMES:
        print(f"错误: 不支持的维度 '{unit}'，可选: h / d / m / y")
        print()
        return None

    amount_str = input(f"请输入{_UNIT_NAMES[unit]}数: ").strip()
    try:
        amount = int(amount_str)
    except ValueError:
        print(f"错误: 数量必须是正整数，收到: {amount_str}")
        print()
        return None
    if amount <= 0:
        print("错误: 数量必须大于0")
        print()
        return None
    return unit, amount


def main():
    """交互式生成激活码或续期码，按提示逐步输入"""
    print("=" * 50)
    print("  闲鱼自动回复系统 - 激活码生成工具")
    print("=" * 50)
    print()

    while True:
        # 选择生成类型
        print("请选择生成类型:")
        print("  1 = 激活码（首次激活）")
        print("  2 = 续期码（延长有效期）")
        code_type = input("请输入选项（输入 q 退出）: ").strip()
        if code_type.upper() == "Q":
            print("已退出")
            break
        if code_type not in ("1", "2"):
            print("错误: 请输入 1 或 2")
            print()
            continue

        # 输入机器码
        machine_id = _input_machine_id()
        if machine_id is None:
            print("已退出")
            break
        if machine_id == "RETRY":
            continue

        # 输入时间维度和数量
        result = _input_time_unit_and_amount()
        if result is None:
            continue
        unit, amount = result

        if code_type == "1":
            # 生成激活码
            expire_ts = calc_expire_time(unit, amount)
            code = generate_activation_code(machine_id, expire_ts)
            expire_str = format_expire_time(expire_ts)
            print()
            print("=" * 50)
            print(f"  类型:     激活码")
            print(f"  机器码:   {machine_id}")
            print(f"  有效期:   {amount}{_UNIT_NAMES[unit]}")
            print(f"  到期时间: {expire_str}")
            print(f"  激活码:   {code}")
            print("=" * 50)
        else:
            # 生成续期码
            duration = calc_duration_seconds(unit, amount)
            code = generate_renew_code(machine_id, duration)
            print()
            print("=" * 50)
            print(f"  类型:     续期码")
            print(f"  机器码:   {machine_id}")
            print(f"  续期时长: {amount}{_UNIT_NAMES[unit]}")
            print(f"  续期码:   {code}")
            print("=" * 50)
        print()


if __name__ == "__main__":
    main()
