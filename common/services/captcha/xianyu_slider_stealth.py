"""
闲鱼滑块验证服务 - 扩展版

在 PlaywrightSliderService 基础上扩展，添加密码登录功能
"""
from __future__ import annotations

import os
import time
import random
from typing import Any, Callable, Dict, Optional, Tuple
from loguru import logger

from common.services.captcha.slider_stealth import PlaywrightSliderService
from common.utils.time_utils import get_beijing_now_naive

try:
    from playwright.sync_api import sync_playwright, Page
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    Page = Any
    logger.warning("Playwright 未安装")


class LoginPageErrorException(Exception):
    """登录页面提示错误异常。

    专门用于表示登录页面 `class="login-error-msg"` 元素中检测到的错误，
    比如"账密错误"、"账号已被冻结"、"操作过于频繁"等。

    与普通 Exception 区分开，使外层调用方（如 cookie_token_manager / internal.py）
    能够拿到原始错误文案并据此设置冷却期或做兜底处理。
    内层 ``login_with_password_playwright`` 在 except 中会让该异常透传，
    其它异常仍然被吞掉并 return None。
    """
    pass


class BaxiaPunishCaptchaException(Exception):
    """检测到 baxia-punish 风控图形滑块验证（如"找出两个松鼠"）。

    特征：
    - iframe#baxia-dialog-content 容器
    - 内部 #baxia-punish.baxia-punish 元素
    - canvas#captcha-question 图形识别画布
    - 文案"请按照说明进行验证哦"、"拖动滑块出现完整的两个松鼠后就行"等

    与"账密错误"等账号自身问题不同，此为闲鱼风控系统识别出可疑行为后弹出
    的图形识别验证，**无法被脚本自动通过**。

    外层处理策略（与 LoginPageErrorException 不同）：
    - **不禁用账号**（账号本身正常）
    - **设置 5 小时冷却**（避免反复触发风控）
    - 发送 ``baxia_punish_captcha`` 类型通知，提示用户稍后重试或手动登录

    内层 ``login_with_password_playwright`` 与 ``_wait_for_face_verification``
    在 except 中均会让该异常透传，其它异常仍然按原逻辑处理。
    """
    pass


class XianyuSliderStealth(PlaywrightSliderService):
    """闲鱼滑块验证服务 - 扩展版
    
    继承 PlaywrightSliderService，添加密码登录功能
    """
    
    def __init__(self, user_id: str = "default", enable_learning: bool = True, headless: bool = True):
        """初始化
        
        Args:
            user_id: 用户ID
            enable_learning: 是否启用轨迹学习
            headless: 是否无头模式
        """
        super().__init__(user_id, enable_learning, headless)
    
    def login_with_password_playwright(
        self, 
        account: str, 
        password: str, 
        show_browser: bool = False, 
        notification_callback: Optional[Callable] = None
    ) -> Optional[Dict[str, str]]:
        """使用Playwright进行密码登录
        
        Args:
            account: 登录账号（必填）
            password: 登录密码（必填）
            show_browser: 是否显示浏览器窗口（默认False为无头模式）
            notification_callback: 可选的通知回调函数，用于发送二维码/人脸验证通知
        
        Returns:
            dict: Cookie字典，失败返回None
        """
        if not PLAYWRIGHT_AVAILABLE:
            logger.error(f"【{self.pure_user_id}】Playwright 未安装")
            return None
        
        # 验证必需参数
        if not account or not password:
            logger.error(f"【{self.pure_user_id}】账号或密码不能为空")
            return None
        
        browser_mode = "有头" if show_browser else "无头"
        logger.info(f"【{self.pure_user_id}】开始{browser_mode}模式密码登录流程（使用Playwright）...")
        logger.info(f"【{self.pure_user_id}】账号: {account}")
        logger.info("=" * 60)
        
        # 设置headless模式
        # Docker环境下强制无头模式（容器内无显示器，有头模式会报错）
        if show_browser and os.environ.get("BROWSER_HEADLESS", "").lower() == "true":
            logger.info(f"【{self.pure_user_id}】检测到BROWSER_HEADLESS=true，忽略show_browser，强制使用无头模式")
            self.headless = True
        else:
            self.headless = not show_browser
        
        try:
            # 初始化浏览器（密码登录不需要反检测脚本，参照旧框架）
            self.init_browser(add_stealth_script=False)
            
            # 访问登录页面
            login_url = "https://www.goofish.com/im"
            logger.info(f"【{self.pure_user_id}】访问登录页面: {login_url}")
            self.page.goto(login_url, wait_until='domcontentloaded', timeout=30000)
            
            # 等待页面加载
            wait_time = 2
            logger.info(f"【{self.pure_user_id}】等待页面加载（{wait_time}秒）...")
            time.sleep(wait_time)
            
            # 页面诊断信息
            logger.info(f"【{self.pure_user_id}】========== 页面诊断信息 ==========")
            logger.info(f"【{self.pure_user_id}】当前URL: {self.page.url}")
            logger.info(f"【{self.pure_user_id}】页面标题: {self.page.title()}")
            logger.info(f"【{self.pure_user_id}】=====================================")
            
            # ====== 优先检查是否有[快速进入]按钮（cookies注入后可能直接可用） ======
            logger.info(f"【{self.pure_user_id}】检查是否有[快速进入]按钮...")
            quick_enter_clicked = self._find_and_click_quick_enter_button()
            if quick_enter_clicked:
                logger.info(f"【{self.pure_user_id}】已点击[快速进入]按钮，等待5秒让界面自动刷新后获取Cookie...")
                time.sleep(5)
                cookies = self._get_cookies()
                if cookies and cookies.get("unb"):
                    logger.success(f"【{self.pure_user_id}】✅ 点击[快速进入]后成功获取到有效Cookie（含unb）")
                    return cookies
                else:
                    logger.info(f"【{self.pure_user_id}】点击[快速进入]后未获取到有效Cookie，继续执行密码登录流程...")
                    # 重新访问登录页面（点击快速进入后页面可能已变化）
                    logger.info(f"【{self.pure_user_id}】重新访问登录页面: {login_url}")
                    self.page.goto(login_url, wait_until='domcontentloaded', timeout=30000)
                    time.sleep(2)
            else:
                logger.info(f"【{self.pure_user_id}】未找到[快速进入]按钮，继续执行密码登录流程...")
            
            # 查找登录frame
            logger.info(f"【{self.pure_user_id}】查找登录frame...")
            login_frame = self._find_login_frame()
            
            if not login_frame:
                # 【情况2】未找到登录表单 → 可能已登录，检查登录状态（参照旧框架）
                logger.warning(f"【{self.pure_user_id}】未找到任何iframe，检查是否已登录...")
                
                # 等待一下让页面完全加载（参照旧框架）
                time.sleep(2)
                
                # 检测滑块验证
                if self._detect_and_handle_slider():
                    logger.info(f"【{self.pure_user_id}】滑块检测/处理完成")
                
                # 等待页面加载
                time.sleep(3)
                
                # 检查登录状态
                if self._check_login_success():
                    logger.success(f"【{self.pure_user_id}】✅ 检测到已登录状态，直接获取Cookie")
                    return self._get_cookies()
                else:
                    logger.error(f"【{self.pure_user_id}】❌ 未找到登录表单且未登录")
                    return None
            
            # 点击密码登录标签
            logger.info(f"【{self.pure_user_id}】查找密码登录标签...")
            try:
                password_tab = login_frame.query_selector('a.password-login-tab-item')
                if password_tab:
                    logger.info(f"【{self.pure_user_id}】✓ 找到密码登录标签，点击中...")
                    password_tab.click()
                    time.sleep(1.5)
            except Exception as e:
                logger.warning(f"【{self.pure_user_id}】查找密码登录标签失败: {e}")
            
            # 输入账号
            logger.info(f"【{self.pure_user_id}】输入账号: {account}")
            time.sleep(1)
            
            account_input = login_frame.query_selector('#fm-login-id')
            if account_input:
                logger.info(f"【{self.pure_user_id}】✓ 找到账号输入框")
                account_input.fill(account)
                logger.info(f"【{self.pure_user_id}】✓ 账号已输入")
                time.sleep(random.uniform(0.5, 1.0))
            else:
                logger.error(f"【{self.pure_user_id}】✗ 未找到账号输入框")
                return None
            
            # 输入密码
            logger.info(f"【{self.pure_user_id}】输入密码...")
            password_input = login_frame.query_selector('#fm-login-password')
            if password_input:
                password_input.fill(password)
                logger.info(f"【{self.pure_user_id}】✓ 密码已输入")
                time.sleep(random.uniform(0.5, 1.0))
            else:
                logger.error(f"【{self.pure_user_id}】✗ 未找到密码输入框")
                return None
            
            # 勾选用户协议
            logger.info(f"【{self.pure_user_id}】查找并勾选用户协议...")
            try:
                agreement_checkbox = login_frame.query_selector('#fm-agreement-checkbox')
                if agreement_checkbox:
                    is_checked = agreement_checkbox.evaluate('el => el.checked')
                    if not is_checked:
                        agreement_checkbox.click()
                        time.sleep(0.3)
                        logger.info(f"【{self.pure_user_id}】✓ 用户协议已勾选")
            except Exception as e:
                logger.warning(f"【{self.pure_user_id}】勾选用户协议失败: {e}")
            
            # 点击登录按钮
            logger.info(f"【{self.pure_user_id}】点击登录按钮...")
            time.sleep(1)
            
            login_button = login_frame.query_selector('button.password-login')
            if login_button:
                logger.info(f"【{self.pure_user_id}】✓ 找到登录按钮")
                login_button.click()
                logger.info(f"【{self.pure_user_id}】✓ 登录按钮已点击")
            else:
                logger.error(f"【{self.pure_user_id}】✗ 未找到登录按钮")
                return None
            
            # 等待页面响应
            logger.info(f"【{self.pure_user_id}】========== 登录后监控 ==========")
            logger.info(f"【{self.pure_user_id}】等待页面响应...")
            time.sleep(3)
            
            # 检测并处理滑块验证
            if self._detect_and_handle_slider():
                logger.success(f"【{self.pure_user_id}】✅ 滑块验证成功！")
            
            # 等待登录完成（参照旧框架，等待5秒）
            logger.info(f"【{self.pure_user_id}】等待登录完成...")
            time.sleep(5)
            
            # 再次检查是否有滑块验证（可能在等待过程中出现）
            logger.info(f"【{self.pure_user_id}】等待1秒后检查是否有滑块验证...")
            time.sleep(1)
            if self._detect_and_handle_slider():
                logger.success(f"【{self.pure_user_id}】✅ 等待后滑块验证成功！")
                time.sleep(3)
            
            # 检查登录状态
            logger.info(f"【{self.pure_user_id}】等待1秒后检查登录状态...")
            time.sleep(1)
            login_success = self._check_login_success()
            
            if login_success:
                logger.success(f"【{self.pure_user_id}】✅ 登录验证成功！")
                return self._get_cookies()
            else:
                # 优先检测 baxia-punish 风控图形滑块（不是账号问题，仅设冷却不禁用）
                # 必须先于 _check_login_error，因 punish 弹窗与登录错误是两类不同场景
                has_punish, punish_msg = self._check_baxia_punish_captcha()
                if has_punish:
                    logger.warning(
                        f"【{self.pure_user_id}】⚠️ 触发风控图形滑块验证，账号本身正常，仅设置冷却（不禁用）：{punish_msg}"
                    )
                    raise BaxiaPunishCaptchaException(punish_msg)
                
                # 检查是否有登录错误（class="login-error-msg"），可能是账密错误、账号冻结、风控等
                logger.info(f"【{self.pure_user_id}】等待1秒后检查是否有登录错误...")
                time.sleep(1)
                has_error, error_message = self._check_login_error()
                if has_error:
                    logger.error(f"【{self.pure_user_id}】❌ 登录失败：{error_message}")
                    # 直接以页面原始错误文案作为禁用原因，避免文不对题
                    disable_reason = error_message if error_message else "登录失败"
                    self._disable_account_on_timeout(disable_reason)
                    # 抛出特定异常，使外层 except 分支能够区分"登录页错误"与其它异常，
                    # 进而正确设置 5 小时冷却期等兜底逻辑
                    raise LoginPageErrorException(
                        error_message if error_message else "登录失败，请检查账号密码是否正确"
                    )
                
                # 【重要】检测是否需要二维码/人脸验证（排除滑块验证）
                # 注意：_detect_qr_code_verification 如果检测到滑块，会立即处理滑块
                logger.info(f"【{self.pure_user_id}】等待1秒后检测是否需要二维码/人脸验证...")
                time.sleep(1)
                logger.info(f"【{self.pure_user_id}】检测是否需要二维码/人脸验证...")
                has_qr, qr_frame = self._detect_qr_code_verification()
                
                # 如果检测到滑块并已处理，再次检查登录状态（参照旧框架）
                if not has_qr:
                    # 滑块可能已被处理，再次检查登录状态
                    logger.info(f"【{self.pure_user_id}】等待1秒后再次检查登录状态...")
                    time.sleep(1)
                    login_success_after_slider = self._check_login_success()
                    if login_success_after_slider:
                        logger.success(f"【{self.pure_user_id}】✅ 滑块验证后，登录验证成功！")
                        return self._get_cookies()
                    else:
                        # 滑块验证后仍未登录成功，继续检测二维码/人脸验证（此时应该不会再检测到滑块）
                        logger.info(f"【{self.pure_user_id}】等待1秒后继续检测是否需要二维码/人脸验证...")
                        time.sleep(1)
                        logger.info(f"【{self.pure_user_id}】滑块验证后，继续检测是否需要二维码/人脸验证...")
                        has_qr, qr_frame = self._detect_qr_code_verification()
                
                if has_qr:
                    logger.warning(f"【{self.pure_user_id}】⚠️ 检测到二维码/人脸验证")
                    
                    # 获取验证链接URL和截图路径
                    frame_url = None
                    screenshot_path = None
                    if qr_frame:
                        try:
                            # 检查是否有验证链接（从VerificationFrame对象）
                            if hasattr(qr_frame, 'verify_url') and qr_frame.verify_url:
                                frame_url = qr_frame.verify_url
                                logger.info(f"【{self.pure_user_id}】使用获取到的人脸验证链接: {frame_url}")
                            else:
                                frame_url = qr_frame.url if hasattr(qr_frame, 'url') else None
                            
                            # 检查是否有截图路径（从VerificationFrame对象）
                            if hasattr(qr_frame, 'screenshot_path') and qr_frame.screenshot_path:
                                screenshot_path = qr_frame.screenshot_path
                                logger.info(f"【{self.pure_user_id}】使用获取到的人脸验证截图: {screenshot_path}")
                        except Exception as e:
                            logger.warning(f"【{self.pure_user_id}】获取frame信息失败: {e}")
                    
                    # 发送通知
                    if notification_callback:
                        self._send_face_verification_notification(notification_callback, screenshot_path, frame_url)
                    
                    # 等待用户完成人脸验证
                    if self._wait_for_face_verification():
                        logger.success(f"【{self.pure_user_id}】✅ 人脸验证完成，登录成功！")
                        return self._get_cookies()
                    else:
                        # 人脸验证超时，禁用账号
                        logger.warning(f"【{self.pure_user_id}】❌ 人脸验证超时，禁用账号")
                        self._disable_account_on_timeout("人脸验证超时")
                        return None
                else:
                    logger.error(f"【{self.pure_user_id}】❌ 登录失败，原因未知")
                    return None
        
        except BaxiaPunishCaptchaException:
            # baxia-punish 风控图形滑块（账号本身正常）需要透传，
            # 由外层调用方仅设置冷却期、不禁用账号、发送特定通知。
            raise
        except LoginPageErrorException:
            # 登录页错误（账密错误、账号冻结、风控等）需要让外层调用方拿到具体错误文案，
            # 因此让该异常透传，不在此处吞掉。账号禁用与通知发送已在 raise 之前完成。
            raise
        except Exception as e:
            logger.error(f"【{self.pure_user_id}】密码登录异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
        
        finally:
            self.close()
    
    def _find_and_click_quick_enter_button(self) -> bool:
        """查找并点击[快速进入]按钮

        在主页面和所有iframe中查找"快速进入"按钮，找到则点击。
        该按钮通常出现在登录iframe中，表示cookies仍有效可以快速登录。

        Returns:
            是否找到并成功点击了[快速进入]按钮
        """
        # 策略1：在主页面直接查找
        if self._try_click_quick_enter_in_page(self.page, "主页面"):
            return True

        # 策略2：在所有iframe中查找
        try:
            iframes = self.page.query_selector_all("iframe")
            logger.info(f"【{self.pure_user_id}】找到 {len(iframes)} 个iframe，逐一检查[快速进入]按钮...")

            for idx, iframe in enumerate(iframes):
                try:
                    frame = iframe.content_frame()
                    if not frame:
                        continue

                    # 等待iframe内容加载
                    try:
                        frame.wait_for_load_state("domcontentloaded", timeout=5000)
                    except Exception:
                        pass

                    if self._try_click_quick_enter_in_page(frame, f"iframe[{idx}]"):
                        return True
                except Exception as exc:
                    logger.info(f"【{self.pure_user_id}】检查iframe[{idx}]时出错: {exc}")
                    continue
        except Exception as exc:
            logger.warning(f"【{self.pure_user_id}】查找iframe时出错: {exc}")

        return False

    def _try_click_quick_enter_in_page(self, frame, frame_name: str) -> bool:
        """在指定frame中尝试查找并点击[快速进入]按钮

        Args:
            frame: 页面或frame对象
            frame_name: frame名称（用于日志）

        Returns:
            是否成功点击
        """
        target_text = "快速进入"

        # 选择器列表：按优先级排列
        selectors = [
            f'button:has-text("{target_text}")',
            f'button[type="submit"]:has-text("{target_text}")',
            f'.fm-button:has-text("{target_text}")',
            f'.fn-button:has-text("{target_text}")',
        ]

        for selector in selectors:
            try:
                element = frame.query_selector(selector)
                if element and element.is_visible():
                    logger.info(f"【{self.pure_user_id}】✓ 在{frame_name}找到[快速进入]按钮: {selector}")
                    element.click()
                    logger.info(f"【{self.pure_user_id}】✓ [快速进入]按钮已点击")
                    return True
            except Exception:
                continue

        # 兜底策略：通过文本内容匹配所有button
        try:
            buttons = frame.query_selector_all("button")
            for btn in buttons:
                try:
                    text = btn.text_content() or ""
                    if target_text in text.strip() and btn.is_visible():
                        logger.info(f"【{self.pure_user_id}】✓ 在{frame_name}通过文本匹配找到[快速进入]按钮")
                        btn.click()
                        logger.info(f"【{self.pure_user_id}】✓ [快速进入]按钮已点击")
                        return True
                except Exception:
                    continue
        except Exception:
            pass

        return False

    def _find_login_frame(self) -> Optional[Page]:
        """查找登录frame
        
        Returns:
            登录frame或主页面
        """
        # 等待页面和iframe加载完成
        time.sleep(1)
        
        # 先尝试在主页面查找登录表单
        main_page_selectors = [
            '#fm-login-id',
            'input[name="fm-login-id"]',
            'input[placeholder*="手机号"]',
            'input[placeholder*="邮箱"]',
        ]
        
        for selector in main_page_selectors:
            try:
                element = self.page.query_selector(selector)
                if element and element.is_visible():
                    logger.info(f"【{self.pure_user_id}】✓ 在主页面找到登录表单元素: {selector}")
                    return self.page
            except Exception:
                continue
        
        # 如果主页面没找到，在iframe中查找
        iframes = self.page.query_selector_all('iframe')
        logger.info(f"【{self.pure_user_id}】找到 {len(iframes)} 个 iframe")
        
        for idx, iframe in enumerate(iframes):
            try:
                frame = iframe.content_frame()
                if frame:
                    # 等待iframe内容加载
                    try:
                        frame.wait_for_selector('#fm-login-id', timeout=3000)
                    except Exception:
                        pass
                    
                    # 检查是否有登录表单
                    for selector in main_page_selectors:
                        try:
                            element = frame.query_selector(selector)
                            if element and element.is_visible():
                                logger.info(f"【{self.pure_user_id}】✓ 在Frame {idx} 找到登录表单: {selector}")
                                return frame
                        except Exception:
                            continue
            except Exception as e:
                logger.debug(f"【{self.pure_user_id}】检查Frame {idx}时出错: {e}")
                continue
        
        return None
    
    def _detect_and_handle_slider(self) -> bool:
        """检测并处理滑块验证
        
        Returns:
            是否成功处理滑块
        """
        slider_selectors = [
            '#nc_1_n1z',
            '.nc-container',
            '.nc_scale',
            '.nc-wrapper'
        ]
        
        has_slider = False
        for selector in slider_selectors:
            try:
                element = self.page.query_selector(selector)
                if element and element.is_visible():
                    logger.info(f"【{self.pure_user_id}】✅ 检测到滑块验证元素: {selector}")
                    has_slider = True
                    break
            except Exception:
                continue
        
        if has_slider:
            logger.warning(f"【{self.pure_user_id}】检测到滑块验证，开始处理...")
            slider_success = self.solve_slider(max_retries=3)
            
            if slider_success:
                logger.success(f"【{self.pure_user_id}】✅ 滑块验证成功！")
                return True
            else:
                logger.error(f"【{self.pure_user_id}】❌ 滑块验证失败")
                return False
        
        return True
    
    def _check_login_success(self) -> bool:
        """检查登录是否成功（参照旧框架）
        
        Returns:
            是否登录成功
        """
        try:
            # 使用旧框架的选择器
            selector = '.rc-virtual-list-holder-inner'
            logger.info(f"【{self.pure_user_id}】========== 检查登录状态（通过页面元素） ==========")
            logger.info(f"【{self.pure_user_id}】检查选择器: {selector}")
            
            element = self.page.query_selector(selector)
            
            if element:
                # 获取元素的子元素数量
                child_count = element.evaluate('el => el.children.length')
                
                logger.info(f"【{self.pure_user_id}】找到目标元素:")
                logger.info(f"【{self.pure_user_id}】  - 子元素数量: {child_count}")
                logger.info(f"【{self.pure_user_id}】  - 是否可见: {element.is_visible()}")
                
                # 判断是否有数据：子元素数量大于0
                if child_count > 0:
                    logger.success(f"【{self.pure_user_id}】✅ 登录成功！检测到列表有 {child_count} 个子元素")
                    return True
                else:
                    logger.debug(f"【{self.pure_user_id}】列表为空，登录未完成")
                    return False
            else:
                logger.debug(f"【{self.pure_user_id}】未找到目标元素: {selector}")
                return False
                
        except Exception as e:
            logger.debug(f"【{self.pure_user_id}】检查登录状态时出错: {e}")
            return False
    
    def _check_login_error(self) -> Tuple[bool, str]:
        """检查是否有登录错误。
        
        闲鱼登录表单可能位于主页面也可能位于 iframe（passport.goofish.com 弹窗形式
        或嵌入式登录），因此需要同时遍历主页面和所有子 frame。
        
        Returns:
            (是否有错误, 错误消息)
        """
        # 优先按精确 class 命中（适配阿里旧版 fm 表单和闲鱼新版 login-error-msg）
        error_selectors = [
            '.fm-error-msg',
            '.error-msg',
            '.login-error',
            '.login-error-msg',
        ]
        
        # 文案关键词兜底：当上述 class 未命中（例如页面改版）时，
        # 直接用 Playwright 的 text 选择器在页面文本中匹配常见错误文案。
        error_keywords = [
            '账密错误',
            '账号或密码错误',
            '账号错误',
            '密码错误',
            '密码不正确',
            '用户名或密码',
            '账号已被冻结',
            '账号被冻结',
            '账号被锁定',
            '操作过于频繁',
        ]
        
        # 同时遍历主页面与所有 iframe
        frames_to_check = [self.page] + list(self.page.frames)
        
        # 1) 按 class 精确匹配
        for frame in frames_to_check:
            for selector in error_selectors:
                try:
                    element = frame.query_selector(selector)
                    if element and element.is_visible():
                        error_text = (element.inner_text() or '').strip()
                        if error_text:
                            logger.info(
                                f"【{self.pure_user_id}】✓ 检测到错误消息(class={selector}): {error_text}"
                            )
                            return True, error_text
                except Exception:
                    continue
        
        # 2) 文本关键词兜底匹配
        for frame in frames_to_check:
            for keyword in error_keywords:
                try:
                    # Playwright 文本选择器：精确匹配（区分大小写按文本内容）
                    element = frame.query_selector(f'text="{keyword}"')
                    if element and element.is_visible():
                        error_text = (element.inner_text() or keyword).strip()
                        logger.info(
                            f"【{self.pure_user_id}】✓ 检测到错误消息(text={keyword}): {error_text}"
                        )
                        return True, error_text
                except Exception:
                    continue
        
        return False, ""
    
    def _check_baxia_punish_captcha(self) -> Tuple[bool, str]:
        """检测是否出现 baxia-punish 风控图形滑块验证。
        
        典型特征（来自闲鱼风控弹窗 DOM 结构）：
        - #baxia-punish.baxia-punish（"punish" 特有标志，普通 NC 滑块不会出现）
        - canvas#captcha-question（图形识别画布）
        - .scratch-captcha-container / .scratch-captcha-title（"scratch"=擦除/找图，图形特有）
        - 文案："请按照说明进行验证哦"、"拖动滑块出现完整的两个松鼠后就行"、"反爬码"
        
        因 punish 弹窗通常嵌套在 iframe 里，需要同时遍历主页面与所有子 frame。
        
        ⚠️ 已刻意不使用 `#baxia-dialog-content` / `.baxia-dialog-content`：
        这两个是 baxia 通用弹窗容器（普通 NC 滑块 `#nc_1_n1z` 也会装在里面），
        不够特异，会把普通滑块误判为 punish 而错设 5 小时冷却。
        
        Returns:
            (是否检测到, 描述文案)
        """
        # 选择器特征：只用 punish/scratch/captcha-question 特有标志，避免误判普通 NC 滑块
        punish_selectors = [
            '#baxia-punish',                # punish 特有
            '.baxia-punish',                # punish 特有
            'canvas#captcha-question',      # 图形识别画布
            '.scratch-captcha-container',   # 图形滑块容器
            '.scratch-captcha-title',       # 图形滑块标题
        ]
        
        # 文案特征（兜底）
        punish_keywords = [
            '请按照说明进行验证哦',
            '拖动滑块出现完整的两个松鼠后就行',
            '拖动滑块出现完整的两个松鼠',
        ]
        
        try:
            frames_to_check = [self.page] + list(self.page.frames)
        except Exception:
            return False, ""
        
        # 1) 按 selector 命中（特异性最高）
        for frame in frames_to_check:
            for selector in punish_selectors:
                try:
                    element = frame.query_selector(selector)
                    if element and element.is_visible():
                        logger.warning(
                            f"【{self.pure_user_id}】⚠️ 检测到风控图形滑块验证(selector={selector})"
                        )
                        return True, f"风控图形滑块验证(selector={selector})"
                except Exception:
                    continue
        
        # 2) 按文案兜底（应对页面 DOM 改版）
        for frame in frames_to_check:
            for keyword in punish_keywords:
                try:
                    element = frame.query_selector(f'text="{keyword}"')
                    if element and element.is_visible():
                        logger.warning(
                            f"【{self.pure_user_id}】⚠️ 检测到风控图形滑块验证(text={keyword})"
                        )
                        return True, f"风控图形滑块验证：{keyword}"
                except Exception:
                    continue
        
        return False, ""
    
    def _detect_qr_code_verification(self) -> tuple:
        """检测是否存在二维码/人脸验证（排除滑块验证）- 参照旧框架
        
        Returns:
            tuple: (has_qr, qr_frame) - 是否有二维码/人脸验证，验证frame
                   (False, None) - 如果检测到滑块验证，会先处理滑块，然后返回
        """
        try:
            logger.info(f"【{self.pure_user_id}】检测二维码/人脸验证...")
            
            # 先检查是否是滑块验证，如果是滑块验证，立即处理并返回
            slider_selectors = [
                '#nc_1_n1z',
                '.nc-container',
                '.nc_scale',
                '.nc-wrapper',
                '.nc_iconfont',
                '[class*="nc_"]'
            ]
            
            # 在主页面和所有frame中检查滑块
            frames_to_check = [self.page] + list(self.page.frames)
            for frame in frames_to_check:
                try:
                    for selector in slider_selectors:
                        try:
                            element = frame.query_selector(selector)
                            if element and element.is_visible():
                                logger.info(f"【{self.pure_user_id}】检测到滑块验证元素，立即处理滑块: {selector}")
                                # 检测到滑块验证，立即处理
                                logger.warning(f"【{self.pure_user_id}】检测到滑块验证，开始自动处理...")
                                slider_success = self.solve_slider(max_retries=3)
                                if slider_success:
                                    logger.success(f"【{self.pure_user_id}】✅ 滑块验证成功！")
                                    time.sleep(3)  # 等待滑块验证后的状态更新
                                else:
                                    # 3次失败后，刷新页面重试
                                    logger.warning(f"【{self.pure_user_id}】⚠️ 滑块处理3次都失败，刷新页面后重试...")
                                    try:
                                        self.page.reload(wait_until="domcontentloaded", timeout=30000)
                                        logger.info(f"【{self.pure_user_id}】✅ 页面刷新完成")
                                        time.sleep(2)
                                        slider_success = self.solve_slider(max_retries=3)
                                        if not slider_success:
                                            logger.error(f"【{self.pure_user_id}】❌ 刷新后滑块验证仍然失败")
                                        else:
                                            logger.success(f"【{self.pure_user_id}】✅ 刷新后滑块验证成功！")
                                            time.sleep(3)
                                    except Exception as e:
                                        logger.error(f"【{self.pure_user_id}】❌ 页面刷新失败: {e}")
                                
                                # 返回 False, None 表示不是二维码/人脸验证（已处理滑块）
                                return False, None
                        except Exception:
                            continue
                except Exception:
                    continue
            
            # 检测所有frames中的二维码/人脸验证
            # 首先检查是否有 alibaba-login-box iframe（人脸验证或短信验证）
            try:
                iframes = self.page.query_selector_all('iframe')
                for iframe in iframes:
                    try:
                        iframe_id = iframe.get_attribute('id')
                        if iframe_id == 'alibaba-login-box':
                            logger.info(f"【{self.pure_user_id}】✅ 检测到 alibaba-login-box iframe（人脸验证/短信验证）")
                            frame = iframe.content_frame()
                            if frame:
                                logger.info(f"【{self.pure_user_id}】人脸验证/短信验证Frame URL: {frame.url if hasattr(frame, 'url') else '未知'}")
                                
                                # 尝试自动点击"其他验证方式"，然后找到"通过拍摄脸部"的验证按钮
                                face_verify_url = self._get_face_verification_url(frame)
                                if face_verify_url:
                                    logger.info(f"【{self.pure_user_id}】✅ 获取到人脸验证链接: {face_verify_url}")
                                    
                                    # 截图并保存（完全参照旧框架，内联实现）
                                    screenshot_path = None
                                    try:
                                        # 等待页面加载完成
                                        time.sleep(2)
                                        
                                        # 先删除该账号的旧截图
                                        import glob
                                        import pathlib
                                        # 使用STATIC_DIR环境变量（Docker共享卷），本地回退到项目下的backend-web/static
                                        _static_env = os.environ.get("STATIC_DIR", "")
                                        if _static_env:
                                            _static_base = pathlib.Path(_static_env)
                                        else:
                                            _static_base = pathlib.Path(__file__).resolve().parent.parent.parent.parent / 'backend-web' / 'static'
                                        screenshots_dir = str(_static_base / 'uploads' / 'face')
                                        os.makedirs(screenshots_dir, exist_ok=True)
                                        
                                        old_screenshots = glob.glob(os.path.join(screenshots_dir, f"face_verify_{self.pure_user_id}_*.jpg"))
                                        for old_file in old_screenshots:
                                            try:
                                                os.remove(old_file)
                                                logger.info(f"【{self.pure_user_id}】删除旧的验证截图: {old_file}")
                                            except Exception as e:
                                                logger.warning(f"【{self.pure_user_id}】删除旧截图失败: {e}")
                                        
                                        # 尝试截取iframe元素的截图
                                        screenshot_bytes = None
                                        try:
                                            # 获取iframe元素并截图
                                            iframe_element = self.page.query_selector('iframe#alibaba-login-box')
                                            if iframe_element:
                                                screenshot_bytes = iframe_element.screenshot()
                                                logger.info(f"【{self.pure_user_id}】已截取iframe元素")
                                            else:
                                                # 如果找不到iframe，截取整个页面
                                                screenshot_bytes = self.page.screenshot(full_page=False)
                                                logger.info(f"【{self.pure_user_id}】已截取整个页面")
                                        except Exception as e:
                                            logger.warning(f"【{self.pure_user_id}】截取iframe失败，尝试截取整个页面: {e}")
                                            screenshot_bytes = self.page.screenshot(full_page=False)
                                        
                                        if screenshot_bytes:
                                            # 生成带时间戳的文件名并直接保存
                                            timestamp = get_beijing_now_naive().strftime('%Y%m%d_%H%M%S')
                                            filename = f"face_verify_{self.pure_user_id}_{timestamp}.jpg"
                                            file_path = os.path.join(screenshots_dir, filename)
                                            
                                            try:
                                                with open(file_path, 'wb') as f:
                                                    f.write(screenshot_bytes)
                                                # 返回相对URL路径，供前端访问
                                                screenshot_path = f"/static/uploads/face/{filename}"
                                                logger.info(f"【{self.pure_user_id}】✅ 人脸验证截图已保存: {file_path}, URL: {screenshot_path}")
                                            except Exception as e:
                                                logger.error(f"【{self.pure_user_id}】保存截图失败: {e}")
                                                screenshot_path = None
                                        else:
                                            logger.warning(f"【{self.pure_user_id}】⚠️ 截图失败，无法获取截图数据")
                                    except Exception as e:
                                        logger.error(f"【{self.pure_user_id}】截图时出错: {e}")
                                        import traceback
                                        logger.debug(traceback.format_exc())
                                    
                                    # 创建一个特殊的frame对象，包含截图路径
                                    class VerificationFrame:
                                        def __init__(self, original_frame, verify_url, screenshot_path=None):
                                            self._original_frame = original_frame
                                            self.verify_url = verify_url
                                            self.screenshot_path = screenshot_path
                                        
                                        def __getattr__(self, name):
                                            return getattr(self._original_frame, name)
                                    
                                    return True, VerificationFrame(frame, face_verify_url, screenshot_path)
                                
                                return True, frame
                    except Exception as e:
                        logger.debug(f"【{self.pure_user_id}】检查iframe时出错: {e}")
                        continue
            except Exception as e:
                logger.debug(f"【{self.pure_user_id}】检查alibaba-login-box iframe时出错: {e}")
            
            # 检查其他frames
            for idx, frame in enumerate(self.page.frames):
                try:
                    frame_url = frame.url
                    logger.debug(f"【{self.pure_user_id}】检查Frame {idx} 是否有二维码: {frame_url}")
                    
                    # 检查frame URL是否包含 mini_login（人脸验证或短信验证页面）
                    if 'mini_login' in frame_url:
                        # 进一步确认不是滑块验证
                        is_slider = False
                        for selector in slider_selectors:
                            try:
                                element = frame.query_selector(selector)
                                if element and element.is_visible():
                                    is_slider = True
                                    break
                            except Exception:
                                continue
                        
                        if not is_slider:
                            logger.info(f"【{self.pure_user_id}】✅ 在Frame {idx} 检测到 mini_login 页面（人脸验证/短信验证）")
                            return True, frame
                    
                    # 先检查这个frame是否是滑块验证
                    is_slider_frame = False
                    for selector in slider_selectors:
                        try:
                            element = frame.query_selector(selector)
                            if element and element.is_visible():
                                logger.debug(f"【{self.pure_user_id}】Frame {idx} 包含滑块验证元素，跳过")
                                is_slider_frame = True
                                break
                        except Exception:
                            continue
                    
                    if is_slider_frame:
                        continue  # 跳过滑块验证的frame
                    
                    # 人脸验证的关键词
                    face_keywords = ['拍摄脸部', '人脸验证', '人脸识别', '面部验证', '请进行人脸验证', '请完成人脸识别']
                    try:
                        frame_content = frame.content()
                        has_face_keyword = False
                        for keyword in face_keywords:
                            if keyword in frame_content:
                                has_face_keyword = True
                                break
                        
                        if has_face_keyword:
                            slider_keywords = ['滑块', '拖动', 'nc_', 'nc-container']
                            has_slider_keyword = any(keyword in frame_content for keyword in slider_keywords)
                            
                            if not has_slider_keyword:
                                logger.info(f"【{self.pure_user_id}】✅ 在Frame {idx} 检测到人脸验证")
                                return True, frame
                    except Exception:
                        pass
                        
                except Exception as e:
                    logger.debug(f"【{self.pure_user_id}】检查Frame {idx} 失败: {e}")
                    continue
            
            logger.info(f"【{self.pure_user_id}】未检测到二维码/人脸验证")
            return False, None
            
        except Exception as e:
            logger.error(f"【{self.pure_user_id}】检测二维码/人脸验证时出错: {e}")
            return False, None
    
    def _get_face_verification_url(self, frame) -> Tuple[str, Optional[str]]:
        """在alibaba-login-box frame中，点击'其他验证方式'，然后找到'通过拍摄脸部'的验证按钮，获取链接 - 参照旧框架
        
        Returns:
            Tuple[str, Optional[str]]: (验证URL, 截图路径)
        """
        try:
            logger.info(f"【{self.pure_user_id}】开始查找人脸验证链接...")
            
            # 等待frame加载完成
            time.sleep(2)
            
            # 查找"其他验证方式"链接并点击
            other_verify_clicked = False
            try:
                all_links = frame.query_selector_all('a')
                for link in all_links:
                    try:
                        text = link.inner_text()
                        if '其他验证方式' in text or ('其他' in text and '验证' in text):
                            logger.info(f"【{self.pure_user_id}】找到'其他验证方式'链接，点击中...")
                            link.click()
                            time.sleep(2)
                            other_verify_clicked = True
                            break
                    except Exception:
                        continue
            except Exception as e:
                logger.debug(f"【{self.pure_user_id}】查找'其他验证方式'链接时出错: {e}")
            
            if not other_verify_clicked:
                logger.warning(f"【{self.pure_user_id}】未找到'其他验证方式'链接，可能已经在验证方式选择页面")
            
            # 等待页面加载
            time.sleep(2)
            
            # 【重要】在点击按钮之前先截图（此时iframe还存在）
            screenshot_path = self._save_face_verification_screenshot()
            
            # 查找"通过拍摄脸部"相关的验证按钮，获取href并点击按钮
            face_verify_url = None
            
            # 方法1: 使用JavaScript精确查找
            try:
                href = frame.evaluate("""
                    () => {
                        const listItems = document.querySelectorAll('li');
                        for (let li of listItems) {
                            const descDiv = li.querySelector('div.desc');
                            if (descDiv && !descDiv.innerText.includes('手机') && (descDiv.innerText.includes('通过 拍摄脸部') || descDiv.innerText.includes('通过拍摄脸部') || descDiv.innerText.includes('拍摄脸部'))) {
                                const verifyButton = li.querySelector('a.ui-button, a.ui-button-small, button');
                                if (verifyButton && verifyButton.innerText && verifyButton.innerText.includes('立即验证')) {
                                    const href = verifyButton.href || verifyButton.getAttribute('href') || null;
                                    verifyButton.click();
                                    return href;
                                }
                            }
                        }
                        return null;
                    }
                """)
                if href:
                    face_verify_url = href
                    logger.info(f"【{self.pure_user_id}】通过JavaScript找到'通过拍摄脸部'验证按钮的href并已点击: {face_verify_url}")
            except Exception as e:
                logger.debug(f"【{self.pure_user_id}】方法1（JavaScript）查找失败: {e}")
            
            # 方法2: 如果方法1失败，使用Playwright API查找并点击
            if not face_verify_url:
                try:
                    list_items = frame.query_selector_all('li')
                    for li in list_items:
                        try:
                            desc_div = li.query_selector('div.desc')
                            if desc_div:
                                desc_text = desc_div.inner_text()
                                if '手机' not in desc_text and ('通过 拍摄脸部' in desc_text or '通过拍摄脸部' in desc_text or '拍摄脸部' in desc_text):
                                    logger.info(f"【{self.pure_user_id}】找到'通过拍摄脸部'选项（方法2）")
                                    verify_button = li.query_selector('a.ui-button, a.ui-button-small, button')
                                    if verify_button:
                                        button_text = verify_button.inner_text()
                                        if '立即验证' in button_text:
                                            href = verify_button.get_attribute('href')
                                            if href:
                                                face_verify_url = href
                                                logger.info(f"【{self.pure_user_id}】找到'通过拍摄脸部'验证按钮的href: {face_verify_url}")
                                                logger.info(f"【{self.pure_user_id}】点击'立即验证'按钮...")
                                                verify_button.click()
                                                logger.info(f"【{self.pure_user_id}】已点击'立即验证'按钮")
                                                break
                        except Exception:
                            continue
                except Exception as e:
                    logger.debug(f"【{self.pure_user_id}】方法2查找失败: {e}")
            
            if face_verify_url:
                # 如果是相对路径，转换为绝对路径
                if not face_verify_url.startswith('http'):
                    base_url = frame.url.split('/iv/')[0] if '/iv/' in frame.url else 'https://passport.goofish.com'
                    if face_verify_url.startswith('/'):
                        face_verify_url = base_url + face_verify_url
                    else:
                        face_verify_url = base_url + '/' + face_verify_url
                
                return face_verify_url, screenshot_path
            else:
                logger.warning(f"【{self.pure_user_id}】未找到人脸验证链接，返回原始frame URL")
                return (frame.url if hasattr(frame, 'url') else None), screenshot_path
                
        except Exception as e:
            logger.error(f"【{self.pure_user_id}】获取人脸验证链接时出错: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return None, None
    
    def _save_face_verification_screenshot(self) -> Optional[str]:
        """保存人脸验证截图 - 完全参照旧框架"""
        try:
            # 等待页面加载完成
            time.sleep(2)
            
            # 先删除该账号的旧截图
            import glob
            import pathlib
            # 使用STATIC_DIR环境变量（Docker共享卷），本地回退到项目下的backend-web/static
            _static_env = os.environ.get("STATIC_DIR", "")
            if _static_env:
                _static_base = pathlib.Path(_static_env)
            else:
                _static_base = pathlib.Path(__file__).resolve().parent.parent.parent.parent / 'backend-web' / 'static'
            screenshots_dir = str(_static_base / 'uploads' / 'face')
            os.makedirs(screenshots_dir, exist_ok=True)
            logger.info(f"【{self.pure_user_id}】截图保存目录: {screenshots_dir}")
            
            old_screenshots = glob.glob(os.path.join(screenshots_dir, f"face_verify_{self.pure_user_id}_*.jpg"))
            for old_file in old_screenshots:
                try:
                    os.remove(old_file)
                    logger.info(f"【{self.pure_user_id}】删除旧的验证截图: {old_file}")
                except Exception as e:
                    logger.warning(f"【{self.pure_user_id}】删除旧截图失败: {e}")
            
            # 尝试截取iframe元素的截图（完全参照旧框架，不设置timeout）
            screenshot_bytes = None
            try:
                # 获取iframe元素并截图
                iframe_element = self.page.query_selector('iframe#alibaba-login-box')
                if iframe_element:
                    screenshot_bytes = iframe_element.screenshot()
                    logger.info(f"【{self.pure_user_id}】已截取iframe元素")
                else:
                    # 如果找不到iframe，截取整个页面
                    screenshot_bytes = self.page.screenshot(full_page=False)
                    logger.info(f"【{self.pure_user_id}】已截取整个页面")
            except Exception as e:
                logger.warning(f"【{self.pure_user_id}】截取iframe失败，尝试截取整个页面: {e}")
                try:
                    screenshot_bytes = self.page.screenshot(full_page=False)
                except Exception as e2:
                    logger.error(f"【{self.pure_user_id}】截取整个页面也失败: {e2}")
            
            if screenshot_bytes:
                # 生成带时间戳的文件名并直接保存
                timestamp = get_beijing_now_naive().strftime('%Y%m%d_%H%M%S')
                filename = f"face_verify_{self.pure_user_id}_{timestamp}.jpg"
                file_path = os.path.join(screenshots_dir, filename)
                
                try:
                    with open(file_path, 'wb') as f:
                        f.write(screenshot_bytes)
                    # 返回相对URL路径，供前端访问
                    screenshot_path = f"/static/uploads/face/{filename}"
                    logger.info(f"【{self.pure_user_id}】✅ 人脸验证截图已保存: {file_path}, URL: {screenshot_path}")
                    return screenshot_path
                except Exception as e:
                    logger.error(f"【{self.pure_user_id}】保存截图失败: {e}")
                    return None
            else:
                logger.warning(f"【{self.pure_user_id}】⚠️ 截图失败，无法获取截图数据")
                return None
        except Exception as e:
            logger.error(f"【{self.pure_user_id}】截图时出错: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return None
    
    def _send_face_verification_notification(self, notification_callback: Callable, screenshot_path: Optional[str], frame_url: Optional[str]):
        """发送人脸验证通知 - 参照旧框架
        
        Args:
            notification_callback: 通知回调函数
            screenshot_path: 截图路径
            frame_url: 验证链接URL
        """
        try:
            if screenshot_path:
                notification_msg = (
                    f"⚠️ 账号密码登录需要人脸验证\n\n"
                    f"账号: {self.pure_user_id}\n"
                    f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    f"请登录自动化网站，访问账号管理模块，进行对应账号的人脸验证\n"
                    f"在验证期间，闲鱼自动回复暂时无法使用。"
                )
            else:
                notification_msg = (
                    f"⚠️ 账号密码登录需要人脸验证\n\n"
                    f"账号: {self.pure_user_id}\n"
                    f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    f"请点击验证链接完成验证:\n{frame_url}\n\n"
                    f"在验证期间，闲鱼自动回复暂时无法使用。"
                )
            
            logger.info(f"【{self.pure_user_id}】准备发送人脸验证通知，截图路径: {screenshot_path}, URL: {frame_url}")
            
            # 检查回调是否是异步函数
            import asyncio
            import inspect
            if inspect.iscoroutinefunction(notification_callback):
                # 在新的线程中运行异步回调
                def run_async_callback():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        # 传递通知消息、截图路径和URL给回调
                        # 参数顺序：message, screenshot_path, verification_url
                        loop.run_until_complete(notification_callback(notification_msg, screenshot_path, frame_url))
                        logger.info(f"【{self.pure_user_id}】✅ 异步通知回调已执行")
                    except Exception as async_err:
                        logger.error(f"【{self.pure_user_id}】异步通知回调执行失败: {async_err}")
                        import traceback
                        logger.error(traceback.format_exc())
                    finally:
                        loop.close()
                
                import threading
                thread = threading.Thread(target=run_async_callback)
                thread.start()
                logger.info(f"【{self.pure_user_id}】异步通知线程已启动")
            else:
                # 同步回调直接调用（传递通知消息、截图路径和URL）
                notification_callback(notification_msg, screenshot_path, frame_url)
                logger.info(f"【{self.pure_user_id}】✅ 同步通知回调已执行")
        
        except Exception as e:
            logger.error(f"【{self.pure_user_id}】发送人脸验证通知失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _wait_for_face_verification(self) -> bool:
        """等待用户完成人脸验证
        
        Returns:
            是否验证成功
        """
        logger.info(f"【{self.pure_user_id}】等待人脸验证完成...")
        
        check_interval = 10  # 每10秒检查一次
        max_wait_time = 300  # 最多等待5分钟
        waited_time = 0
        
        # 释放槽位，让其他请求可以进来
        from common.services.captcha.concurrency import concurrency_manager
        slot_released = False
        try:
            concurrency_manager.unregister_instance(self.user_id)
            slot_released = True
            logger.info(f"【{self.pure_user_id}】人脸验证等待期间已释放槽位")
        except Exception as e:
            logger.warning(f"【{self.pure_user_id}】释放槽位失败: {e}")
        
        while waited_time < max_wait_time:
            time.sleep(check_interval)
            waited_time += check_interval
            
            # 检查登录状态
            if self._check_login_success():
                logger.success(f"【{self.pure_user_id}】✅ 人脸验证完成，登录成功！")
                
                # 重新获取槽位
                if slot_released:
                    try:
                        concurrency_manager.register_instance(self.user_id, self)
                        logger.info(f"【{self.pure_user_id}】已重新获取槽位")
                    except Exception as e:
                        logger.warning(f"【{self.pure_user_id}】重新获取槽位失败: {e}")
                
                return True
            
            # 同步检查登录错误与风控验证：
            # 1) baxia-punish 风控图形滑块（如"找两个松鼠"）：账号本身正常，仅冷却不禁用
            # 2) 登录错误（账密错误、账号冻结、操作过于频繁）：禁用账号 + 冷却
            # 命中后立即以对应异常抛出，让外层走相应分支，避免被错判为"人脸验证超时"。
            try:
                # 优先检测 punish（特异性更强，避免误归类为登录错误）
                has_punish, punish_msg = self._check_baxia_punish_captcha()
                if has_punish:
                    logger.warning(
                        f"【{self.pure_user_id}】⚠️ 等待期间触发风控图形滑块验证，账号本身正常，仅设置冷却（不禁用）：{punish_msg}"
                    )
                    raise BaxiaPunishCaptchaException(punish_msg)
                
                has_error, error_message = self._check_login_error()
                if has_error:
                    logger.error(
                        f"【{self.pure_user_id}】❌ 等待期间检测到登录错误: {error_message}"
                    )
                    disable_reason = error_message if error_message else "登录失败"
                    # 内层禁用 + 通知（与 login_with_password_playwright 主流程保持一致）
                    self._disable_account_on_timeout(disable_reason)
                    # 抛出 LoginPageErrorException 透传给外层，槽位由 close() 统一兜底释放
                    raise LoginPageErrorException(disable_reason)
            except BaxiaPunishCaptchaException:
                # 透传给外层，不在此处吞掉
                raise
            except LoginPageErrorException:
                # 透传给外层，不在此处吞掉
                raise
            except Exception as e:
                # 检查动作本身的异常（如 page 已关闭等）不影响等待循环
                logger.debug(
                    f"【{self.pure_user_id}】等待期间检查登录错误时出错: {e}"
                )
            
            logger.info(f"【{self.pure_user_id}】等待中... ({waited_time}/{max_wait_time}秒)")
        
        # 超时
        logger.warning(f"【{self.pure_user_id}】❌ 人脸验证超时（{max_wait_time}秒）")
        
        # 重新获取槽位（即使超时也要释放资源）
        if slot_released:
            try:
                concurrency_manager.register_instance(self.user_id, self)
                logger.info(f"【{self.pure_user_id}】已重新获取槽位")
            except Exception as e:
                logger.warning(f"【{self.pure_user_id}】重新获取槽位失败: {e}")
        
        return False
    
    def _get_cookies(self) -> Optional[Dict[str, str]]:
        """获取Cookie
        
        Returns:
            Cookie字典
        """
        try:
            cookies_dict = {}
            cookies_list = self.context.cookies()
            for cookie in cookies_list:
                cookies_dict[cookie.get('name', '')] = cookie.get('value', '')
            
            logger.info(f"【{self.pure_user_id}】成功获取Cookie，包含 {len(cookies_dict)} 个字段")
            
            if cookies_dict:
                logger.success("✅ Cookie有效")
                return cookies_dict
            else:
                logger.error("❌ Cookie为空")
                return None
        except Exception as e:
            logger.error(f"【{self.pure_user_id}】获取Cookie失败: {e}")
            return None
    
    def _disable_account_on_timeout(self, reason: str):
        """登录失败/人脸验证超时禁用账号，并根据账号通知配置发送提醒。

        触发场景：
        - 检测到 `class="login-error-msg"` 时（账号密码错误等）
        - 人脸验证超时（受系统设置开关控制）

        Args:
            reason: 禁用原因（会写入 xy_accounts.disable_reason，并在通知详情中展示）
        """
        try:
            from common.db.compat import db_manager
            from common.services.captcha.concurrency import disabled_account_manager
            
            # 检查系统设置：人脸验证超时是否自动禁用账号
            if "人脸验证超时" in reason:
                setting_value = db_manager.get_system_setting(
                    "account.face_verify_timeout_disable", "true"
                )
                if setting_value and setting_value.lower() != "true":
                    logger.info(f"【{self.pure_user_id}】系统设置关闭了人脸验证超时自动禁用，跳过禁用操作")
                    return
            
            logger.info(f"【{self.pure_user_id}】开始禁用账号，原因: {reason}")
            
            # 添加到禁用账号列表
            disabled_account_manager.add(self.pure_user_id)
            
            # 更新数据库
            success = db_manager.disable_account(self.pure_user_id, reason=reason)
            
            if success:
                logger.info(f"【{self.pure_user_id}】✅ 账号已禁用，原因: {reason}")
            else:
                logger.warning(f"【{self.pure_user_id}】⚠️ 未找到账号，无法禁用")

            # 不论数据库是否更新成功，只要触发了禁用流程都尝试发送通知
            self._send_account_disabled_notification(reason)
        
        except Exception as e:
            logger.error(f"【{self.pure_user_id}】❌ 禁用账号失败: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _send_account_disabled_notification(self, reason: str):
        """账号被自动禁用后发送提醒通知（同步方法）。

        复用 `NotificationManager.send_token_refresh_notification`，依赖其内置的
        冷却机制避免重复发送。本方法只是动态 import 该类，并将协程调度到事件循环中。

        Args:
            reason: 禁用原因（决定通知类型和正文详情）
        """
        try:
            # 动态 import：common 包不强依赖 websocket 包，按运行时上下文按需加载。
            # 双层 fallback 仅用于源码 .py 模式下兼容跨服务调用方（如 backend-web 未来
            # 可能新增调用）。在加密 .so 模式下，websocket 服务的 .so 内部 m_name 已
            # 统一为短路径 `app.services.xianyu.notification_manager`，长路径 fallback
            # 触发 Cython multi-phase init 的 m_name 校验失败，会安全 ImportError 而
            # 不会重新引发同一 .so 双初始化的段错误。
            NotificationManager = None
            try:
                from app.services.xianyu.notification_manager import NotificationManager  # noqa: F401
            except ImportError:
                try:
                    from websocket.app.services.xianyu.notification_manager import (  # noqa: F401
                        NotificationManager,
                    )
                except ImportError:
                    logger.warning(
                        f"【{self.pure_user_id}】NotificationManager 不可用，跳过禁用通知发送"
                    )
                    return

            # 根据 reason（页面原始错误文案）识别通知类型，对应 NotificationManager.notification_title_map
            # 注意：reason 现在直接来自闲鱼登录页 .login-error-msg 文本，不再带有自加前缀
            password_keywords = ("账密", "密码", "账号或密码", "用户名", "登录密码")
            if "人脸验证超时" in reason:
                notification_type = "face_verification_timeout"
            elif any(keyword in reason for keyword in password_keywords):
                notification_type = "password_error"
            else:
                notification_type = "account_disabled"

            error_message = f"账号已被自动禁用，原因: {reason}\n请检查账号状态后在账号管理中手动启用。"

            import asyncio
            manager = NotificationManager(self.pure_user_id)
            coro = manager.send_token_refresh_notification(error_message, notification_type)

            # 当前线程是否已经处于异步事件循环中
            try:
                running_loop = asyncio.get_running_loop()
            except RuntimeError:
                running_loop = None

            if running_loop is not None:
                # 已有事件循环（异步上下文），fire-and-forget 调度协程
                try:
                    asyncio.ensure_future(coro, loop=running_loop)
                except Exception as schedule_e:
                    logger.warning(f"【{self.pure_user_id}】调度禁用通知任务失败: {schedule_e}")
            else:
                # 同步上下文（子线程），创建临时事件循环执行
                new_loop = asyncio.new_event_loop()
                try:
                    new_loop.run_until_complete(coro)
                finally:
                    try:
                        new_loop.close()
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"【{self.pure_user_id}】发送账号禁用通知失败: {e}")


# 导出函数，用于兼容旧代码
def run_slider_verification(
    user_id: str,
    url: str,
    enable_learning: bool = True,
    headless: bool = True
) -> Tuple[bool, Optional[Dict[str, str]]]:
    """运行滑块验证（兼容函数）
    
    Args:
        user_id: 用户ID
        url: 验证URL
        enable_learning: 是否启用学习
        headless: 是否无头模式
    
    Returns:
        (是否成功, Cookie字典)
    """
    service = XianyuSliderStealth(user_id, enable_learning, headless)
    return service.run(url)
