# 闲鱼自动回复系统

基于 FastAPI + React + MySQL + Redis + Playwright 的闲鱼多账号自动化系统。

主系统负责账号管理、消息收发、自动回复、自动发货、商品发布与后台管理；`promotion` 子项目负责返佣账号、选品规则、素材库、发布规则、删除规则和相关修复任务。

## 🔴 说明

> **🔴 诚邀各位开发者提交pr，完善系统**
>
> **🔴 承接各类项目定制，各类项目均可，有需要可联系，另外我菜，不一定都会**

## 🔴 最新源码地址(建议转存)

> 🔴 我用夸克网盘给你分享了「自动发货」，点击链接或复制整段内容，打开「夸克网盘APP」即可获取。
> 
> 🔴 /~79313YhCQU~:/
> 
> 🔴 **链接：https://pan.quark.cn/s/af567356cba7**

## 交流群

| 微信群 | QQ群 | 微信公众号 | Telegram | 赞赏支持 |
|:---:|:---:|:---:|:---:|:---:|
| ![微信群](https://xy.zhinianboke.com/static/qrcode/wechat-group.png) | ![QQ群](https://xy.zhinianboke.com/static/qrcode/qq-group.jpg) | ![微信公众号](https://xy.zhinianboke.com/static/qrcode/wechat-official-group.jpg) | ![Telegram](https://xy.zhinianboke.com/static/qrcode/telegram-group.png) | ![赞赏支持](https://xy.zhinianboke.com/static/qrcode/reward-group.png) |
| 扫码加好友拉微信交流群 | 扫码加入QQ交流群 | 关注公众号发送"最新源码"获取最新代码 | 扫码加入Telegram群 | 如果觉得好用，请作者喝杯咖啡 |

如群二维码过期，请关注公众号获取最新群链接。

---

## 功能概览

### 主系统

| 功能 | 简介 |
| --- | --- |
| 多账号管理 | 闲鱼多账号登录、状态管理、Cookie 维护与续期 |
| 自动回复 | 文本、图片、API 关键词、默认回复及商品专属回复 |
| AI 回复 | 大模型上下文对话与智能回复 |
| 在线聊天 | 会话管理、消息收发与聊天记录 |
| 自动发货 | 卡券与虚拟商品发货、自动补发及发货记录 |
| 商品发布 | 素材库、地址库、AI 上架、单品与批量发布、定时发布及自动续售 |
| 订单与评价 | 订单同步、状态跟踪、自动评价及求小红花 |
| 商品采集与分销 | 商品采集、货源管理、分销对接与结算 |
| 用户管理 | 用户查询、角色权限、账号启停、余额调整与结算记录 |
| 通知管理 | 多渠道消息、发货、账号状态及上新监控通知 |
| 安全设置 | 注册与登录限流、账号锁定、邮箱后缀及 IP 限制 |
| 定时任务 | 系统任务间隔配置、启停、手动执行及安全频率检查 |
| 日志查询 | 注册、登录、邮件、安全、回复、发货、发布与风控日志 |
| 系统管理 | 系统设置、公告、反馈、广告管理与支付充值 |
| 远程接口 | Token 远程获取、账号查询、Cookie 同步、商品发布、订单及消息日志查询 |

### 返佣子系统

| 功能 | 简介 |
| --- | --- |
| 返佣账号 | 账号登录、状态管理与 Cookie 维护 |
| 选品规则 | 按规则选品并写入素材库 |
| 素材库 | 商品文案、图片、淘口令、短链、库存及发布状态管理 |
| 发布与删除规则 | 定时发布、删除返佣商品 |
| 补偿任务 | 商品 ID 回写、短链修复与卡券补偿 |

### 移动端

提供 Android 客户端，支持消息、订单、商品和账号管理。详见 [移动端说明](xianyu-mobile/README.md)。

## 技术栈

后端采用 FastAPI、SQLAlchemy、MySQL、Redis、Playwright 和 APScheduler；网页采用 React、TypeScript、Vite 和 TailwindCSS；支持 Docker Compose 部署。

## 快速开始

### 一键部署

在 Linux 服务器上执行，使用 root 或具备免密 sudo 权限的账号；执行远程命令前需已安装 `curl`：

```bash
curl -fsSL https://xy-update.zhinianboke.com/deploy.sh | sed 's/\r$//' | bash
```

脚本自动准备 Docker / Compose、生成 `.env` 并拉取镜像部署；已有配置保留。

### 一键更新

在原部署目录执行：

```bash
curl -fsSL https://xy-update.zhinianboke.com/update.sh | sed 's/\r$//' | bash
```

已下载脚本时也可执行 `bash update.sh`。更新会拉取最新镜像并重建应用容器，保留 MySQL / Redis 数据卷与配置。此方式对应 `deploy.sh` 部署；远程数据库部署按下一节更新，源码部署按源码章节更新。

### 使用远程 MySQL / Redis 部署

先安装 Docker / Compose，准备好远程数据库与 Redis，再执行：

```bash
curl -fsSL https://xy-update.zhinianboke.com/deploy_remote.sh | sed 's/\r$//' | bash
```

首次运行生成 `.env.remote` 后退出。填写真实连接信息并授权部署机访问，再执行一次同样的命令完成部署；后续更新也在原目录重新执行该命令，沿用原配置。数据库或 Redis 在宿主机上时，使用容器可访问的宿主机地址，不能填写 `127.0.0.1`。远程 MySQL 的 `max_connections` 应覆盖所有服务连接池上限，单实例默认配置建议不少于 4000。

### 源码 Docker 部署

先安装 Git、Docker 和 Docker Compose，然后执行：

```bash
git clone https://github.com/zhinianboke/xianyu-auto-reply.git
cd xianyu-auto-reply
bash build.sh rebuild
```

首次运行会生成 `.env` 并构建启动；自定义配置后，重新执行 `bash build.sh rebuild`。

源码更新在仓库目录执行：

```bash
git pull --ff-only
bash build.sh rebuild
```

有本地修改时先自行保存或合并修改。源码部署通过 `build.sh` 重建，`update.sh` 用于预构建镜像部署。

| 命令 | 用途 |
| --- | --- |
| `bash build.sh start` | 启动服务 |
| `bash build.sh stop` | 停止服务 |
| `bash build.sh restart` | 重启服务 |
| `bash build.sh logs` | 查看日志 |
| `bash build.sh status` | 查看状态 |

### 直接运行源码

准备 Python 3.11+、Node.js 18+、MySQL 8 和 Redis，克隆仓库。以下命令以 Linux / macOS 为例。

1. 分别将 [Backend-Web](backend-web/.env.example)、[WebSocket](websocket/.env.example)、[Scheduler](scheduler/.env.example) 的 `.env.example` 复制为同目录下的 `.env`，已有文件保留。填写相同的数据库及 Redis 连接信息，提前创建数据库；服务间 URL 按实际地址填写。三个服务的 `STATIC_DIR` 指向同一绝对目录，Backend-Web 与 Scheduler 的 `BACKUP_DIR` 也指向同一绝对目录。MySQL 的 `max_connections` 应覆盖所有服务连接池上限并预留管理连接，单实例默认配置建议不少于 4000。
2. 为三个后端分别打开终端，进入 `backend-web`、`websocket`、`scheduler` 目录，各执行一次：

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   python -m pip install -e .
   python -m playwright install chromium
   ```

   Windows 激活命令为 `.venv\Scripts\activate.bat`（CMD）或 `.\.venv\Scripts\Activate.ps1`（PowerShell）。Linux 缺少浏览器系统依赖时，使用 `python -m playwright install --with-deps chromium`。

   Backend-Web 与 WebSocket 还需安装 Patchright 浏览器：

   ```bash
   python -m patchright install chromium
   ```

3. 在各服务终端执行 `python main.py`，先启动 Backend-Web 并等待数据库初始化成功，再启动 WebSocket 和 Scheduler。
4. 在仓库根目录打开另一个终端启动网页：

   ```bash
   cd frontend
   npm ci
   npm run dev
   ```

   默认访问 `http://127.0.0.1:9000`；后端地址不同则在 `frontend/.env.local` 配置 `VITE_BACKEND_SERVICE_URL`。

更新直接运行的源码时，在仓库根目录执行 `git pull --ff-only`；分别在三个后端的虚拟环境中重新执行依赖和浏览器安装命令，在前端目录执行 `npm ci`，再重启四个进程。有本地修改时先保存或合并修改，保留已有 `.env`。

### Docker 访问配置

Docker 前端端口仅绑定本机，默认 `FRONTEND_PORT=9000`；后端不发布宿主机端口。通过同机 Nginx / 宝塔反向代理访问，在实际代理 `location` 中配置：

```nginx
proxy_pass http://127.0.0.1:9000;
proxy_http_version 1.1;
proxy_set_header Host $host;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header X-Real-IP $remote_addr;
proxy_read_timeout 86400s;
```

代理端口与 `.env` 或 `.env.remote` 中的 `FRONTEND_PORT` 保持一致，通过配置的域名访问。公网使用时，将 `FRONTEND_PUBLIC_URL` 配置为真实访问地址；直接运行源码时还需检查 `BACKEND_WEB_PUBLIC_URL`，以确保文件和提货链接可访问。

### 返佣子系统

返佣子系统单独运行：将 [推广后端配置](promotion/backend/.env.example) 复制为同目录的 `.env` 并填写与主系统相同的数据库、Redis 及共享静态目录；在 `promotion/backend` 创建并激活虚拟环境，执行 `python -m pip install -e .` 和 `python main.py`。另开终端在 `promotion/frontend` 执行 `npm ci` 和 `npm run dev`，默认访问 `http://127.0.0.1:9001`。

### 首次登录

全新数据库初始化成功后，默认管理员账号为 `admin`，密码为 `admin123`，登录后修改密码。已有管理员账号和密码不会被重置。

## 许可证

本项目采用 [GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE) 开源协议。

**⚠️ 禁止商业用途：本项目仅供学习研究使用，严禁任何形式的商业用途。**

## 免责声明

本项目仅供技术学习和研究使用，使用者需自行承担使用风险。请遵守相关平台的使用条款和法律法规。

- 本项目不对使用本系统造成的任何后果负责
- 请勿用于违反闲鱼平台规则的行为
- 请勿用于商业用途
- 使用本系统可能存在账号风险，请谨慎使用

## 🧸 特别鸣谢

本项目参考了以下开源项目：

- **[XianYuApis](https://github.com/cv-cat/XianYuApis)** - 提供了闲鱼API接口的技术参考
- **[XianyuAutoAgent](https://github.com/shaxiu/XianyuAutoAgent)** - 提供了自动化处理的实现思路
- **[myfish](https://github.com/Kaguya233qwq/myfish)** - 提供了扫码登录的实现思路


感谢这些优秀的开源项目为本项目的开发提供了宝贵的参考和启发！

## Star History

[![Star History Chart](https://star-history.dera.page/svg?repos=zhinianboke/xianyu-auto-reply&type=Date)](https://star-history.dera.page/#zhinianboke/xianyu-auto-reply&Date)
