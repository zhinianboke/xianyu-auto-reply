"""
滑块失败冷却管理器 —— 本地验证脚本（不依赖 pytest）

直接运行：
    python scripts/test_slider_fail_cooldown.py

覆盖：退避序列、封顶、mark_fail/is_cooling/remaining、过期解除、
clear 清零后重新计数、多账号隔离、空 cookie_id、单例。
"""
import os
import sys

# 把项目根加入 sys.path，使 common.* 可被 import
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 直接按文件路径加载被测模块，绕过 common/services/__init__.py 的运行时依赖
# （该 __init__ 会连带 import sqlalchemy 等本地未必安装的库）。
# 被测模块本身只依赖标准库，可独立加载。
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_slider_fail_cooldown_under_test",
    os.path.join(PROJECT_ROOT, "common", "services", "captcha", "slider_fail_cooldown.py"),
)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
BASE_COOLDOWN = _mod.BASE_COOLDOWN
MAX_COOLDOWN = _mod.MAX_COOLDOWN
SliderFailCooldownManager = _mod.SliderFailCooldownManager
slider_fail_cooldown_manager = _mod.slider_fail_cooldown_manager


class FakeClock:
    """可推进的假时钟，替换 manager._now 用。"""

    def __init__(self, start=1000.0):
        self.t = float(start)

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


def setup(start=1000.0):
    """每个用例独立的干净状态 + 假时钟。"""
    mgr = slider_fail_cooldown_manager
    mgr.reset()
    clock = FakeClock(start)
    mgr._now = clock  # 注入假时钟
    return mgr, clock


def test_constants():
    assert BASE_COOLDOWN == 120
    assert MAX_COOLDOWN == 1800


def test_cooldown_for_sequence():
    f = SliderFailCooldownManager._cooldown_for
    assert f(0) == 0.0
    assert f(1) == 120.0
    assert f(2) == 240.0
    assert f(3) == 480.0
    assert f(4) == 960.0
    assert f(5) == 1800.0  # 1920 封顶到 1800
    assert f(6) == 1800.0
    assert f(100) == 1800.0


def test_mark_fail_sets_cooldown():
    mgr, clock = setup()
    cd = mgr.mark_fail("acc1")
    assert cd == 120.0
    assert mgr.is_cooling("acc1") is True
    assert abs(mgr.remaining("acc1") - 120.0) < 0.01


def test_cooldown_expires():
    mgr, clock = setup()
    mgr.mark_fail("acc1")
    clock.advance(119)
    assert mgr.is_cooling("acc1") is True
    assert abs(mgr.remaining("acc1") - 1.0) < 0.01
    clock.advance(2)  # 累计 121s，越过 120s 冷却
    assert mgr.is_cooling("acc1") is False
    assert mgr.remaining("acc1") == 0.0


def test_backoff_escalation():
    mgr, clock = setup()
    cds = [mgr.mark_fail("acc1") for _ in range(6)]  # 同一时刻连续失败
    assert cds == [120.0, 240.0, 480.0, 960.0, 1800.0, 1800.0]
    # 连续失败后冷却被延长到最长一档
    assert mgr.remaining("acc1") == 1800.0


def test_clear_resets_count():
    mgr, clock = setup()
    mgr.mark_fail("acc1")
    mgr.mark_fail("acc1")  # count=2 → 240s
    assert mgr.is_cooling("acc1") is True
    mgr.clear("acc1")
    assert mgr.is_cooling("acc1") is False
    # 清零后再次失败从 count=1 重新计
    cd = mgr.mark_fail("acc1")
    assert cd == 120.0


def test_multi_account_isolation():
    mgr, clock = setup()
    mgr.mark_fail("A")
    assert mgr.is_cooling("A") is True
    assert mgr.is_cooling("B") is False
    mgr.mark_fail("B")
    assert mgr.is_cooling("B") is True
    # 清 A 不影响 B
    mgr.clear("A")
    assert mgr.is_cooling("A") is False
    assert mgr.is_cooling("B") is True
    # A、B 退避计数独立
    cd_a = mgr.mark_fail("A")  # A 重新 count=1 → 120
    assert cd_a == 120.0
    cd_b = mgr.mark_fail("B")  # B 原 count=1 → 再 mark count=2 → 240
    assert cd_b == 240.0


def test_empty_cookie_id():
    mgr, clock = setup()
    assert mgr.mark_fail("") == 0.0
    assert mgr.is_cooling("") is False
    assert mgr.remaining("") == 0.0


def test_clear_nonexistent_is_noop():
    mgr, clock = setup()
    mgr.clear("ghost")  # 不应抛异常
    assert mgr.is_cooling("ghost") is False


def test_singleton():
    a = SliderFailCooldownManager()
    b = SliderFailCooldownManager()
    assert a is b
    assert a is slider_fail_cooldown_manager


def test_mark_fail_extends_cooldown_on_repeat():
    mgr, clock = setup()
    mgr.mark_fail("acc1")  # count=1, until=1000+120=1120
    clock.advance(100)     # now=1100，仍在冷却
    assert mgr.is_cooling("acc1") is True
    cd = mgr.mark_fail("acc1")  # count=2, until 重置为 1100+240=1340
    assert cd == 240.0
    clock.advance(20)      # now=1120，原本 count=1 的冷却已过，但被延长了
    assert mgr.is_cooling("acc1") is True
    assert abs(mgr.remaining("acc1") - 220.0) < 0.01  # 1340-1120


TESTS = [
    test_constants,
    test_cooldown_for_sequence,
    test_mark_fail_sets_cooldown,
    test_cooldown_expires,
    test_backoff_escalation,
    test_clear_resets_count,
    test_multi_account_isolation,
    test_empty_cookie_id,
    test_clear_nonexistent_is_noop,
    test_singleton,
    test_mark_fail_extends_cooldown_on_repeat,
]


def main():
    failed = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS  {test.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL  {test.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"ERROR {test.__name__}: {type(exc).__name__}: {exc}")
    # 还原单例的 _now，避免影响同进程后续使用
    slider_fail_cooldown_manager._now = (
        SliderFailCooldownManager._now.__get__(slider_fail_cooldown_manager)
    )
    slider_fail_cooldown_manager.reset()

    print(f"\n{'=' * 40}\n{len(TESTS) - failed}/{len(TESTS)} 通过")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
