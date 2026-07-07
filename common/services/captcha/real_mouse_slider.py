"""
真实鼠标滑块求解引擎（可选，开关：环境变量 CAPTCHA_REAL_MOUSE=true）

为什么需要它：
- 闲鱼/阿里 baxia 风控能区分「CDP 注入的鼠标事件」与「真实硬件鼠标事件」。
  实测：Playwright(CDP) 即使回放真人轨迹也被判 code=300（拒），而用 pyautogui 驱动
  物理光标回放同一条真人轨迹则 code=0（通过）。
- 因此本引擎用 pyautogui（Windows SendInput）驱动**物理光标**，回放预先录制的真人滑动
  轨迹，完成 NC 滑块验证。

代价与限制：
- 运行期间会**接管桌面物理光标约 2~3 秒**，期间人不能同时用鼠标；
- 仅适用于**有图形桌面的 Windows**；无头 Linux / Docker 无法驱动物理鼠标，
  故依赖以「惰性导入」方式加载，导入失败时 REAL_MOUSE_AVAILABLE=False，上层自动回退原逻辑；
- 物理光标全局唯一，故本引擎以全局锁串行执行（同一时刻只解一个滑块）。

对外入口：run_real_mouse_verification(...) -> (是否成功, x5* cookies | None)
返回契约与 run_slider_verification 一致，便于编排层无缝切换。
"""
from __future__ import annotations

import glob
import json
import os
import random
import shutil
import subprocess
import sys
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

from loguru import logger

from common.services.captcha.slider_stealth import URL_EXPIRED, CAPTCHA_NOT_REQUIRED
from common.services.captcha.weighted_scheduler import real_mouse_scheduler

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


# 物理光标全局唯一 → 串行执行。
# 串行由 real_mouse_scheduler（加权公平单槽位调度器）保证：多来源同时排队时按权重放行，
# 只有一方排队时该方独占。替代了原先的普通 threading.Lock（无优先级、盲抢）。

# 风控未放行的 URL 关键字
_PUNISH = ("punish", "x5step=2", "action=captcha", "pureCaptcha", "/captcha")

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
  document.addEventListener('mousemove', e => { window.__cal.push([e.clientX, e.clientY, e.screenX, e.screenY]); }, true);
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


def _load_drags() -> List[List[Tuple[float, float, float]]]:
    """加载所有真人通过轨迹，提取「按下拖动段」为相对位移序列 [(dx, dy, dt_ms), ...]。"""
    drags: List[List[Tuple[float, float, float]]] = []
    for f in sorted(glob.glob(os.path.join(_trails_dir(), "human_trail_pass_*.json"))):
        try:
            trail = json.load(open(f, encoding="utf-8")).get("trail", [])
        except Exception as e:
            logger.warning(f"加载真人轨迹失败 {f}: {e}")
            continue
        moves = [e for e in trail if e[0] == "mousemove"]
        seg = [e for e in moves if len(e) >= 5 and e[4] == 1]  # buttons==1 拖动中
        if len(seg) < 5:
            continue
        x0, y0, prev = seg[0][1], seg[0][2], seg[0][3]
        rel: List[Tuple[float, float, float]] = []
        for p in seg:
            rel.append((p[1] - x0, p[2] - y0, p[3] - prev))
            prev = p[3]
        drags.append(rel)
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


class _RealMouseSolver:
    """单次真实鼠标滑块求解（自建浏览器、自然指纹）。"""

    def __init__(self, user_id: str):
        self.user_id = str(user_id)
        self.pure_id = self.user_id.split("_")[0] if "_" in self.user_id else self.user_id
        self.pw = None
        self.context = None
        self.page = None
        # 一次性 profile 目录（每次唯一并在 close 时删除），彻底规避同账号复用导致的 PROFILE_IN_USE
        self.user_data_dir = os.path.join(
            os.getcwd(), "browser_data", f"realmouse_{self.pure_id}_{int(time.time() * 1000)}"
        )
        os.makedirs(self.user_data_dir, exist_ok=True)
        self._slide_code: Optional[int] = None
        self._timed_out = False

    # ---------- 浏览器 ----------
    def init_browser(self) -> None:
        self.pw = sync_playwright().start()
        self.context = self.pw.chromium.launch_persistent_context(
            self.user_data_dir,
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
        self.page = self.context.new_page()

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
        # 删除一次性 profile 目录
        try:
            shutil.rmtree(self.user_data_dir, ignore_errors=True)
        except Exception:
            pass

    def force_kill(self) -> None:
        """看门狗超时回调：按本次唯一 user_data_dir 精确强杀对应 Chrome 进程。

        仅匹配命令行包含本次 user_data_dir 的进程，绝不误伤用户自己的 Chrome。
        强杀后，solve()/close() 中阻塞的 Playwright 调用会立即抛错返回，
        从而保证 run_real_mouse_verification 一定返回、上层风控日志不再卡在“处理中”。
        """
        self._timed_out = True
        if sys.platform != "win32":
            return
        try:
            udir = self.user_data_dir
            ps = (
                "Get-CimInstance Win32_Process | "
                f"Where-Object {{ $_.CommandLine -like '*{udir}*' }} | "
                "ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } catch {} }"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                capture_output=True, timeout=15,
            )
            logger.warning(f"【{self.pure_id}】真实鼠标引擎超时，已强杀本次浏览器进程")
        except Exception as e:
            logger.warning(f"【{self.pure_id}】真实鼠标引擎强杀浏览器失败（可忽略）: {e}")

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
    def solve(self, url: str, drags: List[List[Tuple[float, float, float]]],
              browser_timeout: int, url_provider: Optional[Callable[[], Optional[str]]]) -> Tuple[bool, Optional[Dict[str, str]]]:
        start = time.time()
        self.init_browser()

        # 导航（命中过期页则用 url_provider 刷新一次）
        target = url
        for attempt in range(2):
            try:
                self.page.goto(target, wait_until="domcontentloaded", timeout=15000)
            except Exception as e:
                logger.warning(f"【{self.pure_id}】真实鼠标引擎导航异常（继续）: {e}")
            time.sleep(random.uniform(1.2, 1.8))
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

            # 计算坐标 + 物理鼠标回放真人轨迹（每次随机挑一条轨迹，降低重复模式风险）
            if not self._do_real_slide(frame, btn, drag=random.choice(drags)):
                break

            # 判定本次结果
            res = self._wait_result(pre_x5, start, browser_timeout)
            if res is True:
                cookies = self._collect_success()
                # 仅当真正拿到 x5sec 才算成功；否则按失败返回
                # （是否回退原引擎由编排层根据 CAPTCHA_REAL_MOUSE 决定，本引擎只负责返回结果）
                return (True, cookies) if cookies else (False, None)

            # 本次未过：若还有重试机会且时间充足，点“重试”按钮重置滑块后再滑
            if attempt < max_attempts and (time.time() - start) < (browser_timeout - 5):
                logger.info(f"【{self.pure_id}】真实鼠标引擎第{attempt}次未通过，点击重试后再滑")
                self._click_retry()
                time.sleep(random.uniform(1.0, 1.8))
                continue
            break
        return False, None

    def _do_real_slide(self, frame, btn, drag: List[Tuple[float, float, float]]) -> bool:
        """对当前滑块做一次：坐标校准 + 物理鼠标接近/按下/回放真人轨迹/松手。返回是否完成滑动。"""
        box = btn.bounding_box()
        if not box:
            return False
        mx = box["x"] + box["width"] / 2
        my = box["y"] + box["height"] / 2
        dpr = self.page.evaluate("() => window.devicePixelRatio") or 1.0

        # 校准：主视口坐标 -> 屏幕坐标 的平移量
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

        # 物理鼠标接近 + 按下 + 回放真人轨迹 + 松手
        ax, ay = to_screen(mx - 50, my - 40)
        _human_mouse_to(ax, ay, 0.3)
        sx, sy = to_screen(mx, my)
        _human_mouse_to(sx, sy, 0.2)
        time.sleep(0.15)
        pyautogui.mouseDown()
        time.sleep(0.12)
        for i, (dx, dy, dt) in enumerate(drag):
            if i == 0:
                continue
            tx, ty = to_screen(mx + dx + random.uniform(-1, 1), my + dy + random.uniform(-1, 1))
            pyautogui.moveTo(tx, ty)
            time.sleep(max(0.0, (dt / 1000.0) * random.uniform(0.85, 1.15)))
        time.sleep(0.08)
        pyautogui.mouseUp()
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
            "remote_cookie"=远程有cookie）。本地与远程按权重公平放行；远程内部无cookie 严格优先于有cookie。

    Returns:
        (是否成功, x5* cookies 字典 | None)
    """
    if not REAL_MOUSE_AVAILABLE:
        return False, None

    drags = _load_drags()
    if not drags:
        logger.error("真实鼠标引擎缺少真人轨迹样本（human_trails/human_trail_pass_*.json）")
        return False, None

    # 加权公平排队：阻塞直到轮到本来源（无限等待，与旧 with lock 语义一致）
    if not real_mouse_scheduler.acquire(weight_class):
        logger.warning(f"【{user_id}】真实鼠标引擎排队获取执行权失败")
        return False, None
    try:
        solver = _RealMouseSolver(user_id)
        # 看门狗：总预算内若 solve()/close() 卡死，强杀浏览器解除阻塞，
        # 保证本函数一定返回（否则上层风控日志会一直停留在“处理中”，且执行权被长期占用）。
        budget = max(browser_timeout, 40) + 20
        watchdog = threading.Timer(budget, solver.force_kill)
        watchdog.daemon = True
        watchdog.start()
        ok: bool = False
        cookies: Optional[Dict[str, str]] = None
        try:
            ok, cookies = solver.solve(url, drags, browser_timeout, url_provider)
        except Exception as e:
            logger.error(f"【{user_id}】真实鼠标引擎执行异常: {e}")
            ok, cookies = False, None
        finally:
            try:
                solver.close()
            except Exception:
                pass
            watchdog.cancel()
        return ok, cookies
    finally:
        real_mouse_scheduler.release()
