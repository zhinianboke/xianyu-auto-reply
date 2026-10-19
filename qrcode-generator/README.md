# 链接生成二维码工具 · 闲鱼强制跳转浏览器版

将任意链接生成二维码，并支持**闲鱼 / 微信 / QQ 扫码后强制跳转系统浏览器**打开目标链接。

## 文件说明

| 文件 | 作用 |
|------|------|
| `index.html` | 二维码生成器（可视化工具，支持自定义尺寸/颜色/跳转模式） |
| `redirect.html` | 跳转处理页（检测应用内 webview，尝试唤起系统浏览器） |
| `xianyu_qrcode_force_browser.png` | 已生成的「强制跳转浏览器」二维码 |
| `xianyu_qrcode_direct.png` | 已生成的「直链」二维码（备用） |

## 快速使用（3 步）

### 1. 部署跳转页

将 `redirect.html` 上传到你的服务器，确保可通过 HTTPS 访问，例如：

```
https://xianyu.jinan.me/redirect.html
```

> 必须是 HTTPS 且公网可访问的地址，否则闲鱼扫码无法加载。

### 2. 生成二维码

打开 `index.html`，输入目标链接，确认「闲鱼强制跳转浏览器」开关已开启，跳转页地址填第 1 步的地址，点击「生成二维码」→「下载 PNG」。

也可直接使用已生成的 `xianyu_qrcode_force_browser.png`（已预填目标链接和 xianyu.jinan.me 跳转页）。

### 3. 用闲鱼扫码

用闲鱼 APP 扫描二维码 → 跳转页加载 → 自动尝试唤起系统浏览器打开目标链接。若被系统拦截，页面会显示「在浏览器中打开」按钮引导操作。

## 工作原理

```
用户扫码
  ↓
闲鱼内置浏览器打开 redirect.html?url=目标链接
  ↓
【闲鱼加载页】短暂展示（普通浏览器约 0.3s，应用内浏览器立即尝试唤起）
  ↓
redirect.html 检测 User-Agent：
  ├─ 闲鱼/微信/QQ webview → 尝试 intent:// 等 scheme 唤起系统浏览器
  │                          失败则显示「在浏览器中打开」引导按钮
  └─ 普通浏览器 → 直接 window.location.replace 跳转到目标链接
```

### 强制浏览器策略（多策略组合，最大化成功率）

页面加载后立即依次尝试以下策略（每种间隔 80ms），只要有一个命中即可唤起系统浏览器：

**Android（9 种策略）：**
1. `intent://` scheme（标准 Android 方式，`ACTION_VIEW` + `BROWSABLE`）
2. `googlechrome://navigate?url=` 直接唤起 Chrome
3. `microsoft-edge://?url=` 唤起 Edge
4. `<meta http-equiv="refresh">` 刷新跳转
5. `<iframe>` 加载 intent scheme
6. `<a target="_system|_blank|_top">` 模拟点击（Android WebView 约定 `_system` 在系统浏览器打开）
7. `<form target="_blank">` 表单提交
8. `window.open()` 新窗口
9. `location.replace()` 直跳（兜底）

**iOS（6 种策略）：**
1. `x-safari-https://` scheme 唤起 Safari
2. `<meta refresh>` 刷新跳转
3. `<a target="_blank">` 模拟点击
4. `window.open()` 新窗口
5. `<form target="_blank">` 表单提交
6. `location.replace()` 直跳（兜底）

**兜底：** 所有策略执行完后（约 1.5 秒），若页面仍在 webview 中，显示「在浏览器中打开」手动引导页。

> ⚠️ **技术限制说明**：闲鱼/淘宝系 APP 的 webview 高度定制，会拦截部分外部 scheme。本工具已穷尽前端可用的所有唤起技巧，最大化成功率，但无法 100% 保证绕过所有版本的安全限制。若自动唤起失败，用户可一键复制链接或按引导手动打开。

## 自定义目标链接

修改 `index.html` 中的 `PRESET_URL` 变量，或直接在页面文本框输入。

## 自定义加载等待时间

在 `redirect.html` 顶部修改以下参数：

```js
var MANUAL_DELAY = 1100;   // 尝试跳转后多久显示手动引导（毫秒）
```

普通浏览器约 320ms 自动跳转；应用内浏览器立即尝试唤起系统浏览器。
如需调整普通浏览器跳转速度，修改主流程中的 `320` 数值。

如需重新生成 PNG：

```bash
python3 -c "
import qrcode
from urllib.parse import quote
target = '你的目标链接'
redirect = 'https://你的域名/redirect.html?url=' + quote(target, safe='')
qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=2)
qr.add_data(redirect)
qr.make(fit=True)
qr.make_image().save('my_qrcode.png')
"
```

## 关于闲鱼安全机制

闲鱼/淘宝系 APP 对外部链接有安全风控，会拦截部分自动跳转。本工具采用「自动尝试 + 手动引导」双保险策略，最大程度提升跳转成功率，但**无法 100% 绕过所有版本的安全限制**。若自动跳转失败，用户可一键复制链接到浏览器粘贴打开。
