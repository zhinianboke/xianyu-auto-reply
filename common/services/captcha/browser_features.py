"""
浏览器特征和反检测脚本

提供随机浏览器特征生成和反检测JavaScript脚本
复刻原始 utils/xianyu_slider_stealth.py 中的浏览器特征相关逻辑
"""
from __future__ import annotations

import random
from typing import Any, Dict


def get_random_browser_features() -> Dict[str, Any]:
    """获取随机浏览器特征"""
    # 随机选择窗口大小（使用更大的尺寸以适应最大化）
    window_sizes = [
        "1920,1080", "1920,1200", "2560,1440", "1680,1050", "1600,900"
    ]

    # 随机选择语言
    languages = [
        ("zh-CN", "zh-CN,zh;q=0.9,en;q=0.8"),
        ("zh-CN", "zh-CN,zh;q=0.9"),
        ("zh-CN", "zh-CN,zh;q=0.8,en;q=0.6")
    ]

    # 随机选择用户代理
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    ]

    window_size = random.choice(window_sizes)
    lang, accept_lang = random.choice(languages)
    user_agent = random.choice(user_agents)

    # 解析窗口大小
    width, height = map(int, window_size.split(','))

    return {
        'window_size': window_size,
        'lang': lang,
        'accept_lang': accept_lang,
        'user_agent': user_agent,
        'locale': lang,
        'viewport_width': width,
        'viewport_height': height,
        'device_scale_factor': random.choice([1.0, 1.25, 1.5]),
        'is_mobile': False,
        'has_touch': False,
        'timezone_id': 'Asia/Shanghai'
    }


def get_stealth_script(browser_features: Dict[str, Any]) -> str:
    """获取增强反检测脚本"""
    return f"""
        // 隐藏webdriver属性（使用try-catch避免重复定义错误）
        try {{
            Object.defineProperty(navigator, 'webdriver', {{
                get: () => undefined,
                configurable: true
            }});
        }} catch (e) {{}}
        
        // 隐藏自动化相关属性
        try {{ delete navigator.__proto__.webdriver; }} catch (e) {{}}
        try {{ delete window.navigator.webdriver; }} catch (e) {{}}
        try {{ delete window.navigator.__proto__.webdriver; }} catch (e) {{}}
        
        // 模拟真实浏览器环境
        if (!window.chrome) {{
            window.chrome = {{
                runtime: {{}},
                loadTimes: function() {{}},
                csi: function() {{}},
                app: {{}}
            }};
        }}
        
        // 覆盖plugins - 随机化
        try {{
            const pluginCount = {random.randint(3, 8)};
            Object.defineProperty(navigator, 'plugins', {{
                get: () => Array.from({{length: pluginCount}}, (_, i) => ({{
                    name: 'Plugin' + i,
                    description: 'Plugin ' + i
                }})),
                configurable: true
            }});
        }} catch (e) {{}}
        
        // 覆盖languages
        try {{
            Object.defineProperty(navigator, 'languages', {{
                get: () => ['{browser_features['locale']}', 'zh', 'en'],
                configurable: true
            }});
        }} catch (e) {{}}
        
        // 模拟真实的屏幕信息
        try {{
            Object.defineProperty(screen, 'availWidth', {{ get: () => {browser_features['viewport_width']}, configurable: true }});
            Object.defineProperty(screen, 'availHeight', {{ get: () => {browser_features['viewport_height'] - 40}, configurable: true }});
            Object.defineProperty(screen, 'width', {{ get: () => {browser_features['viewport_width']}, configurable: true }});
            Object.defineProperty(screen, 'height', {{ get: () => {browser_features['viewport_height']}, configurable: true }});
        }} catch (e) {{}}
        
        // 隐藏自动化检测 - 随机化硬件信息
        try {{
            Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => {random.choice([2, 4, 6, 8])}, configurable: true }});
        }} catch (e) {{}}
        Object.defineProperty(navigator, 'deviceMemory', {{ get: () => {random.choice([4, 8, 16])} }});
        
        // 模拟真实的时区
        Object.defineProperty(Intl.DateTimeFormat.prototype, 'resolvedOptions', {{
            value: function() {{
                return {{ timeZone: '{browser_features['timezone_id']}' }};
            }}
        }});
        
        // 隐藏自动化痕迹
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
        
        // 模拟有头模式的特征
        Object.defineProperty(navigator, 'maxTouchPoints', {{ get: () => 0 }});
        Object.defineProperty(navigator, 'platform', {{ get: () => 'Win32' }});
        Object.defineProperty(navigator, 'vendor', {{ get: () => 'Google Inc.' }});
        Object.defineProperty(navigator, 'vendorSub', {{ get: () => '' }});
        Object.defineProperty(navigator, 'productSub', {{ get: () => '20030107' }});
        
        // 模拟真实的连接信息
        Object.defineProperty(navigator, 'connection', {{
            get: () => ({{
                effectiveType: "{random.choice(['3g', '4g', '5g'])}",
                rtt: {random.randint(20, 100)},
                downlink: {round(random.uniform(1, 10), 2)}
            }})
        }});
        
        // 隐藏无头模式特征
        Object.defineProperty(navigator, 'headless', {{ get: () => undefined }});
        Object.defineProperty(window, 'outerHeight', {{ get: () => {browser_features['viewport_height']} }});
        Object.defineProperty(window, 'outerWidth', {{ get: () => {browser_features['viewport_width']} }});
        
        // 模拟真实的媒体设备
        Object.defineProperty(navigator, 'mediaDevices', {{
            get: () => ({{
                enumerateDevices: () => Promise.resolve([])
            }}),
        }});
        
        // 隐藏自动化检测特征
        Object.defineProperty(navigator, 'webdriver', {{ get: () => undefined }});
        Object.defineProperty(navigator, '__webdriver_script_fn', {{ get: () => undefined }});
        Object.defineProperty(navigator, '__webdriver_evaluate', {{ get: () => undefined }});
        Object.defineProperty(navigator, '__webdriver_unwrapped', {{ get: () => undefined }});
        Object.defineProperty(navigator, '__fxdriver_evaluate', {{ get: () => undefined }});
        Object.defineProperty(navigator, '__driver_evaluate', {{ get: () => undefined }});
        Object.defineProperty(navigator, '__webdriver_script_func', {{ get: () => undefined }});
        
        // 隐藏Playwright特定的对象
        delete window.playwright;
        delete window.__playwright;
        delete window.__pw_manual;
        delete window.__pw_original;
        
        // 模拟真实的用户代理
        Object.defineProperty(navigator, 'userAgent', {{
            get: () => '{browser_features['user_agent']}'
        }});
        
        // 隐藏自动化相关的全局变量
        delete window.webdriver;
        delete window.__webdriver_script_fn;
        delete window.__webdriver_evaluate;
        delete window.__webdriver_unwrapped;
        delete window.__fxdriver_evaluate;
        delete window.__driver_evaluate;
        delete window.__webdriver_script_func;
        delete window._selenium;
        delete window._phantom;
        delete window.callPhantom;
        delete window._phantom;
        delete window.phantom;
        delete window.Buffer;
        delete window.emit;
        delete window.spawn;
        
        // Canvas指纹随机化
        const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function() {{
            const context = this.getContext('2d');
            if (context) {{
                const imageData = context.getImageData(0, 0, this.width, this.height);
                const data = imageData.data;
                for (let i = 0; i < data.length; i += 4) {{
                    if (Math.random() < 0.001) {{
                        data[i] = Math.floor(Math.random() * 256);
                    }}
                }}
                context.putImageData(imageData, 0, 0);
            }}
            return originalToDataURL.apply(this, arguments);
        }};
        
        // 音频指纹随机化
        const originalGetChannelData = AudioBuffer.prototype.getChannelData;
        AudioBuffer.prototype.getChannelData = function(channel) {{
            const data = originalGetChannelData.call(this, channel);
            for (let i = 0; i < data.length; i += 1000) {{
                if (Math.random() < 0.01) {{
                    data[i] += Math.random() * 0.0001;
                }}
            }}
            return data;
        }};
        
        // WebGL指纹随机化
        const originalGetParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {{
            if (parameter === 37445) {{ // UNMASKED_VENDOR_WEBGL
                return 'Intel Inc.';
            }}
            if (parameter === 37446) {{ // UNMASKED_RENDERER_WEBGL
                return 'Intel Iris OpenGL Engine';
            }}
            return originalGetParameter.call(this, parameter);
        }};
        
        // 增强鼠标移动轨迹记录
        let mouseMovements = [];
        let lastMouseTime = Date.now();
        document.addEventListener('mousemove', function(e) {{
            const now = Date.now();
            const timeDiff = now - lastMouseTime;
            mouseMovements.push({{
                x: e.clientX,
                y: e.clientY,
                time: now,
                timeDiff: timeDiff
            }});
            lastMouseTime = now;
            if (mouseMovements.length > 100) {{
                mouseMovements.shift();
            }}
        }}, true);
        
        // 模拟真实的屏幕触摸点数
        Object.defineProperty(navigator, 'maxTouchPoints', {{
            get: () => {random.choice([0, 1, 5, 10])}
        }});
        
        // 伪装Performance API
        const originalNow = Performance.prototype.now;
        Performance.prototype.now = function() {{
            return originalNow.call(this) + Math.random() * 0.1;
        }};
        
        // 伪装Date API（添加微小随机偏移）
        const OriginalDate = Date;
        Date = function(...args) {{
            if (args.length === 0) {{
                const date = new OriginalDate();
                const offset = Math.floor(Math.random() * 3) - 1;
                return new OriginalDate(date.getTime() + offset);
            }}
            return new OriginalDate(...args);
        }};
        Date.prototype = OriginalDate.prototype;
        Date.now = function() {{
            return OriginalDate.now() + Math.floor(Math.random() * 3) - 1;
        }};
        
        // 隐藏CDP运行时特征
        Object.defineProperty(navigator, 'webdriver', {{
            get: () => undefined
        }});
        
        // 隐藏Playwright特征
        delete window.__playwright;
        delete window.__pw_manual;
        delete window.__PW_inspect;
        
        // 伪装chrome对象（防止检测headless）
        if (!window.chrome) {{
            window.chrome = {{}};
        }}
        window.chrome.runtime = {{
            id: undefined,
            sendMessage: function() {{}},
            connect: function() {{}}
        }};
    """

