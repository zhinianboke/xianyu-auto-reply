"""
真实鼠标滑块求解引擎（可选，通过系统设置选择）

为什么需要它：
- 闲鱼/阿里 baxia 风控能区分「CDP 注入的鼠标事件」与「真实硬件鼠标事件」。
  实测：Playwright(CDP) 即使回放真人轨迹也被判 code=300（拒），而用 pyautogui 驱动
  物理光标回放同一条真人轨迹则 code=0（通过）。
- 因此业务场景用 SendInput、登录场景用 pyautogui 驱动物理光标，回放预先录制的真人轨迹，
  完成 NC 滑块验证；登录场景继续使用登录专用长位移样本和原有回放逻辑。

代价与限制：
- 运行期间会**接管桌面物理光标约 2~3 秒**，期间人不能同时用鼠标；
- 仅适用于**有图形桌面的 Windows**；无头 Linux / Docker 无法驱动物理鼠标，
  故依赖以「惰性导入」方式加载，导入失败时 REAL_MOUSE_AVAILABLE=False，上层自动回退原逻辑；
- 物理光标全局唯一，故本引擎以全局锁串行执行（同一时刻只解一个滑块）。

对外入口：run_real_mouse_verification(...) -> (是否成功, x5* cookies | None)
返回契约与 run_slider_verification 一致，便于编排层无缝切换。
"""
from __future__ import annotations

import atexit
import glob
import json
import os
import random
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from loguru import logger

from common.services.captcha.slider_stealth import URL_EXPIRED, CAPTCHA_NOT_REQUIRED
from common.services.captcha.weighted_scheduler import real_mouse_scheduler
from common.services.captcha.real_mouse_coordinates import (
    build_geometry_mapper,
    compute_slider_distance,
)
from common.services.captcha.windows_foreground import (
    activate_page_window,
    activate_window,
)
from common.services.captcha.win_input import (
    precise_sleep,
    send_button,
    send_move_abs,
    timer_resolution,
)

from playwright.sync_api import sync_playwright

# —— 惰性/可选依赖：仅在有桌面的 Windows 上可用，导入失败则标记为不可用 ——
try:
    import pyautogui

    pyautogui.PAUSE = 0
    pyautogui.FAILSAFE = False
    REAL_MOUSE_AVAILABLE = True
except Exception as _e:  # noqa: BLE001  （任何导入异常都视为不可用）
    pyautogui = None  # type: ignore
    REAL_MOUSE_AVAILABLE = False
    logger.warning(f"真实鼠标引擎不可用（pyautogui 导入失败，将回退原逻辑）: {_e}")

try:
    import msvcrt
except ImportError:
    msvcrt = None  # type: ignore


# 物理光标全局唯一 → 串行执行。
# 串行由 real_mouse_scheduler（加权公平单槽位调度器）保证：多来源同时排队时按权重放行，
# 只有一方排队时该方独占。替代了原先的普通 threading.Lock（无优先级、盲抢）。

# 风控未放行的 URL 关键字
_PUNISH = ("punish", "x5step=2", "action=captcha", "pureCaptcha", "/captcha")
_MAX_REPLAY_DURATION_MS = 2600.0
_BUSINESS_SEGMENT_GAP_MS = 500.0
_PREFERRED_BUSINESS_TRAIL = "human_trail_pass_1783943859.json"
# Existing business samples were collected on the standard 258px NC slider.
# New samples can override this value with a top-level slider_distance field.
_LEGACY_BUSINESS_CAPTURE_DISTANCE_PX = 258.0
# Live replay validation showed that the captured 36-78px tails are stable,
# while samples with tails of 83px or more consistently reduced pass rate.
_MAX_BUSINESS_CAPTURE_OVERSHOOT_PX = 80.0
# 真人鼠标模式专用固定目录：本地与远程请求共用，用于复用和精确识别 Chrome 进程。
_REAL_MOUSE_BROWSER_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "browser_data", "real_mouse_shared")
)
_REAL_MOUSE_BROWSER_LOCK = os.path.join(_REAL_MOUSE_BROWSER_DIR, "browser.lock")


class _TimedDrag(list):
    """拖动点列表，并保留采集按下段的原点与松手时间。"""

    def __init__(
        self,
        points=(),
        press_delay_ms: float = 0.0,
        release_delay_ms: float = 0.0,
        origin_x: Optional[float] = None,
        origin_y: Optional[float] = None,
        pressed_at: Optional[float] = None,
        approach=(),
        approach_to_press_ms: float = 0.0,
        capture_distance_px: Optional[float] = None,
        source_file: str = "",
    ):
        super().__init__(points)
        self.press_delay_ms = max(0.0, float(press_delay_ms))
        self.release_delay_ms = max(0.0, float(release_delay_ms))
        self.origin_x = origin_x
        self.origin_y = origin_y
        self.pressed_at = pressed_at
        self.approach = list(approach)
        self.approach_to_press_ms = max(0.0, float(approach_to_press_ms))
        try:
            parsed_capture_distance = float(capture_distance_px)
        except (TypeError, ValueError):
            parsed_capture_distance = 0.0
        self.capture_distance_px = parsed_capture_distance if parsed_capture_distance > 0 else None
        self.source_file = str(source_file or "")

# 仅隐藏 webdriver，绝不伪造与真实 Chrome 冲突的指纹（UA/WebGL 交给真实 Chrome）
_STEALTH_MINIMAL = """
try { Object.defineProperty(navigator, 'webdriver', { get: () => undefined, configurable: true }); } catch (e) {}
try { delete Object.getPrototypeOf(navigator).webdriver; } catch (e) {}
try { delete window.__playwright; delete window.__pw_manual; delete window.__PW_inspect; } catch (e) {}
"""

# 注入到每个 frame：捕获鼠标事件，用于「主视口坐标 -> 屏幕坐标」校准
_CAP_JS = r"""
(() => {
  if (window.__cal) return;
  window.__cal = [];
  document.addEventListener('mousemove', e => {
    window.__cal.push([e.clientX, e.clientY, e.screenX, e.screenY, e.timeStamp, e.buttons]);
  }, true);
})();
"""

_BROWSER_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-popup-blocking",
    "--force-color-profile=srgb",
    "--lang=zh-CN",
    "--start-maximized",       # 窗口默认最大化（配合 no_viewport 生效）
]


def _trails_dir() -> str:
    """真人轨迹样本目录（与本文件同级 human_trails/）。"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "human_trails")


def _detect_scene(url: str) -> str:
    """按验证链接 URL 判滑块场景：登录滑块 vs 业务滑块。

    登录滑块出现在 passport 登录接口 punish（/newlogin/login.do/_____tmd_____/punish），
    其滑条更宽、需登录专用长位移轨迹并强制最大化窗口；其余（token/业务刷新）为 business。
    业务滑块 URL 不含 /newlogin/login.do，故不会误判。
    """
    return "login" if "/newlogin/login.do" in (url or "") else "business"


def _extract_business_drag(trail: list) -> list:
    """切分业务轨迹中的多次按下操作，保留完整按住时序。"""
    segments: List[_TimedDrag] = []
    current: list = []
    pressed_at: Optional[float] = None
    origin_x: Optional[float] = None
    origin_y: Optional[float] = None
    pending_approach: list = []
    active_approach: list = []

    def finish(released_at: Optional[float] = None) -> None:
        nonlocal current, pressed_at, origin_x, origin_y, active_approach
        if not current:
            return
        first_at = float(current[0][3])
        last_at = float(current[-1][3])
        press_delay_ms = first_at - pressed_at if pressed_at is not None else 0.0
        release_delay_ms = released_at - last_at if released_at is not None else 0.0
        segments.append(
            _TimedDrag(
                current,
                press_delay_ms=press_delay_ms,
                release_delay_ms=release_delay_ms,
                origin_x=origin_x,
                origin_y=origin_y,
                pressed_at=pressed_at,
                approach=active_approach,
            )
        )
        current = []
        pressed_at = None
        origin_x = None
        origin_y = None
        active_approach = []

    for event in trail:
        if not isinstance(event, list) or len(event) < 5:
            continue
        event_type = event[0]
        if event_type in ("mousedown", "pointerdown") and event[4] == 1:
            if current:
                finish()
            if pressed_at is None:
                pressed_at = float(event[3])
                origin_x = float(event[1])
                origin_y = float(event[2])
                active_approach = list(pending_approach)
            continue
        if event_type in ("mousemove", "pointermove") and event[4] == 1:
            if current and event[3] - current[-1][3] > _BUSINESS_SEGMENT_GAP_MS:
                finish()
                pressed_at = float(event[3])
                origin_x = float(event[1])
                origin_y = float(event[2])
            current.append(event)
            continue
        if event_type in ("mouseup", "pointerup"):
            finish(float(event[3]))
            pressed_at = None
            pending_approach = []
            continue
        if current and event_type in ("mousemove", "pointermove"):
            finish(float(event[3]))
        if event_type in ("mousemove", "pointermove") and event[4] == 0:
            pending_approach.append(event)
    if current:
        finish()

    forward = [segment for segment in segments if segment[-1][1] - segment[0][1] > 5]
    return max(forward, key=lambda segment: segment[-1][1] - segment[0][1], default=[])


def _load_drags(scene: str = "business") -> List[List[Tuple[float, float, float]]]:
    """加载真人通过轨迹，提取「按下拖动段」为相对位移序列 [(dx, dy, dt_ms), ...]。

    Args:
        scene: "business"（默认，业务/Token 刷新滑块，样本 human_trail_pass_*.json）
               或 "login"（登录滑块，样本 human_trail_login_*.json，长位移）
    """
    pattern = "human_trail_login_*.json" if scene == "login" else "human_trail_pass_*.json"
    files = sorted(glob.glob(os.path.join(_trails_dir(), pattern)))
    preferred: Optional[str] = None
    if scene == "business":
        preferred_path = os.path.join(_trails_dir(), _PREFERRED_BUSINESS_TRAIL)
        if os.path.isfile(preferred_path):
            preferred = preferred_path
            files = [preferred] + [f for f in files if f != preferred]
        else:
            logger.warning(
                f"业务优选真人轨迹不存在，回退全部业务样本: {_PREFERRED_BUSINESS_TRAIL}"
            )
    drags: List[List[Tuple[float, float, float]]] = []
    preferred_drag: Optional[List[Tuple[float, float, float]]] = None
    rejected_count = 0
    excessive_overshoot_count = 0
    for f in files:
        try:
            with open(f, encoding="utf-8") as trail_file:
                data = json.load(trail_file)
            if scene == "login":
                if data.get("passed") is False:
                    logger.warning(f"跳过未通过的真人轨迹样本: {f}")
                    continue
                trail = data.get("trail", [])
            else:
                if data.get("passed") is False:
                    rejected_count += 1
                    continue
                if data.get("slide_code") == 300:
                    rejected_count += 1
                    continue
                trail = data.get("trail", [])
        except Exception as e:
            logger.warning(f"加载真人轨迹失败 {f}: {e}")
            continue
        if scene == "business":
            seg = _extract_business_drag(trail)
        else:
            # 登录滑块保持原有提取方式，不改变登录专用长轨迹行为。
            moves = [e for e in trail if isinstance(e, list) and len(e) >= 5 and e[0] == "mousemove"]
            seg = [e for e in moves if len(e) >= 5 and e[4] == 1]
        if len(seg) < 5:
            continue
        if scene == "business" and getattr(seg, "pressed_at", None) is not None:
            x0 = seg.origin_x
            y0 = seg.origin_y
            prev = seg[0][3]
        else:
            x0, y0, prev = seg[0][1], seg[0][2], seg[0][3]
        raw_duration_ms = max(0.0, seg[-1][3] - seg[0][3])
        press_delay_ms = getattr(seg, "press_delay_ms", 0.0)
        release_delay_ms = getattr(seg, "release_delay_ms", 0.0)
        raw_approach = getattr(seg, "approach", []) if scene == "business" else []
        approach: List[Tuple[float, float, float]] = []
        if raw_approach:
            approach_prev = raw_approach[0][3]
            for p in raw_approach:
                approach.append(
                    (
                        p[1] - x0,
                        p[2] - y0,
                        max(0.0, p[3] - approach_prev),
                    )
                )
                approach_prev = p[3]
        approach_to_press_ms = (
            max(0.0, seg.pressed_at - raw_approach[-1][3])
            if raw_approach and getattr(seg, "pressed_at", None) is not None
            else 0.0
        )
        gesture_duration_ms = press_delay_ms + raw_duration_ms + release_delay_ms
        if scene == "business" and gesture_duration_ms > _MAX_REPLAY_DURATION_MS:
            continue
        rel: List[Tuple[float, float, float]] = []
        for p in seg:
            dt = max(0.0, p[3] - prev)
            rel.append((p[1] - x0, p[2] - y0, dt))
            prev = p[3]
        if scene == "business":
            duration_ms = sum(point[2] for point in rel)
            distance = rel[-1][0]
            if len(rel) < 20 or duration_ms < 350 or duration_ms > _MAX_REPLAY_DURATION_MS:
                continue
            if distance < 120 or distance > 1200:
                continue
            try:
                capture_distance_px = float(
                    data.get("slider_distance")
                    or _LEGACY_BUSINESS_CAPTURE_DISTANCE_PX
                )
            except (TypeError, ValueError):
                capture_distance_px = _LEGACY_BUSINESS_CAPTURE_DISTANCE_PX
            capture_overshoot_px = distance - capture_distance_px
            if capture_overshoot_px > _MAX_BUSINESS_CAPTURE_OVERSHOOT_PX:
                excessive_overshoot_count += 1
                continue
        else:
            capture_distance_px = None
        replay_drag = _TimedDrag(
            rel,
            press_delay_ms=press_delay_ms if scene == "business" else 0.0,
            release_delay_ms=release_delay_ms if scene == "business" else 0.0,
            origin_x=x0 if scene == "business" else None,
            origin_y=y0 if scene == "business" else None,
            pressed_at=getattr(seg, "pressed_at", None) if scene == "business" else None,
            approach=approach,
            approach_to_press_ms=approach_to_press_ms,
            capture_distance_px=capture_distance_px,
            source_file=os.path.basename(f),
        )
        drags.append(replay_drag)
        if preferred and f == preferred:
            preferred_drag = replay_drag
    if scene == "business":
        logger.debug(
            f"业务真人轨迹池: 可用={len(drags)}, "
            f"未通过或code=300={rejected_count}, "
            f"超出>{_MAX_BUSINESS_CAPTURE_OVERSHOOT_PX:.0f}px={excessive_overshoot_count}"
        )
    if scene == "business" and preferred:
        if preferred_drag is not None:
            return [preferred_drag] + [drag for drag in drags if drag is not preferred_drag]
        logger.warning(
            f"业务优选真人轨迹无效，回退其他业务样本: {_PREFERRED_BUSINESS_TRAIL}"
        )
    return drags


def _human_mouse_to(tx: int, ty: int, dur: float) -> None:
    """pyautogui 贝塞尔平滑移动物理光标到目标点（拟人接近）。"""
    x0, y0 = pyautogui.position()
    cx = x0 + (tx - x0) * random.uniform(0.2, 0.4) + random.uniform(-30, 30)
    cy = y0 + (ty - y0) * random.uniform(0.2, 0.4) + random.uniform(-30, 30)
    n = max(10, int(dur / 0.012))
    for i in range(1, n + 1):
        t = i / n
        mt = 1 - t
        x = mt * mt * x0 + 2 * mt * t * cx + t * t * tx
        y = mt * mt * y0 + 2 * mt * t * cy + t * t * ty
        pyautogui.moveTo(int(x), int(y))
        time.sleep(dur / n * random.uniform(0.6, 1.4))


def _choose_drag(drags: List[List[Tuple[float, float, float]]]) -> List[Tuple[float, float, float]]:
    """加权随机选择轨迹：仍然随机，但降低过短、过快样本被选中的概率。"""
    weights: List[float] = []
    for drag in drags:
        points = len(drag)
        duration_ms = sum(point[2] for point in drag)
        if points < 25 or duration_ms < 800:
            weights.append(0.25)
            continue
        weights.append(1.0 + min(points, 80) / 25.0 + min(duration_ms, 1800) / 900.0)
    return random.choices(drags, weights=weights, k=1)[0]


def _take_drag(
    remaining_drags: List[List[Tuple[float, float, float]]],
) -> List[Tuple[float, float, float]]:
    """Choose and remove one sample so retries do not repeat it."""
    selected_drag = _choose_drag(remaining_drags)
    for index, candidate in enumerate(remaining_drags):
        if candidate is selected_drag:
            remaining_drags.pop(index)
            break
    return selected_drag


def _scale_drag_to_distance(
    drag: List[Tuple[float, float, float]],
    distance: float,
) -> List[Tuple[float, float, float]]:
    """按采集滑轨基准映射 X 位移，保留真人到底后的原始超出段。"""
    if not drag or distance <= 0:
        return drag
    capture_distance = getattr(drag, "capture_distance_px", None)
    if capture_distance is None or capture_distance <= 0:
        capture_distance = _LEGACY_BUSINESS_CAPTURE_DISTANCE_PX
    factor = distance / capture_distance
    points = [(dx * factor, dy, dt) for dx, dy, dt in drag]
    return _TimedDrag(
        points,
        press_delay_ms=getattr(drag, "press_delay_ms", 0.0),
        release_delay_ms=getattr(drag, "release_delay_ms", 0.0),
        origin_x=getattr(drag, "origin_x", None),
        origin_y=getattr(drag, "origin_y", None),
        pressed_at=getattr(drag, "pressed_at", None),
        approach=getattr(drag, "approach", []),
        approach_to_press_ms=getattr(drag, "approach_to_press_ms", 0.0),
        capture_distance_px=capture_distance,
        source_file=getattr(drag, "source_file", ""),
    )


class _RealMouseSolver:
    """可复用真实鼠标滑块求解器（固定浏览器目录、自然指纹）。"""

    def __init__(self, user_id: str):
        self.user_id = str(user_id)
        self.pure_id = self.user_id.split("_")[0] if "_" in self.user_id else self.user_id
        self.pw = None
        self.context = None
        self.page = None
        self.browser_dir = _REAL_MOUSE_BROWSER_DIR
        os.makedirs(self.browser_dir, exist_ok=True)
        self._browser_lock_file = None
        self._slide_code: Optional[int] = None
        self._timed_out = False
        self._window_handle: Optional[int] = None

    # ---------- 浏览器 ----------
    def update_user(self, user_id: str) -> None:
        """更新当前任务日志标识，不改变共享浏览器实例。"""
        self.user_id = str(user_id)
        self.pure_id = self.user_id.split("_")[0] if "_" in self.user_id else self.user_id

    def init_browser(self) -> None:
        self._acquire_browser_lock()
        # 当前进程没有可用上下文时，先清理固定目录对应的孤儿 Chrome。
        self._kill_browser_processes(log_result=False)
        try:
            self.pw = sync_playwright().start()
            self.context = self.pw.chromium.launch_persistent_context(
                self.browser_dir,
                channel="chrome",          # 用本机真实 Chrome（自然指纹），非自带 Chromium
                headless=False,            # 真实鼠标必须有可见窗口
                args=_BROWSER_ARGS,
                no_viewport=True,          # 不强制 viewport，保留真实窗口尺寸
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
                ignore_https_errors=True,
                extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
                timeout=30000,
            )
        except Exception:
            self._release_browser_lock()
            raise
        self.context.add_init_script(_STEALTH_MINIMAL)
        self.context.add_init_script(_CAP_JS)

        def _on_resp(resp):
            try:
                if "/slide" in resp.url and "_____tmd_____" in resp.url:
                    v = resp.json().get("result", {}).get("code")
                    if v is not None:
                        self._slide_code = v
            except Exception:
                pass

        self.context.on("response", _on_resp)
        pages = list(self.context.pages)
        self.page = pages[0] if pages else self.context.new_page()
        for extra_page in pages[1:]:
            try:
                extra_page.close()
            except Exception:
                pass
        self.page.bring_to_front()

    def _acquire_browser_lock(self) -> None:
        """跨进程独占固定浏览器目录，防止多个服务进程同时启动真人鼠标 Chrome。"""
        if self._browser_lock_file is not None:
            return
        if sys.platform != "win32" or msvcrt is None:
            return
        lock_file = open(_REAL_MOUSE_BROWSER_LOCK, "a+b")
        try:
            lock_file.seek(0, os.SEEK_END)
            if lock_file.tell() == 0:
                lock_file.write(b"0")
                lock_file.flush()
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as e:
            lock_file.close()
            raise RuntimeError("真人鼠标共享浏览器已被另一个服务进程占用") from e
        self._browser_lock_file = lock_file

    def _release_browser_lock(self) -> None:
        """释放真人鼠标固定浏览器目录的跨进程锁。"""
        lock_file = self._browser_lock_file
        self._browser_lock_file = None
        if lock_file is None:
            return
        try:
            lock_file.seek(0)
            if sys.platform == "win32" and msvcrt is not None:
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        try:
            lock_file.close()
        except Exception:
            pass

    def ensure_browser(self) -> None:
        """确认共享 Chrome/Context/Page 可用，失效时自动完整重启。"""
        context_ok = False
        try:
            if self.context is not None:
                _ = self.context.pages
                context_ok = True
        except Exception:
            context_ok = False
        if context_ok:
            try:
                if self.page is None or self.page.is_closed():
                    self.page = self.context.new_page()
                for extra_page in list(self.context.pages):
                    if extra_page is not self.page:
                        extra_page.close()
                self.page.evaluate("() => 1")
                return
            except Exception:
                pass
        self.close()
        self.init_browser()

    def prepare_task(self, user_id: str, url: str) -> None:
        """复用浏览器前清理上一任务状态，防止本地/远程或账号之间串 Cookie。"""
        self.update_user(user_id)
        self._slide_code = None
        self._timed_out = False
        self._window_handle = None
        last_error: Optional[Exception] = None
        for attempt in range(2):
            try:
                self.ensure_browser()
                self._prepare_clean_page(url)
                return
            except Exception as e:
                last_error = e
                if attempt == 0:
                    logger.warning(
                        f"【{self.pure_id}】共享浏览器状态清理失败，将重启后重试: {e}"
                    )
                self.close()
        raise RuntimeError(f"共享浏览器重启后仍无法清理任务状态: {last_error}") from last_error

    def _prepare_clean_page(self, url: str) -> None:
        """在当前共享 Context 中创建唯一干净页面，并确认无历史 Cookie。"""
        new_page = self.context.new_page()
        for old_page in list(self.context.pages):
            if old_page is not new_page:
                old_page.close()
        self.page = new_page
        # 先关闭旧页面，避免尾部响应在首次清理后重新写入 Cookie。
        self.context.clear_cookies()
        remaining = self.context.cookies()
        if remaining:
            raise RuntimeError(f"关闭旧页面后仍残留 {len(remaining)} 个 Cookie")
        self._clear_browser_storage(url)
        # 存储清理后再次清 Cookie 并校验，任何残留都触发浏览器重启。
        self.context.clear_cookies()
        remaining = self.context.cookies()
        if remaining:
            raise RuntimeError(f"二次清理后仍残留 {len(remaining)} 个 Cookie")
        if len(self.context.pages) != 1:
            raise RuntimeError(f"共享浏览器页面数量异常: {len(self.context.pages)}")
        self.page.bring_to_front()

    def _clear_browser_storage(self, url: str) -> None:
        """清理缓存及闲鱼相关 Origin 存储，避免固定 Context 残留上一次任务状态。"""
        origins = {
            "https://h5api.m.goofish.com",
            "https://passport.goofish.com",
            "https://www.goofish.com",
            "https://m.goofish.com",
        }
        parsed = urlsplit(url or "")
        if parsed.scheme and parsed.netloc:
            origins.add(f"{parsed.scheme}://{parsed.netloc}")
        try:
            session = self.context.new_cdp_session(self.page)
            session.send("Network.clearBrowserCache")
            for origin in origins:
                session.send(
                    "Storage.clearDataForOrigin",
                    {"origin": origin, "storageTypes": "all"},
                )
        except Exception as e:
            raise RuntimeError(f"清理共享浏览器站点存储失败: {e}") from e

    def close(self) -> None:
        for fn in (
            lambda: self.page and self.page.close(),
            lambda: self.context and self.context.close(),
            lambda: self.pw and self.pw.stop(),
        ):
            try:
                fn()
            except Exception:
                pass
        self.page = None
        self.context = None
        self.pw = None
        self._release_browser_lock()

    def force_kill(self) -> None:
        """看门狗超时回调：按真人鼠标固定目录精确强杀对应 Chrome 进程。

        仅匹配命令行包含真人鼠标固定目录的进程，绝不误伤用户自己的 Chrome。
        强杀后，solve()/close() 中阻塞的 Playwright 调用会立即抛错返回，
        从而保证 run_real_mouse_verification 一定返回、上层风控日志不再卡在“处理中”。
        """
        self._timed_out = True
        self._kill_browser_processes(log_result=True)

    def _kill_browser_processes(self, log_result: bool) -> None:
        """按固定目录清理真人鼠标 Chrome 主进程和子进程。"""
        if sys.platform != "win32":
            return
        try:
            browser_dir = self.browser_dir
            ps = (
                "Get-CimInstance Win32_Process | "
                f"Where-Object {{ $_.Name -eq 'chrome.exe' -and $_.CommandLine -like '*{browser_dir}*' }} | "
                "ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } catch {} }"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                capture_output=True, timeout=15,
            )
            if log_result:
                logger.warning(f"【{self.pure_id}】真实鼠标引擎超时，已强杀共享浏览器进程")
        except Exception as e:
            if log_result:
                logger.warning(f"【{self.pure_id}】真实鼠标引擎强杀共享浏览器失败（可忽略）: {e}")

    # ---------- 工具 ----------
    def _cookies(self) -> Dict[str, str]:
        try:
            return {c["name"]: c["value"] for c in self.context.cookies()}
        except Exception:
            return {}

    def _x5sec(self) -> str:
        return self._cookies().get("x5sec", "")

    def _in_punish(self) -> bool:
        try:
            u = self.page.url or ""
        except Exception:
            u = ""
        return any(k in u for k in _PUNISH)

    def _find_slider(self):
        for frame in self.page.frames:
            try:
                btn = frame.query_selector("#nc_1_n1z")
                if btn and btn.is_visible():
                    track = frame.query_selector("#nc_1_n1t") or frame.query_selector(".nc_scale")
                    if track:
                        return frame, btn, track
            except Exception:
                continue
        return None, None, None

    def _x5_cookies(self) -> Dict[str, str]:
        """提取 x5* 相关 cookie（成功后返回给上层）。"""
        out: Dict[str, str] = {}
        for name, value in self._cookies().items():
            low = name.lower()
            if low.startswith("x5") or "x5sec" in low:
                out[name] = value
        return out

    # ---------- 核心 ----------
    def _maximize_window(self) -> None:
        """通过 CDP 强制最大化窗口（登录滑块必须最大化才能用长位移轨迹通过）。"""
        try:
            session = self.context.new_cdp_session(self.page)
            win = session.send("Browser.getWindowForTarget")
            session.send(
                "Browser.setWindowBounds",
                {"windowId": win["windowId"], "bounds": {"windowState": "maximized"}},
            )
        except Exception as e:
            logger.warning(f"【{self.pure_id}】强制最大化窗口失败（继续）: {e}")

    def _ensure_window_foreground(self, scene: str) -> bool:
        """激活当前验证 Chrome，并校验物理输入的真实前台归属。"""
        scene_name = "登录滑块" if scene == "login" else "业务滑块"
        try:
            self.page.bring_to_front()
            if self._window_handle:
                success, detail = activate_window(self._window_handle)
                if success:
                    return True
            success, hwnd, detail = activate_page_window(self.page)
            if success and hwnd:
                first_detection = self._window_handle is None
                self._window_handle = hwnd
                if first_detection:
                    logger.info(
                        f"【{self.pure_id}】{scene_name}已锁定 Windows 前台窗口: {detail}"
                    )
                return True
            logger.error(
                f"【{self.pure_id}】{scene_name}无法激活 Windows 前台窗口，"
                f"已取消物理鼠标回放: {detail}"
            )
        except Exception as e:
            logger.error(
                f"【{self.pure_id}】{scene_name} Windows 前台校验异常，"
                f"已取消物理鼠标回放: {e}"
            )
        return False

    def solve(
        self,
        url: str,
        drags: List[List[Tuple[float, float, float]]],
        browser_timeout: int,
        url_provider: Optional[Callable[[], Optional[str]]],
        scene: str = "business",
    ) -> Tuple[bool, Optional[Dict[str, str]]]:
        start = time.time()
        self.ensure_browser()
        # 登录场景强制最大化（业务场景保持原有窗口行为不变）
        if scene == "login":
            self._maximize_window()
            self._ensure_window_foreground(scene)

        # 导航（命中过期页则用 url_provider 刷新一次）
        target = url
        for attempt in range(2):
            try:
                self.page.goto(target, wait_until="domcontentloaded", timeout=15000)
            except Exception as e:
                logger.warning(f"【{self.pure_id}】真实鼠标引擎导航异常（继续）: {e}")
            time.sleep(random.uniform(1.2, 1.8))
            if scene == "login":
                self._maximize_window()
                self._ensure_window_foreground(scene)
            try:
                content = self.page.content()
            except Exception:
                content = ""
            if "抱歉，页面访问出现了问题" in content:
                if url_provider and attempt == 0:
                    try:
                        fresh = url_provider()
                    except Exception:
                        fresh = None
                    # 风控已解除、无需滑块：交由上层 _refetch_token_ok 流程处理
                    if fresh == CAPTCHA_NOT_REQUIRED:
                        logger.info(f"【{self.pure_id}】重取链接时检测到 token 已可用，无需滑块，提前结束")
                        return True, None
                    if fresh and isinstance(fresh, str):
                        target = fresh
                        logger.info(f"【{self.pure_id}】真实鼠标引擎使用刷新后的验证链接重试")
                        continue
                # 链接已过期且无法自助重取：返回过期哨兵，供编排层/远程调用方刷新URL重试
                return False, URL_EXPIRED
            break

        # 多次尝试：失败则点“重试”按钮重置滑块，再用物理鼠标滑（同页重试，最多 3 次）
        pre_x5 = self._x5sec()
        max_attempts = 3
        remaining_drags = list(drags) if scene == "business" else []
        for attempt in range(1, max_attempts + 1):
            if time.time() - start > browser_timeout:
                break

            # 定位滑块
            frame = btn = track = None
            for _ in range(12):
                if time.time() - start > browser_timeout:
                    break
                frame, btn, track = self._find_slider()
                if btn and track:
                    break
                time.sleep(0.4)
            if not btn or not track:
                # 滑块消失：可能已通过（被前一次滑动放行）
                if not self._in_punish() and self._x5sec() and self._x5sec() != pre_x5:
                    cookies = self._collect_success()
                    if cookies:
                        return True, cookies
                logger.warning(f"【{self.pure_id}】真实鼠标引擎未找到滑块（第{attempt}次尝试）")
                break

            # SendInput/pyautogui 都是系统级输入，必须确认本次 Chrome 是 Windows 真实前台窗口。
            if scene == "login":
                self._maximize_window()
            if not self._ensure_window_foreground(scene):
                return False, None

            # 计算坐标 + 物理鼠标回放真人轨迹（每次随机挑一条轨迹，降低重复模式风险）
            if scene == "business":
                if not remaining_drags:
                    remaining_drags = list(drags)
                selected_drag = _take_drag(remaining_drags)
            else:
                # Keep the existing login retry selection behavior unchanged.
                selected_drag = _choose_drag(drags)
            if scene == "login":
                logger.info(
                    f"【{self.pure_id}】登录滑块回放真人原始样本: "
                    f"点数={len(selected_drag) - 1}, "
                    f"位移={selected_drag[-1][0]:.0f}px, "
                    f"按下至末点={sum(point[2] for point in selected_drag):.0f}ms, "
                    f"首点等待={selected_drag[1][2]:.0f}ms"
                )
            else:
                move_duration_ms = sum(point[2] for point in selected_drag)
                press_delay_ms = getattr(selected_drag, "press_delay_ms", 0.0)
                release_delay_ms = getattr(selected_drag, "release_delay_ms", 0.0)
                approach = getattr(selected_drag, "approach", [])
                source_file = getattr(selected_drag, "source_file", "") or "unknown"
                logger.info(
                    f"【{self.pure_id}】业务滑块第{attempt}次选用真人原始轨迹: "
                    f"样本={source_file}, "
                    f"接近点={len(approach)}, 拖动点={len(selected_drag)}, "
                    f"位移={selected_drag[-1][0]:.0f}px, "
                    f"移动={move_duration_ms:.0f}ms, "
                    f"按下等待={press_delay_ms:.0f}ms, "
                    f"松手等待={release_delay_ms:.0f}ms, "
                    f"总按住={press_delay_ms + move_duration_ms + release_delay_ms:.0f}ms"
                )
            if not self._do_real_slide(
                frame,
                btn,
                track,
                drag=selected_drag,
                scene=scene,
            ):
                break

            # 判定本次结果
            res = self._wait_result(pre_x5, start, browser_timeout)
            if res is True:
                cookies = self._collect_success()
                if scene == "login" and cookies:
                    logger.info(f"【{self.pure_id}】登录滑块第{attempt}次回放通过")
                # 仅当真正拿到 x5sec 才算成功；否则按失败返回
                # （是否回退原引擎由编排层根据系统设置决定，本引擎只负责返回结果）
                return (True, cookies) if cookies else (False, None)

            # 本次未过：业务远程调用优先重新获取新鲜 URL，避免在已被风控拒绝的旧页面上
            # 连续重复轨迹；login 或没有 URL 刷新能力时，保持原页面点击重试逻辑。
            if attempt < max_attempts and (time.time() - start) < (browser_timeout - 5):
                logger.info(f"【{self.pure_id}】真实鼠标引擎第{attempt}次未通过，准备刷新或重试")
                refreshed = False
                if scene == "business" and url_provider is not None:
                    try:
                        fresh = url_provider()
                    except Exception as refresh_error:
                        logger.warning(f"【{self.pure_id}】失败后刷新验证链接异常，沿用当前页面: {refresh_error}")
                        fresh = None
                    if fresh == CAPTCHA_NOT_REQUIRED:
                        logger.info(f"【{self.pure_id}】失败后刷新 token 已可用，无需继续滑块")
                        return True, None
                    if isinstance(fresh, str) and fresh:
                        try:
                            self.page.goto(fresh, wait_until="domcontentloaded", timeout=15000)
                            time.sleep(random.uniform(1.2, 1.8))
                            if "抱歉，页面访问出现了问题" not in self.page.content():
                                refreshed = True
                                logger.info(f"【{self.pure_id}】失败后已切换到新鲜验证链接重试")
                        except Exception as refresh_error:
                            logger.warning(f"【{self.pure_id}】失败后导航新验证链接异常，沿用当前页面: {refresh_error}")
                if not refreshed:
                    self._click_retry()
                time.sleep(random.uniform(1.0, 1.8))
                continue
            break
        return False, None

    def _do_real_slide(
        self,
        frame,
        btn,
        track,
        drag: List[Tuple[float, float, float]],
        scene: str = "business",
    ) -> bool:
        """对当前滑块做一次：坐标校准 + 物理鼠标接近/按下/回放真人轨迹/松手。返回是否完成滑动。"""
        box = btn.bounding_box()
        if not box:
            return False
        mx = box["x"] + box["width"] / 2
        my = box["y"] + box["height"] / 2
        replay_drag = drag
        if scene == "business":
            distance = compute_slider_distance(frame, btn, track)
            if distance <= 0:
                logger.error(f"【{self.pure_id}】业务滑块无法计算当前滑轨距离")
                return False
            replay_drag = _scale_drag_to_distance(drag, distance)
            overshoot = replay_drag[-1][0] - distance
            logger.info(
                f"【{self.pure_id}】业务滑块按采集滑轨基准映射真人轨迹: "
                f"采集末点={drag[-1][0]:.1f}px, 当前到底={distance:.1f}px, "
                f"末点=({replay_drag[-1][0]:.1f},{replay_drag[-1][1]:.1f})px, "
                f"到底后继续={overshoot:.1f}px, "
                f"点数={len(replay_drag)}"
            )
        else:
            track_box = track.bounding_box() if track else None
            if track_box:
                candidate_x = track_box["x"] + track_box["width"] - 1 - drag[-1][0]
                if box["x"] <= candidate_x <= box["x"] + box["width"]:
                    mx = candidate_x
        if scene == "business":
            mapper, geometry = build_geometry_mapper(self.page)
            logger.info(
                f"【{self.pure_id}】业务滑块使用被动窗口几何映射: "
                f"dpr={geometry.get('devicePixelRatio')}, "
                f"窗口=({geometry.get('screenX')},{geometry.get('screenY')}), "
                f"视口={geometry.get('innerWidth')}x{geometry.get('innerHeight')}"
            )
            to_screen = mapper.to_screen
        else:
            # 登录滑块保持原 CDP 校准逻辑，不改变 login 的滑动行为。
            dpr = self.page.evaluate("() => window.devicePixelRatio") or 1.0
            try:
                frame.evaluate("() => { window.__cal = []; }")
            except Exception:
                pass
            self.page.mouse.move(mx, my, steps=3)
            time.sleep(0.2)
            cal = []
            try:
                cal = frame.evaluate("() => window.__cal || []") or self.page.evaluate("() => window.__cal || []")
            except Exception:
                pass
            if not cal:
                logger.warning(f"【{self.pure_id}】真实鼠标引擎坐标校准失败")
                return False
            c = cal[-1]
            off_x, off_y = c[2] - mx, c[3] - my

            def to_screen(vx: float, vy: float) -> Tuple[int, int]:
                return int(round((vx + off_x) * dpr)), int(round((vy + off_y) * dpr))

        self._slide_code = None  # 每次滑动前重置，避免读到上一次的返回码

        # 坐标校准后再次校验，避免校准期间被其他程序抢走 Windows 前台窗口。
        if not self._ensure_window_foreground(scene):
            return False

        sx, sy = to_screen(mx, my)
        if scene == "login":
            logger.info(f"【{self.pure_id}】登录滑块使用业务同款 pyautogui 回放: 起点=({sx},{sy})")
        if scene == "business":
            # 业务滑块保留采集样本的未按下接近段及完整按住时序。
            timer_resolution(True)
            try:
                approach = getattr(replay_drag, "approach", [])
                if approach:
                    first_x, first_y, _ = approach[0]
                    first_sx, first_sy = to_screen(mx + first_x, my + first_y)
                    send_move_abs(first_sx, first_sy)
                    approach_started = time.perf_counter()
                    approach_elapsed = 0.0
                    for dx, dy, dt in approach[1:]:
                        approach_elapsed += dt / 1000.0
                        if dt >= 3.0:
                            precise_sleep(approach_started + approach_elapsed)
                        tx, ty = to_screen(mx + dx, my + dy)
                        send_move_abs(tx, ty)
                    precise_sleep(
                        approach_started
                        + approach_elapsed
                        + getattr(replay_drag, "approach_to_press_ms", 0.0) / 1000.0
                    )
                else:
                    send_move_abs(sx, sy)
                send_button(True)
                started = time.perf_counter()
                press_delay = getattr(replay_drag, "press_delay_ms", 0.0) / 1000.0
                release_delay = getattr(replay_drag, "release_delay_ms", 0.0) / 1000.0
                precise_sleep(started + press_delay)
                move_started = started + press_delay
                elapsed = 0.0
                for dx, dy, dt in replay_drag:
                    elapsed += dt / 1000.0
                    if dt >= 3.0:
                        precise_sleep(move_started + elapsed)
                    tx, ty = to_screen(mx + dx, my + dy)
                    send_move_abs(tx, ty)
                precise_sleep(move_started + elapsed + release_delay)
            finally:
                send_button(False)
                timer_resolution(False)
        else:
            # 登录滑块保持原有 pyautogui 轨迹、坐标抖动和逐点时序，不受业务优化影响。
            ax, ay = to_screen(mx - 50, my - 40)
            _human_mouse_to(ax, ay, 0.3)
            _human_mouse_to(sx, sy, 0.2)
            time.sleep(0.15)
            pyautogui.mouseDown()
            time.sleep(0.12)
            for i, (dx, dy, dt) in enumerate(drag):
                if i == 0:
                    continue
                tx, ty = to_screen(
                    mx + dx + random.uniform(-1, 1),
                    my + dy + random.uniform(-1, 1),
                )
                pyautogui.moveTo(tx, ty)
                time.sleep(max(0.0, (dt / 1000.0) * random.uniform(0.85, 1.15)))
            time.sleep(0.08)
            pyautogui.mouseUp()
        if scene == "login":
            try:
                observed = frame.evaluate("() => window.__cal || []") or []
                pressed = [event for event in observed if len(event) >= 6 and event[5] == 1]
                pressed_duration = (
                    pressed[-1][4] - pressed[0][4] if len(pressed) >= 2 else 0
                )
                actual_start = pressed[0][2:4] if pressed else []
                actual_end = pressed[-1][2:4] if pressed else []
                actual_distance = (
                    pressed[-1][2] - pressed[0][2] if len(pressed) >= 2 else 0
                )
                logger.info(
                    f"【{self.pure_id}】登录滑块页面接收鼠标移动事件: "
                    f"总计={len(observed)}个, 按下={len(pressed)}个, "
                    f"按下时长={pressed_duration:.0f}ms, 起点={mx:.0f}, "
                    f"目标={mx + drag[-1][0]:.0f}, 实际首点={actual_start}, "
                    f"实际末点={actual_end}, 实际位移={actual_distance:.0f}px"
                )
            except Exception:
                # 成功后页面可能立即跳转并销毁 frame，无需作为异常处理。
                pass
        return True

    def _wait_result(self, pre_x5: str, start: float, browser_timeout: int) -> Optional[bool]:
        """等待并判定本次滑动结果：True=通过 / False=明确失败(code 300) / None=不明确（可重试）。"""
        def _nc_ok() -> bool:
            for fr in self.page.frames:
                try:
                    if fr.evaluate("()=>!!(document.querySelector('.nc_ok_icon')||document.querySelector('.btn_ok'))"):
                        return True
                except Exception:
                    pass
            return False

        deadline = min(8.0, max(3.0, browser_timeout - (time.time() - start)))
        waited = 0.0
        while waited < deadline:
            time.sleep(0.5)
            waited += 0.5
            if self._slide_code == 300:
                return False
            if self._slide_code == 0:
                return True
            if self._x5sec() and self._x5sec() != pre_x5:
                return True
            if not self._in_punish():
                return True
            if _nc_ok():
                return True
        return None

    def _click_retry(self) -> None:
        """点击滑块失败后的“点击框体重试”按钮，重置滑块（与老引擎一致的选择器）。"""
        selectors = (
            "#nc_1_refresh1",
            ".nc_iconfont.btn_refresh",
            ".errloading",
            "[class*='refresh']",
            ".nc-container",
        )
        for fr in self.page.frames:
            for sel in selectors:
                try:
                    el = fr.query_selector(sel)
                    if el and el.is_visible():
                        el.click()
                        logger.info(f"【{self.pure_id}】真实鼠标引擎已点击重试按钮: {sel}")
                        return
                except Exception:
                    continue

    def _collect_success(self) -> Optional[Dict[str, str]]:
        """成功后等待 set-cookie 落盘并返回 x5* cookies。"""
        time.sleep(1.0)
        x5 = self._x5_cookies()
        if "x5sec" not in x5:
            # 视觉通过但未真正下发 x5sec，按未通过处理（与项目主引擎一致）
            logger.warning(f"【{self.pure_id}】真实鼠标引擎视觉通过但未获取到 x5sec")
            return None
        return x5


_shared_solver: Optional[_RealMouseSolver] = None
_real_mouse_executor: Optional[ThreadPoolExecutor] = None
_real_mouse_executor_lock = threading.Lock()


def _get_real_mouse_executor() -> ThreadPoolExecutor:
    """返回真人鼠标专用单线程执行器，保证 Playwright Sync 对象始终在同一线程使用。"""
    global _real_mouse_executor
    if _real_mouse_executor is None:
        with _real_mouse_executor_lock:
            if _real_mouse_executor is None:
                _real_mouse_executor = ThreadPoolExecutor(
                    max_workers=1,
                    thread_name_prefix="real-mouse",
                )
    return _real_mouse_executor


def _get_shared_solver(user_id: str) -> _RealMouseSolver:
    """获取真人鼠标进程级共享浏览器实例。"""
    global _shared_solver
    if _shared_solver is None:
        _shared_solver = _RealMouseSolver(user_id)
    else:
        _shared_solver.update_user(user_id)
    return _shared_solver


def _close_shared_solver_in_worker() -> None:
    """在真人鼠标专用线程中关闭共享浏览器。"""
    global _shared_solver
    if _shared_solver is None:
        return
    try:
        _shared_solver.close()
    except Exception:
        pass
    _shared_solver = None


def _shutdown_real_mouse_executor() -> None:
    """服务退出时在 Playwright 所属线程关闭浏览器，再停止专用执行器。"""
    global _real_mouse_executor
    executor = _real_mouse_executor
    if executor is None:
        return
    try:
        executor.submit(_close_shared_solver_in_worker).result(timeout=15)
    except Exception:
        pass
    try:
        executor.shutdown(wait=False, cancel_futures=True)
    except Exception:
        pass
    _real_mouse_executor = None


try:
    # ThreadPoolExecutor 会在线程级退出阶段先于普通 atexit 关闭；这里后注册、先执行，
    # 确保 Playwright 仍可在所属 real-mouse 线程中正常 close，避免 Node 管道 EPIPE。
    threading._register_atexit(_shutdown_real_mouse_executor)
except AttributeError:
    atexit.register(_shutdown_real_mouse_executor)


def _execute_shared_verification(
    user_id: str,
    url: str,
    drags: List[List[Tuple[float, float, float]]],
    browser_timeout: int,
    url_provider: Optional[Callable[[], Optional[str]]],
    scene: str,
) -> Tuple[bool, Optional[Dict[str, str]]]:
    """在真人鼠标专用线程内完成浏览器准备、滑动和结果收集。"""
    solver = _get_shared_solver(user_id)
    budget = max(browser_timeout, 40) + 20
    watchdog = threading.Timer(budget, solver.force_kill)
    watchdog.daemon = True
    watchdog.start()
    try:
        solver.prepare_task(user_id, url)
        return solver.solve(
            url, drags, browser_timeout, url_provider, scene=scene
        )
    finally:
        watchdog.cancel()


def run_real_mouse_verification(
    user_id: str,
    url: str,
    existing_cookies_str: str = "",
    browser_timeout: int = 60,
    url_provider: Optional[Callable[[], Optional[str]]] = None,
    weight_class: str = "local",
) -> Tuple[bool, Optional[Dict[str, str]]]:
    """真实鼠标滑块验证入口（串行执行，物理光标唯一）。

    Args:
        weight_class: 排队来源类别（"local"=本地Token刷新 / "remote"=远程无cookie /
            "remote_cookie"=远程有cookie）。本地与远程按权重公平放行；远程内部默认无cookie优先，等待满70秒后按最早入队优先。

    Returns:
        (是否成功, x5* cookies 字典 | None)
    """
    if not REAL_MOUSE_AVAILABLE:
        return False, None

    # 按 URL 自动判场景：登录滑块用登录轨迹并强制最大化；业务滑块保持原有行为
    scene = _detect_scene(url)
    drags = _load_drags(scene)
    if not drags:
        sample = "human_trail_login_*.json" if scene == "login" else "human_trail_pass_*.json"
        logger.error(f"真实鼠标引擎缺少真人轨迹样本（human_trails/{sample}，scene={scene}）")
        return False, None

    # 加权公平排队：阻塞直到轮到本来源（无限等待，与旧 with lock 语义一致）
    if not real_mouse_scheduler.acquire(weight_class):
        logger.warning(f"【{user_id}】真实鼠标引擎排队获取执行权失败")
        return False, None
    try:
        try:
            future = _get_real_mouse_executor().submit(
                _execute_shared_verification,
                user_id,
                url,
                drags,
                browser_timeout,
                url_provider,
                scene,
            )
            return future.result()
        except Exception as e:
            logger.error(f"【{user_id}】真实鼠标引擎执行异常: {e}")
            return False, None
    finally:
        real_mouse_scheduler.release()
