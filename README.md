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
| ![微信群](https://xy.zhinianboke.com/static/qrcode/wechat-group.jpg) | ![QQ群](https://xy.zhinianboke.com/static/qrcode/qq-group.jpg) | ![微信公众号](https://xy.zhinianboke.com/static/qrcode/wechat-official-group.jpg) | ![Telegram](https://xy.zhinianboke.com/static/qrcode/telegram-group.png) | ![赞赏支持](https://xy.zhinianboke.com/static/qrcode/reward-group.png) |
| 扫码加入微信交流群 | 扫码加入QQ交流群 | 关注公众号发送"最新源码"获取最新代码 | 扫码加入Telegram群 | 如果觉得好用，请作者喝杯咖啡 |

如群二维码过期，请关注公众号获取最新群链接。

---

## 功能概览

### 主系统

| 模块 | 说明 |
|------|------|
| 多账号管理 | 支持多个闲鱼账号登录、状态切换、Cookie 维护与登录续期 |
| 自动回复 | 支持文本关键词、图片关键词、默认回复、商品专属回复 |
| AI 回复 | 支持大模型上下文对话与智能回复 |
| 自动发货 | 支持卡券、虚拟商品、自动补发、发送结果记录 |
| 在线聊天 | 支持会话列表、消息收发、聊天联动 |
| 商品发布 | 支持素材库、地址库、单品发布、批量发布、发布日志 |
| 订单与评价 | 订单拉取、自动评价、求小红花、状态跟踪 |
| 商品采集与分销 | Goofish 采集、货源管理、对接记录、结算链路 |
| 通知与风控 | 支持消息通知、风控日志、系统反馈与公告管理 |

### 返佣子系统

| 模块 | 说明 |
|------|------|
| 返佣账号 | 返佣账号登录、状态管理、Cookie 维护 |
| 选品规则 | 按规则抓取候选商品并自动写入素材库 |
| 素材库 | 管理标题、图片、详情、淘口令、短链、库存、发布状态 |
| 发布规则 | 定时发布返佣商品，复用公共发布能力 |
| 删除规则 | 定时删除已发布商品 |
| 补偿任务 | 已发布商品 ID 回写、短链修复、卡券补偿等 |

## 技术栈

### 后端与自动化

| 技术 | 说明 |
|------|------|
| FastAPI | 主系统与返佣后端 API 服务 |
| SQLAlchemy 2.0 | ORM 与数据库访问 |
| MySQL 8.0 | 主数据存储 |
| Redis 7 | 缓存、会话与任务辅助 |
| Playwright | 登录、Cookie 刷新、发布等浏览器自动化 |
| APScheduler | 定时任务调度 |
| Loguru | 日志管理 |

### 前端

| 技术 | 说明 |
|------|------|
| React 18 + TypeScript | 主系统与返佣前端 |
| Vite | 开发与构建 |
| TailwindCSS | 主系统 UI 样式 |
| Zustand | 状态管理 |
| Lucide React | 图标体系 |

### 部署

| 技术 | 说明 |
|------|------|
| Docker / Docker Compose | 容器化部署 |
| Nginx | 前端静态资源与反向代理 |

## 系统要求

### 开发环境

- Python 3.11+
- Node.js 18+
- MySQL 8.0+
- Redis 6+
- Chromium / Chrome（Playwright 相关功能）

### 生产环境

- Docker 20.10+
- Docker Compose 2.0+
- 最低 2 核 CPU / 4GB 内存
- 推荐 4 核 CPU / 8GB 内存

## 项目结构

```text
xianyu-auto-reply/
├── backend-web/          # 主 Web API 服务（端口 8089）
├── websocket/            # 闲鱼连接与消息处理服务（端口 8090）
├── scheduler/            # 定时任务服务（端口 8091）
├── common/               # 主系统与返佣系统共享模块
├── frontend/             # 主系统前端（端口 9000）
├── launcher/             # Windows 桌面启动器（Nuitka 打包为 EXE）
├── promotion/
│   ├── backend/          # 返佣后端（端口 8092）
│   └── frontend/         # 返佣前端（端口 9001）
├── scripts/              # CI/CD 与工具脚本
├── docker/frontend/      # 前端 Dockerfile 与 Nginx 配置
├── docker-compose.yml    # 本地源码构建编排
├── deploy.sh             # 一键部署脚本（自动生成远程镜像版 compose）
├── deploy_remote.sh      # 远程 MySQL/Redis 一键部署脚本（自动生成 docker-compose.remote.yml）
├── update.sh             # 一键更新脚本（拉取最新远程镜像）
├── build.sh              # 本地源码全量构建脚本
├── build_frontend.sh     # 单独构建并重启 Frontend
├── build_backend_web.sh  # 单独构建并重启 Backend-Web
├── build_websocket.sh    # 单独构建并重启 WebSocket
├── build_scheduler.sh    # 单独构建并重启 Scheduler
├── EXE打包构建.bat       # Windows 桌面启动器打包脚本
├── 离线依赖打包.bat      # Windows 离线依赖打包脚本
└── README.md
```

### 服务职责

| 服务 | 默认端口 | 说明 |
|------|----------|------|
| `frontend` | 9000 | 主系统前端 |
| `backend-web` | 8089 | 主系统 API 网关、业务接口 |
| `websocket` | 8090 | 闲鱼 WebSocket、消息收发、登录与订单联动 |
| `scheduler` | 8091 | 定时任务执行器 |
| `promotion/backend` | 8092 | 返佣后端 API |
| `promotion/frontend` | 9001 | 返佣前端 |

### 架构说明

- 主系统采用多服务拆分：
  - `frontend` 负责界面与交互
  - `backend-web` 负责大部分业务 API
  - `websocket` 负责闲鱼实时连接、扫码登录、消息处理
  - `scheduler` 负责自动发货、评价、订单拉取、Cookie 刷新等定时任务
  - `common` 提供模型、数据库、自检、公共服务与工具
- 返佣子系统位于 `promotion/` 目录，前后端独立，当前不在根目录 Docker Compose 编排内
- 主系统三个后端服务都提供 `/health` 健康检查接口
- Docker 依赖链：mysql/redis → backend-web → websocket → scheduler；frontend → backend-web

## 快速开始

### 方式一：服务器一键部署（推荐）

服务器已安装 Docker 与 Docker Compose 后，直接执行一键部署脚本即可：

```bash
curl -fsSL https://xy-update.zhinianboke.com/deploy.sh | sed 's/\r$//' | bash
```

该脚本会自动完成部署所需的配置生成、镜像拉取、旧容器清理与服务启动。

更新版本，直接执行一键更新脚本即可：

```bash
curl -fsSL https://xy-update.zhinianboke.com/update.sh | sed 's/\r$//' | bash
```

### 方式二：克隆仓库部署

```bash
git clone https://github.com/zhinianboke/xianyu-auto-reply.git
cd xianyu-auto-reply
bash deploy.sh
```

- 首次运行会自动生成 `.env` 配置文件和 `docker-compose.deploy.yml`
- 从阿里云镜像仓库拉取预构建镜像并启动
- 如果检测到加密版容器会自动清理（保留数据卷）
- 部署完成后默认访问地址：
  - 前端：`http://服务器IP:9000`
  - API 文档：`http://服务器IP:8089/docs`
  - 默认账号：`admin` / `admin123`

后续更新：

```bash
bash update.sh
```

### 方式三：使用远程 MySQL / Redis 部署

当 MySQL 和 Redis 由外部（如云数据库 RDS、独立服务器或已有实例）提供时，可使用 `deploy_remote.sh`。
该脚本**不内置 mysql/redis 容器**，仅拉取并启动 4 个应用服务（frontend / backend-web / websocket / scheduler），
数据库连接信息通过 `.env.remote` 配置。与方式一相同，直接远程拉取脚本执行即可：

```bash
# 1) 首次运行：自动生成 .env.remote 后退出，提示填写远程连接信息
curl -fsSL https://xy-update.zhinianboke.com/deploy_remote.sh | sed 's/\r$//' | bash

# 2) 编辑 .env.remote，填写真实的远程地址（勿填 localhost）
#    MYSQL_HOST / REDIS_HOST 等
vim .env.remote

# 3) 再次运行：校验配置 → 自动生成 docker-compose.remote.yml → 拉取镜像 → 启动
curl -fsSL https://xy-update.zhinianboke.com/deploy_remote.sh | sed 's/\r$//' | bash
```

> 已克隆仓库的也可改用本地脚本：`bash deploy_remote.sh`（首次生成配置后退出，填好 `.env.remote` 再次执行）。

- 首次运行自动生成 `.env.remote`，每次运行自动生成 `docker-compose.remote.yml`，均不影响根目录原有的 `.env` / `docker-compose.yml` / `docker-compose.deploy.yml`
- 容器名与主套保持一致（`xianyu-backend-web` / `xianyu-websocket` / `xianyu-scheduler` / `xianyu-frontend`），与方式二/方式四属于同一套部署，二者只需选其一，不要同时启动
- 远程 MySQL 需提前创建好数据库（默认 `xianyu_data`）并授权部署机 IP 远程访问，应用启动时会自动建表与补齐字段
- 建议远程 MySQL 持久设置 `max_connect_errors=100000`；若出现错误码 1129，需在数据库服务器执行 `FLUSH HOSTS` 解除主机封锁
- 若远程库/缓存就在宿主机上，请使用 `host.docker.internal` 或宿主机内网 IP，**不要填 `localhost` / `127.0.0.1`**

### 方式四：本地源码 Docker 构建

```bash
bash build.sh rebuild
```

常用命令：

| 命令 | 说明 |
|------|------|
| `bash build.sh rebuild` | 删除旧容器与镜像，重新构建并启动 |
| `bash build.sh start` | 启动服务 |
| `bash build.sh stop` | 停止服务 |
| `bash build.sh restart` | 重启服务 |
| `bash build.sh logs` | 查看实时日志 |
| `bash build.sh status` | 查看服务状态 |

单独重建某个服务（不影响其他服务）：

```bash
bash build_frontend.sh      # 重建前端
bash build_backend_web.sh   # 重建 Backend-Web
bash build_websocket.sh     # 重建 WebSocket
bash build_scheduler.sh     # 重建 Scheduler
```

### 方式五：源码本地开发

需要把 Token / 真实鼠标滑块部署到另一台 Windows 机器时，使用单独发布的
`xianyu-remote-worker` 工程；两者没有源码或数据库依赖，本仓库通过 HTTP 客户端接入。

#### 1. 准备基础服务

可以使用本机 MySQL / Redis，也可以仅用 Docker 启动基础设施：

```bash
docker compose up -d mysql redis
```

#### 2. 创建服务配置

主系统常用 `.env` 配置示例：

```env
ENVIRONMENT=development
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=root
MYSQL_DATABASE=xianyu_data
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0
CORS_ORIGINS=*
BACKEND_WEB_PORT=8089
WEBSOCKET_PORT=8090
SCHEDULER_PORT=8091
WEBSOCKET_SERVICE_URL=http://127.0.0.1:8090
SCHEDULER_SERVICE_URL=http://127.0.0.1:8091
BACKEND_WEB_SERVICE_URL=http://127.0.0.1:8089
STATIC_DIR=static
TZ=Asia/Shanghai
```

#### 3. 启动主系统后端

```bash
# Backend-Web 服务
cd backend-web
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -e .
python -m playwright install chromium
python -m patchright install chromium
python main.py
```

```bash
# WebSocket 服务
cd websocket
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -e .
python -m playwright install chromium
python -m patchright install chromium
python main.py
```

```bash
# Scheduler 服务
cd scheduler
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -e .
python -m playwright install chromium
python main.py
```

#### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

#### 5. 启动返佣子系统

```bash
# 返佣后端
cd promotion/backend
pip install -e .
python main.py

# 返佣前端
cd promotion/frontend
npm install
npm run dev
```

## 配置说明

### 关键环境变量

| 变量 | 说明 |
|------|------|
| `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE` | MySQL 连接 |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_PASSWORD` / `REDIS_DB` | Redis 连接 |
| `JWT_SECRET_KEY` | JWT 密钥，由数据库统一托管（首次启动自动生成并持久化），无需手动配置 |
| `INTERNAL_API_TOKEN` | 服务间 `/internal` API 共享令牌，可留空；首次启动自动生成并持久化到数据库 |
| `BACKEND_WEB_PORT` / `WEBSOCKET_PORT` / `SCHEDULER_PORT` | 各服务端口 |
| `WEBSOCKET_SERVICE_URL` / `SCHEDULER_SERVICE_URL` / `BACKEND_WEB_SERVICE_URL` | 服务间调用地址 |
| `BACKEND_WEB_PUBLIC_URL` | 对外访问地址，用于生成文件 URL |
| `CORS_ORIGINS` | CORS 白名单 |
| `BROWSER_HEADLESS` | Playwright 是否无头运行 |

### 数据库与初始化

- 主系统启动时自动建表、自检、缺失字段补齐、默认数据初始化
- 默认管理员：`admin` / `admin123`
- 返佣系统启动时执行独立的数据库自检
- 返佣系统表统一使用 `fy_` 前缀
- 不依赖外键约束，关系由代码维护
- 所有时间统一使用北京时间（`Asia/Shanghai`）

### 统一响应格式

后端采用统一响应包装，业务异常也返回 HTTP 200：

```json
{
  "success": true,
  "code": 200,
  "message": "操作成功",
  "data": {}
}
```

## 构建脚本速查

| 脚本 | 平台 | 作用 |
|------|------|------|
| `deploy.sh` | Linux | 生成远程镜像版 compose 并拉取镜像启动（首次部署） |
| `deploy_remote.sh` | Linux | 使用远程 MySQL/Redis 部署，生成 `docker-compose.remote.yml` 与 `.env.remote` 并启动应用服务 |
| `update.sh` | Linux | 拉取最新远程镜像并重建应用容器（后续更新） |
| `build.sh` | Linux | 从源码全量构建所有 Docker 镜像并启动 |
| `build_frontend.sh` | Linux | 单独重建并重启 Frontend 服务 |
| `build_backend_web.sh` | Linux | 单独重建并重启 Backend-Web 服务 |
| `build_websocket.sh` | Linux | 单独重建并重启 WebSocket 服务 |
| `build_scheduler.sh` | Linux | 单独重建并重启 Scheduler 服务 |
| `EXE打包构建.bat` | Windows | 使用 Nuitka 打包桌面启动器 EXE |
| `离线依赖打包.bat` | Windows | 打包所有 Python 依赖供离线安装 |
| `scripts/Pipeline脚本-xianyu-auto-reply.groovy` | Jenkins | CI/CD 流水线，构建多架构镜像并推送到阿里云 ACR |

## 安全说明

- **JWT 认证**：主系统与返佣系统都使用 JWT 做登录态控制
- **密码存储**：密码使用哈希方式保存
- **SQL 注入防护**：数据库访问使用参数化查询
- **XSS 防护**：前端输入与展示做好校验与转义
- **CORS 控制**：生产环境应限制到明确域名

### 生产环境建议

1. 立即修改默认管理员密码
2. JWT 密钥由数据库统一托管，首次启动自动生成强随机密钥（无需手动设置）
3. 设置正确的 `BACKEND_WEB_PUBLIC_URL` 与反向代理地址
4. 为外网入口配置 HTTPS
5. 定期备份 MySQL 与静态资源目录
6. 确保 Playwright 浏览器已正确安装

## 常见问题

### 根目录 Docker Compose 没有启动返佣系统？

当前 `docker-compose.yml` 只覆盖主系统。返佣系统需要单独启动。

### 登录或发布时报浏览器缺失？

Backend-Web 和 WebSocket 需要在对应 Python 环境依次执行：
`python -m playwright install chromium`、`python -m patchright install chromium`。
Docker 环境依赖各服务 Dockerfile 内已安装的浏览器。

### Docker 部署端口冲突？

修改根目录 `.env` 中的端口配置后重新部署。

### 执行脚本报 `/bin/bash^M: 坏的解释器`？

脚本文件包含 Windows 换行符（CRLF），Linux 无法识别。解决方法：

```bash
# 方法一：用 sed 去除 \r 后执行
sed -i 's/\r$//' deploy.sh
bash deploy.sh

# 方法二：通过管道执行（推荐远程脚本使用）
curl -fsSL https://xy-update.zhinianboke.com/deploy.sh | sed 's/\r$//' | bash
```

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


## 公开账号查询接口

所有公开接口的完整 URL 格式均为：
`http(s)://<服务域名或IP>:<端口>/api/v1/...`。无需登录，使用个人设置「分销管理」中的
`secret_key` 校验。

### POST `/api/v1/external/enabled-accounts`

获取秘钥所属用户的全部闲鱼账号（包含已禁用账号）。

请求头：`Content-Type: application/json`

请求体：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `secret_key` | string | 是 | 分销秘钥，最长 128 个字符 |

```json
{
  "secret_key": "your-secret-key"
}
```

成功返回：

```json
{
  "success": true,
  "code": 200,
  "message": "查询成功",
  "data": {
    "accounts": [
      {
        "account_id": "闲鱼账号ID",
        "remark": "账号备注",
        "enabled": true,
        "status": "active",
        "status_name": "启用",
        "disable_reason": ""
      }
    ],
    "total": 1,
    "enabled_total": 1,
    "disabled_total": 0
  }
}
```

`enabled` 表示账号当前是否可用；`status` 保留账号原始状态，`status_name` 为中文状态名称。

### 外部账号 Cookie 同步

供外部系统回传账号最新 Cookie。该接口只更新 Cookie，不重启账号 WebSocket 任务。

#### POST `/api/v1/external/account-cookie/sync`

请求头：`Content-Type: application/json`

请求体：

| 参数 | 类型 | 必填 | 限制/说明 |
| --- | --- | --- | --- |
| `secret_key` | string | 是 | 分销秘钥，最长 128 个字符，必须属于目标账号所属用户 |
| `account_id` | string | 是 | 闲鱼账号 ID，最长 80 个字符 |
| `cookies` | string | 是 | 最新 Cookie 字符串，最长 16384 个字符，必须包含登录态 `unb` |

```json
{
  "secret_key": "your-secret-key",
  "account_id": "闲鱼账号ID",
  "cookies": "unb=...; _m_h5_tk=...; ..."
}
```

成功返回：

```json
{
  "success": true,
  "code": 200,
  "message": "Cookie 已更新",
  "data": null
}
```

失败时同样固定返回 HTTP `200`，并通过 `success=false`、`code` 和中文 `message`
表达业务错误。常见错误码为：`40001`（秘钥无效/用户不可用）、`40002`（账号不存在或秘钥与账号不匹配）、
`40007`（Cookie 格式或归属校验失败）、`40008`（请求参数不完整）、
`50001`（账号、秘钥或 Cookie 更新失败）。

## 公开商品发布相关接口

建议按以下顺序调用：

1. 调用公开账号查询接口获取 `account_id`。
2. 调用分类推荐接口获取 `category` 和完整 `card_list`。
3. 如需填写平台动态属性，调用分类属性接口。
4. 调用媒体上传接口上传图片/视频，取得 `media_id`。
5. 调用单品发布接口。

### 1. 分类推荐

#### POST `/api/v1/external/category/recommend`

请求头：`Content-Type: application/json`

请求体：

| 参数 | 类型 | 必填 | 限制/说明 |
| --- | --- | --- | --- |
| `secret_key` | string | 是 | 分销秘钥，最长 128 个字符 |
| `account_id` | string | 是 | 闲鱼账号 ID，最长 80 个字符，必须属于该秘钥用户 |
| `description` | string | 是 | 商品描述，最长 1500 个字符 |

```json
{
  "secret_key": "your-secret-key",
  "account_id": "闲鱼账号ID",
  "description": "全新未拆封的商品，支持官方验货，配件齐全"
}
```

成功返回：

```json
{
  "success": true,
  "code": 200,
  "message": "分类推荐成功",
  "data": {
    "candidates": [
      {
        "cat_id": "平台末级分类ID",
        "cat_name": "分类名称",
        "channel_cat_id": "频道分类ID",
        "channel_cat_name": "频道分类名称",
        "leaf_id": "叶子分类ID",
        "tb_cat_id": "淘宝分类ID",
        "path": [
          {"id": "100", "name": "一级分类"},
          {"id": "10001", "name": "末级分类"}
        ],
        "score": 0.98,
        "is_selected": false
      }
    ],
    "properties": [
      {
        "property_id": "属性ID",
        "property_name": "品牌",
        "input_word": null,
        "is_multiple": false,
        "is_decisive_property": false,
        "options": [
          {
            "property_id": "属性ID",
            "property_name": "品牌",
            "value_id": "属性值ID",
            "value_name": "品牌名称",
            "channel_cat_id": "频道分类ID",
            "tb_cat_id": "淘宝分类ID"
          }
        ]
      }
    ],
    "card_list": [],
    "account_id": "闲鱼账号ID"
  }
}
```

`card_list` 是平台返回的完整属性卡片数组。调用分类属性接口时必须原样传回该数组；
`candidates` 中的分类对象可直接作为后续接口的 `category`。

### 2. 获取分类动态属性

#### POST `/api/v1/external/category/properties`

请求头：`Content-Type: application/json`

请求体：

| 参数 | 类型 | 必填 | 限制/说明 |
| --- | --- | --- | --- |
| `secret_key` | string | 是 | 分销秘钥，最长 128 个字符 |
| `account_id` | string | 是 | 闲鱼账号 ID，最长 80 个字符 |
| `description` | string | 是 | 商品描述，最长 1500 个字符 |
| `category` | object | 是 | 分类推荐接口 `data.candidates` 中选中的分类对象；至少提供 `cat_id`、`cat_name`、`channel_cat_id`、`tb_cat_id` 之一 |
| `card_list` | object[] | 是 | 分类推荐接口返回的完整 `data.card_list`，最多 100 条 |

```json
{
  "secret_key": "your-secret-key",
  "account_id": "闲鱼账号ID",
  "description": "全新未拆封的商品，支持官方验货，配件齐全",
  "category": {
    "channel_cat_id": "频道分类ID",
    "channel_cat_name": "频道分类名称",
    "cat_name": "末级分类名称",
    "tb_cat_id": "淘宝分类ID"
  },
  "card_list": []
}
```

成功返回结构与分类推荐接口相同：`data.candidates`、`data.properties`、
`data.card_list`、`data.account_id`；成功消息为「分类属性获取成功」。

### 3. 上传发布媒体

#### POST `/api/v1/external/publish/media`

请求类型：`multipart/form-data`。

| 表单参数 | 类型 | 必填 | 限制/说明 |
| --- | --- | --- | --- |
| `secret_key` | string | 是 | 分销秘钥，最长 128 个字符 |
| `account_id` | string | 是 | 闲鱼账号 ID，最长 80 个字符 |
| `media_type` | string | 是 | `image` 商品图片、`spec_image` 规格图片或 `video` 商品视频 |
| `file` | file | 是 | 要上传的媒体文件 |

```bash
curl -X POST "http(s)://<服务域名或IP>:<端口>/api/v1/external/publish/media" \
  -F "secret_key=your-secret-key" \
  -F "account_id=闲鱼账号ID" \
  -F "media_type=image" \
  -F "file=@/path/to/image.jpg"
```

成功返回：

```json
{
  "success": true,
  "code": 200,
  "message": "媒体上传成功",
  "data": {
    "media_id": "image_0123456789abcdef0123456789abcdef",
    "media_type": "image",
    "name": "image_0123456789abcdef0123456789abcdef.jpg",
    "size": 123456
  }
}
```

`media_id` 只能在生成它的同一个 `account_id` 下的单品发布请求中使用，不能跨账号使用，
也不能把本地文件路径直接传给单品发布接口。

### 4. 发布单个商品

#### POST `/api/v1/external/publish/single`

请求头：`Content-Type: application/json`

请求体：

| 参数 | 类型 | 必填 | 默认值 | 限制/说明 |
| --- | --- | --- | --- | --- |
| `secret_key` | string | 是 | - | 分销秘钥，最长 128 个字符 |
| `account_id` | string | 是 | - | 闲鱼账号 ID，最长 80 个字符 |
| `title` | string | 是 | - | 商品标题，最长 200 个字符 |
| `description` | string | 是 | - | 商品描述，最长 1500 个字符 |
| `price` | number | 是 | - | 商品售价，必须大于 0 |
| `original_price` | number | 否 | - | 原价，必须大于 0 |
| `image_media_ids` | string[] | 是 | - | 图片媒体 ID，至少 1 个、最多 9 个，必须为 `image` 类型 |
| `video_media_ids` | string[] | 否 | `[]` | 最多 3 个，必须为 `video` 类型 |
| `platform_category_id` | string | 否 | - | 平台末级分类 ID |
| `platform_category_name` | string | 否 | - | 平台分类名称 |
| `platform_channel_category_id` | string | 否 | - | 频道分类 ID |
| `platform_channel_category_name` | string | 否 | - | 频道分类名称 |
| `platform_leaf_id` | string | 否 | - | 叶子分类 ID |
| `platform_tb_category_id` | string | 否 | - | 淘宝分类 ID |
| `platform_attributes` | object[] | 否 | `[]` | 平台属性，最多 30 条 |
| `quantity` | integer | 否 | `1` | 库存数量，1～999999 |
| `specifications` | object[] | 否 | `[]` | 最多 2 个规格维度 |
| `sku_rows` | object[] | 否 | `[]` | 最多 200 条 SKU |
| `address` | string | 是 | - | 宝贝所在地，最长 200 个字符；需传外部系统已选择的地址关键词 |
| `address_expected_text` | string | 否 | - | 地址预期展示文本，最长 200 个字符 |
| `delivery_method` | string | 否 | `express` | `express` 快递或 `pickup` 自提 |
| `shipping_method` | string | 否 | `free` | `free` 包邮、`distance` 按距离计费、`fixed` 一口价、`template` 运费模板、`none` 无需邮寄 |
| `postage` | number | 否 | `0` | `shipping_method=fixed` 时的运费，0～1000 元 |
| `support_pickup` | boolean | 否 | `false` | 是否支持自提；与 `shipping_method` 独立 |

`platform_attributes` 每项可传：`property_id`（最长 64）、`property_name`（最长 100）、
`value_id`（最长 64）、`value_name`（最长 200）、`text`（最长 200）、
`properties`（最长 500）。

`specifications` 每项包含 `name`（必填，最长 100）、`support_image`（默认 `false`）和
`values`（最多 50 项）；`values` 每项包含 `name`（必填，最长 100）及可选的
`image_media_id`（必须是同账号的 `spec_image` 媒体 ID）。

`sku_rows` 每项包含 `specs`（规格名到规格值的对象，最多 4 个键）、`price`（大于 0）、
`stock`（0～999999）。

请求示例：

```json
{
  "secret_key": "your-secret-key",
  "account_id": "闲鱼账号ID",
  "title": "全新商品标题",
  "description": "商品详细描述",
  "price": 99.9,
  "original_price": 129.9,
  "image_media_ids": ["image_0123456789abcdef0123456789abcdef"],
  "video_media_ids": [],
  "platform_category_id": "平台分类ID",
  "platform_category_name": "平台分类名称",
  "platform_channel_category_id": "频道分类ID",
  "platform_channel_category_name": "频道分类名称",
  "platform_leaf_id": "叶子分类ID",
  "platform_tb_category_id": "淘宝分类ID",
  "platform_attributes": [],
  "quantity": 1,
  "specifications": [],
  "sku_rows": [],
  "address": "上海市",
  "address_expected_text": "上海",
  "delivery_method": "express",
  "shipping_method": "free",
  "postage": 0,
  "support_pickup": false
}
```

成功返回：

```json
{
  "success": true,
  "code": 200,
  "message": "商品发布成功",
  "data": {
    "item_url": "商品详情链接",
    "item_id": "平台商品ID",
    "log_id": 123,
    "sync_status": "success",
    "sync_message": "已自动获取商品并入库 1 个商品",
    "sync_total_count": 1,
    "sync_saved_count": 1
  }
}
```

发布失败时仍返回 HTTP `200`，`success=false`、`code=40009`；媒体不存在、类型不匹配或
媒体不属于目标账号时返回 `40007`。

### 商品发布相关接口常见错误码

| `code` | 含义 |
| --- | --- |
| `40001` | 分销秘钥为空、超长或不存在 |
| `40002` | 闲鱼账号 ID 为空、超长、不存在或不属于该秘钥用户 |
| `40004` | 商品描述为空或超长（分类接口） |
| `40005` | 分类推荐/动态属性获取失败 |
| `40006` | 分类选择数据缺失、`category`/`card_list` 格式错误 |
| `40007` | 媒体参数或媒体文件错误 |
| `40008` | 发布请求参数格式错误或必填字段为空 |
| `40009` | 商品发布执行失败 |
| `50001` | 服务端查询或处理失败，请稍后重试 |

## 公开订单查询接口

接口地址：`/api/v1/external/orders`，完整 URL 格式为
`http(s)://<服务域名或IP>:<端口>/api/v1/external/orders`。无需登录，使用用户分销秘钥校验，只返回该秘钥所属用户的订单。

### 1. POST JSON 调用

```http
POST /api/v1/external/orders
Content-Type: application/json
```

请求体：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `secret_key` | string | 是 | - | 个人设置-分销管理中的分销秘钥，最长 128 个字符 |
| `item_ids` | string[] | 否 | `[]` | 商品 ID 数组，最多 100 个；不传表示查询该秘钥所属用户的全部订单 |
| `item_id` | string | 否 | - | 单个或多个商品 ID，多个 ID 用英文逗号分隔；也可与 `item_ids` 同时传 |
| `order_no` | string | 否 | - | 订单号，精确查询，最长 64 个字符 |
| `page` | integer | 否 | `1` | 页码，从 1 开始 |
| `page_size` | integer | 否 | `20` | 每页数量，取值 1～100 |

示例：

```json
{
  "secret_key": "your-secret-key",
  "item_ids": ["商品ID1", "商品ID2"],
  "order_no": "订单号（可选）",
  "page": 1,
  "page_size": 20
}
```

### 2. GET 查询参数调用

```http
GET /api/v1/external/orders?secret_key=your-secret-key&page=1&page_size=20
```

GET 参数与 POST 参数含义相同。商品 ID 支持以下两种传法：

```http
# 重复传 item_id
GET /api/v1/external/orders?secret_key=your-secret-key&item_id=商品ID1&item_id=商品ID2&page=1&page_size=20

# item_ids 使用逗号分隔
GET /api/v1/external/orders?secret_key=your-secret-key&item_ids=商品ID1,商品ID2&page=1&page_size=20
```

`order_no` 可以单独传，也可以和商品 ID、分页参数一起传；多个筛选条件同时传入时按“同时满足”查询。

### 3. 成功返回

HTTP 状态码固定为 `200`，业务结果通过响应体判断：

```json
{
  "success": true,
  "code": 200,
  "message": "订单查询成功",
  "data": {
    "list": [
      {
        "id": "订单数据库ID",
        "order_no": "订单号",
        "order_id": "订单号（与 order_no 相同）",
        "item_id": "商品ID",
        "item_title": "商品标题",
        "status": "订单状态（小写）",
        "buyer_id": "买家ID",
        "buyer_nick": "买家昵称",
        "buyer_fish_nick": "买家闲鱼昵称",
        "chat_id": "聊天会话ID",
        "spec_name": "规格名称",
        "spec_value": "规格值",
        "sku_info": "规格名称 / 规格值",
        "quantity": 1,
        "amount": "99.00",
        "currency": "CNY",
        "account_id": "闲鱼账号ID",
        "cookie_id": "闲鱼账号ID（与 account_id 相同）",
        "account_name": "闲鱼账号名称",
        "is_bargain": false,
        "is_rated": false,
        "is_red_flower": false,
        "is_unregistered": false,
        "unregister_error_reason": "",
        "receiver_name": "收货人",
        "receiver_phone": "收货电话",
        "receiver_address": "收货地址",
        "delivery_method": "auto",
        "delivery_content": "发货内容",
        "delivery_fail_reason": "",
        "card_only_delivered": false,
        "delivery_send_status": "success",
        "delivery_send_fail_reason": null,
        "source": "数据来源",
        "placed_at": "2026-01-01T12:00:00+08:00",
        "synced_at": "2026-01-01T12:01:00+08:00",
        "created_at": "2026-01-01T12:01:00+08:00",
        "updated_at": "2026-01-01T12:01:00+08:00"
      }
    ],
    "orders": [
      {
        "id": "订单数据库ID",
        "order_no": "订单号",
        "order_id": "订单号（与 order_no 相同）",
        "item_id": "商品ID",
        "item_title": "商品标题",
        "status": "订单状态（小写）",
        "buyer_id": "买家ID",
        "buyer_nick": "买家昵称",
        "buyer_fish_nick": "买家闲鱼昵称",
        "chat_id": "聊天会话ID",
        "spec_name": "规格名称",
        "spec_value": "规格值",
        "sku_info": "规格名称 / 规格值",
        "quantity": 1,
        "amount": "99.00",
        "currency": "CNY",
        "account_id": "闲鱼账号ID",
        "cookie_id": "闲鱼账号ID（与 account_id 相同）",
        "account_name": "闲鱼账号名称",
        "is_bargain": false,
        "is_rated": false,
        "is_red_flower": false,
        "is_unregistered": false,
        "unregister_error_reason": "",
        "receiver_name": "收货人",
        "receiver_phone": "收货电话",
        "receiver_address": "收货地址",
        "delivery_method": "auto",
        "delivery_content": "发货内容",
        "delivery_fail_reason": "",
        "card_only_delivered": false,
        "delivery_send_status": "success",
        "delivery_send_fail_reason": null,
        "source": "数据来源",
        "placed_at": "2026-01-01T12:00:00+08:00",
        "synced_at": "2026-01-01T12:01:00+08:00",
        "created_at": "2026-01-01T12:01:00+08:00",
        "updated_at": "2026-01-01T12:01:00+08:00"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "total_pages": 1
  }
}
```

`orders` 与 `list` 返回相同的订单数组，保留该字段用于兼容不同调用方。无匹配订单时，`list` 和 `orders` 为空数组，`total` 为 `0`，`total_pages` 为 `0`。没有对应自动发货日志时，`delivery_send_status` 和 `delivery_send_fail_reason` 为 `null`；没有值的普通文本字段返回空字符串，时间字段可能为 `null`。

### 4. 失败返回

失败时同样返回 HTTP `200`：

```json
{
  "success": false,
  "code": 40001,
  "message": "秘钥不存在",
  "data": null
}
```

常见业务码：

| `code` | 含义 |
| --- | --- |
| `40001` | 秘钥为空、长度超限、秘钥不存在或对应用户不可用 |
| `40008` | 请求参数格式错误（如商品 ID 为空/超过 100 个、分页参数非法等） |
| `50001` | 订单信息查询失败，请稍后重试 |

## 公开消息日志查询接口

接口地址：`/api/v1/external/message-logs`，完整 URL 格式为
`http(s)://<服务域名或IP>:<端口>/api/v1/external/message-logs`。无需登录，使用分销秘钥校验，只返回该秘钥所属用户指定商品的消息日志。

### POST JSON

```http
POST /api/v1/external/message-logs
Content-Type: application/json
```

```json
{
  "secret_key": "your-secret-key",
  "item_id": "商品ID",
  "message_type": "auto_reply",
  "page": 1,
  "page_size": 20
}
```

### GET 查询参数

```http
GET /api/v1/external/message-logs?secret_key=your-secret-key&item_id=商品ID&message_type=auto_reply&page=1&page_size=20
```

参数说明：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `secret_key` | string | 是 | - | 分销秘钥，最长 128 个字符 |
| `item_id` | string | 是 | - | 商品 ID，最长 64 个字符，精确匹配 |
| `message_type` | string | 否 | `auto_reply` | `auto_reply` 自动回复，`auto_delivery` 自动发货 |
| `page` | integer | 否 | `1` | 页码，从 1 开始 |
| `page_size` | integer | 否 | `20` | 每页数量，取值 1～100 |

成功返回：

```json
{
  "success": true,
  "code": 200,
  "message": "消息日志查询成功",
  "data": {
    "list": [
      {
        "id": 1,
        "account_id": "闲鱼账号ID",
        "account_name": "账号名称",
        "chat_id": "聊天会话ID",
        "item_id": "商品ID",
        "item_title": "商品标题",
        "order_no": "订单号",
        "source_message_id": "源消息ID",
        "sender_user_id": "发送方用户ID",
        "sender_user_name": "发送方昵称",
        "source_message": "收到的消息",
        "source_message_time": "2026-01-01T12:00:00+08:00",
        "process_status": "success",
        "decision_reason": "reply_sent",
        "reply_strategy": "keyword",
        "reply_mode": "text",
        "matched_keyword": "关键词",
        "matched_rule_type": "keyword_item",
        "default_reply_scope": "item",
        "default_reply_once": false,
        "ai_model_name": null,
        "ai_provider_name": null,
        "reply_text": "回复内容",
        "reply_image_url": null,
        "error_message": null,
        "send_status": "success",
        "send_fail_reason": null,
        "created_at": "2026-01-01T12:00:01+08:00",
        "updated_at": "2026-01-01T12:00:01+08:00"
      }
    ],
    "logs": [
      {
        "id": 1,
        "account_id": "闲鱼账号ID",
        "account_name": "账号名称",
        "chat_id": "聊天会话ID",
        "item_id": "商品ID",
        "item_title": "商品标题",
        "order_no": "订单号",
        "source_message_id": "源消息ID",
        "sender_user_id": "发送方用户ID",
        "sender_user_name": "发送方昵称",
        "source_message": "收到的消息",
        "source_message_time": "2026-01-01T12:00:00+08:00",
        "process_status": "success",
        "decision_reason": "reply_sent",
        "reply_strategy": "keyword",
        "reply_mode": "text",
        "matched_keyword": "关键词",
        "matched_rule_type": "keyword_item",
        "default_reply_scope": "item",
        "default_reply_once": false,
        "ai_model_name": null,
        "ai_provider_name": null,
        "reply_text": "回复内容",
        "reply_image_url": null,
        "error_message": null,
        "send_status": "success",
        "send_fail_reason": null,
        "created_at": "2026-01-01T12:00:01+08:00",
        "updated_at": "2026-01-01T12:00:01+08:00"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20,
    "total_pages": 1
  }
}
```

`logs` 与 `list` 返回相同的日志数组。无匹配日志时，`list`、`logs` 为空数组，`total` 和 `total_pages` 为 `0`。失败时也返回 HTTP `200`，例如：

```json
{
  "success": false,
  "code": 40008,
  "message": "商品ID不能为空",
  "data": null
}
```

## Star History

[![Star History Chart](https://star-history.dera.page/svg?repos=zhinianboke/xianyu-auto-reply&type=Date)](https://star-history.dera.page/#zhinianboke/xianyu-auto-reply&Date)

## 移动端 App (xianyu-mobile)

本仓库包含一个 Android 移动端客户端，位于 `xianyu-mobile/` 目录。

- 基于 Expo SDK 57 + React Native 0.86.2 + React 19
- 50+ 页面，4 大 Tab（消息/订单/商品/我的）
- 蓝白冷色系设计系统，13 个自研 UI 组件
- 多类型卡券、AI 上架、左滑操作、条形图可视化
- 与本后端完全解耦，用户自托管服务器即可使用
- 支持 OpenAPI 契约驱动的类型安全 API 调用

详见 [xianyu-mobile/README.md](xianyu-mobile/README.md)。

![我的页面](xianyu-mobile/docs/screenshots/mine.png)
