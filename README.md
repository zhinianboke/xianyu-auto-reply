# 🐟 闲鱼自动回复系统

[![GitHub](https://img.shields.io/badge/GitHub-zhinianboke%2Fxianyu--auto--reply-blue?logo=github)](https://github.com/zhinianboke/xianyu-auto-reply)
[![Docker](https://img.shields.io/badge/Docker-一键部署-blue?logo=docker)](https://github.com/zhinianboke/xianyu-auto-reply#-快速开始)
[![Python](https://img.shields.io/badge/Python-3.11+-green?logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-仅供学习-red.svg)](#️-版权声明与使用条款)

> **⚠️ 重要提示：本项目仅供学习研究使用，严禁商业用途！使用前请仔细阅读[版权声明](#️-版权声明与使用条款)。**

一个功能完整的闲鱼自动回复和管理系统，支持多用户、多账号管理，具备智能回复、自动发货、自动确认发货、商品管理等企业级功能。

## ✨ 核心特性

### 🔐 多用户系统
- **用户注册登录** - 支持邮箱验证码注册，图形验证码保护
- **数据完全隔离** - 每个用户的数据独立存储，互不干扰
- **权限管理** - 严格的用户权限控制和JWT认证
- **安全保护** - 防暴力破解、会话管理、安全日志

### 📱 多账号管理
- **无限账号支持** - 每个用户可管理多个闲鱼账号
- **独立运行** - 每个账号独立监控，互不影响
- **实时状态** - 账号连接状态实时监控
- **批量操作** - 支持批量启动、停止账号任务

### 🤖 智能回复系统
- **关键词匹配** - 支持精确关键词匹配回复
- **商品专用回复** - 支持为特定商品设置专用关键词回复
- **通用关键词** - 支持全局通用关键词，适用于所有商品
- **批量导入导出** - 支持Excel格式的关键词批量导入导出
- **AI智能回复** - 集成OpenAI API，支持上下文理解
- **变量替换** - 回复内容支持动态变量（用户名、商品信息等）
- **优先级策略** - 商品专用关键词 > 通用关键词 > AI回复

### 🚚 自动发货功能
- **智能匹配** - 基于商品信息自动匹配发货规则
- **多规格支持** - 支持同一商品的不同规格自动匹配对应卡券
- **精确匹配+兜底机制** - 优先精确匹配规格，失败时自动降级到普通卡券
- **延时发货** - 支持设置发货延时时间（0-3600秒）
- **多种触发** - 支持付款消息、小刀消息等多种触发条件
- **防重复发货** - 智能防重复机制，避免重复发货
- **多种发货方式** - 支持固定文字、批量数据、API调用等发货方式
- **自动确认发货** - 检测到付款后自动调用闲鱼API确认发货
- **防重复确认** - 智能防重复确认机制，避免重复API调用
- **发货统计** - 完整的发货记录和统计功能

### 🛍️ 商品管理
- **自动收集** - 消息触发时自动收集商品信息
- **API获取** - 通过闲鱼API获取完整商品详情
- **多规格支持** - 支持多规格商品的规格信息管理
- **批量管理** - 支持批量查看、编辑、切换多规格状态
- **智能去重** - 自动去重，避免重复存储

### 🔍 商品搜索功能
- **真实数据获取** - 基于Playwright技术获取真实闲鱼商品数据
- **智能排序** - 按"人想要"数量自动倒序排列
- **多页搜索** - 支持一次性获取多页商品数据
- **前端分页** - 灵活的前端分页显示
- **商品详情** - 支持查看完整商品详情信息

### 📊 系统监控
- **实时日志** - 完整的操作日志记录和查看
- **性能监控** - 系统资源使用情况监控
- **健康检查** - 服务状态健康检查

### 📁 数据管理
- **Excel导入导出** - 支持关键词数据的Excel格式导入导出
- **模板生成** - 自动生成包含示例数据的导入模板
- **批量操作** - 支持批量添加、更新关键词数据
- **数据验证** - 导入时自动验证数据格式和重复性
- **多规格卡券管理** - 支持创建和管理多规格卡券
- **发货规则管理** - 支持多规格发货规则的创建和管理
- **数据备份** - 自动数据备份和恢复

## 📁 项目结构

<details>
<summary>点击展开查看详细项目结构</summary>

```
xianyu-auto-reply/
├── 📄 核心文件
│   ├── Start.py                    # 项目启动入口，初始化所有服务
│   ├── XianyuAutoAsync.py         # 闲鱼WebSocket连接和消息处理核心
│   ├── reply_server.py            # FastAPI Web服务器和完整API接口
│   ├── db_manager.py              # SQLite数据库管理，支持多用户数据隔离
│   ├── cookie_manager.py          # 多账号Cookie管理和任务调度
│   ├── ai_reply_engine.py         # AI智能回复引擎，支持多种AI模型
│   ├── file_log_collector.py      # 实时日志收集和管理系统
│   ├── config.py                  # 全局配置文件管理器
│   └── secure_confirm_ultra.py    # 自动确认发货模块（多层加密保护）
├── 🛠️ 工具模块
│   └── utils/
│       ├── xianyu_utils.py        # 闲鱼API工具函数（加密、签名、解析）
│       ├── message_utils.py       # 消息格式化和处理工具
│       ├── ws_utils.py            # WebSocket客户端封装
│       ├── qr_login.py            # 二维码登录功能
│       ├── item_search.py         # 商品搜索功能（基于Playwright）
│       └── order_detail_fetcher.py # 订单详情获取工具
├── 🌐 前端界面
│   └── static/
│       ├── index.html             # 主管理界面（账号管理、系统监控）
│       ├── login.html             # 用户登录页面
│       ├── register.html          # 用户注册页面（邮箱验证）
│       ├── user_management.html   # 用户管理页面（管理员功能）
│       ├── data_management.html   # 数据管理页面（导入导出）
│       ├── log_management.html    # 日志管理页面（实时日志查看）
│       ├── item_search.html       # 商品搜索页面（真实数据获取）
│       ├── xianyu_js_version_2.js # 闲鱼JavaScript工具库
│       └── lib/                   # 前端依赖库（Bootstrap等）
├── 🐳 Docker部署
│   ├── Dockerfile                 # Docker镜像构建文件
│   ├── docker-compose.yml        # Docker Compose一键部署配置
│   ├── docker-deploy.sh          # Docker部署管理脚本
│   └── nginx/                    # Nginx反向代理配置
├── 📋 配置文件
│   ├── global_config.yml         # 全局配置文件（WebSocket、API等）
│   ├── requirements.txt          # Python依赖包列表
│   └── README.md                 # 项目说明文档
└── 📊 数据目录
    ├── xianyu_data.db            # SQLite数据库文件
    ├── logs/                     # 按日期分割的日志文件
    ├── backups/                  # 数据备份文件
    └── realtime.log              # 实时日志文件
```

</details>

## 🚀 快速开始

### 方式一：Docker 一键部署（最简单）

```bash
# 创建数据目录
mkdir -p xianyu-auto-reply

# 一键启动容器
docker run -d \
  -p 8080:8080 \
  -v $PWD/xianyu-auto-reply/:/app/data/ \
  --name xianyu-auto-reply \
  --privileged=true \
  registry.cn-shanghai.aliyuncs.com/zhinian-software/xianyu-auto-reply:1.0

# 访问系统
# http://localhost:8080
```

### 方式二：Docker Compose 部署（推荐）

```bash
# 1. 克隆项目
git clone https://github.com/zhinianboke/xianyu-auto-reply.git
cd xianyu-auto-reply

# 2. 一键部署
./docker-deploy.sh

# 3. 访问系统
# http://localhost:8080
```

### 方式三：本地部署（开发环境）

```bash
# 1. 克隆项目
git clone https://github.com/zhinianboke/xianyu-auto-reply.git
cd xianyu-auto-reply

# 2. 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate  # Linux/macOS
# 或 venv\Scripts\activate  # Windows

# 3. 安装Python依赖
pip install --upgrade pip
pip install -r requirements.txt

# 4. 安装Playwright浏览器
playwright install chromium
playwright install-deps chromium  # Linux需要

# 5. 启动系统
python Start.py

# 6. 访问系统
# http://localhost:8080
```

### 📋 环境要求

- **Python**: 3.11+
- **Node.js**: 16+ (用于JavaScript执行)
- **系统**: Windows/Linux/macOS
- **内存**: 建议2GB+
- **存储**: 建议10GB+
- **Docker**: 20.10+ (Docker部署)
- **Docker Compose**: 2.0+ (Docker部署)

### 🌐 访问系统

部署完成后，您可以通过以下方式访问系统：

- **Web管理界面**：http://localhost:8080
- **默认管理员账号**：
  - 用户名：`admin`
  - 密码：`admin123`
- **API文档**：http://localhost:8080/docs
- **健康检查**：http://localhost:8080/health

> ⚠️ **安全提示**：首次登录后请立即修改默认密码！

### 🔧 Docker部署管理

使用 `docker-deploy.sh` 脚本可以方便地管理Docker部署：

```bash
# 查看所有可用命令
./docker-deploy.sh help

# 初始化配置
./docker-deploy.sh init

# 构建镜像
./docker-deploy.sh build

# 启动服务
./docker-deploy.sh start

# 启动包含Nginx的完整服务
./docker-deploy.sh start with-nginx

# 查看服务状态
./docker-deploy.sh status

# 查看实时日志
./docker-deploy.sh logs

# 备份数据
./docker-deploy.sh backup

# 更新部署
./docker-deploy.sh update

# 停止服务
./docker-deploy.sh stop

# 重启服务
./docker-deploy.sh restart

# 清理环境
./docker-deploy.sh cleanup
```

### 🛠️ 故障排除

**常见问题及解决方案**：

1. **Docker未运行**
   ```bash
   # 启动Docker Desktop或Docker服务
   sudo systemctl start docker  # Linux
   ```

2. **端口冲突**
   ```bash
   # 修改.env文件中的WEB_PORT
   WEB_PORT=8081
   ```

3. **权限问题**
   ```bash
   # 确保数据目录有正确权限
   sudo chown -R $USER:$USER ./data ./logs ./backups
   ```

4. **内存不足**
   ```bash
   # 调整.env文件中的资源限制
   MEMORY_LIMIT=1024
   CPU_LIMIT=1.0
   ```

5. **Playwright浏览器安装失败**
   ```bash
   # 手动安装浏览器
   playwright install chromium --with-deps
   ```
- **权限问题**：Linux系统下使用 `sudo ./docker-deploy.sh`

### 方式三：本地部署

```bash
# 1. 克隆项目
git clone https://github.com/zhinianboke/xianyu-auto-reply.git
cd xianyu-auto-reply

# 2. 安装依赖
pip install -r requirements.txt

# 3. 安装Playwright浏览器（商品搜索功能需要）
playwright install chromium

# 4. 启动系统
python Start.py

# 5. 访问系统
# http://localhost:8080
```

### 🐳 Docker 部署说明

#### 一键部署特点
- **无需配置** - 使用预构建镜像，开箱即用
- **数据持久化** - 自动挂载数据目录，数据不丢失
- **快速启动** - 30秒内完成部署
- **生产就绪** - 包含所有依赖和优化配置

#### 容器管理命令
```bash
# 查看容器状态
docker ps

# 查看容器日志
docker logs -f xianyu-auto-reply

# 停止容器
docker stop xianyu-auto-reply

# 重启容器
docker restart xianyu-auto-reply

# 删除容器
docker rm -f xianyu-auto-reply
```

## 📋 系统使用

### 1. 用户注册
- 访问 `http://localhost:8080/register.html`
- 填写用户信息，完成邮箱验证
- 输入图形验证码完成注册

### 2. 添加闲鱼账号
- 登录系统后进入主界面
- 点击"添加新账号"
- 输入账号ID和完整的Cookie值
- 系统自动启动账号监控任务

### 3. 配置自动回复
- **关键词回复**：设置关键词和对应回复内容
- **AI回复**：配置OpenAI API密钥启用智能回复
- **默认回复**：设置未匹配时的默认回复

### 4. 设置自动发货
- 添加发货规则，设置商品关键词和发货内容
- 支持文本内容和卡密文件两种发货方式
- 系统检测到付款消息时自动确认发货并自动发货

### 5. 使用商品搜索功能
- 访问商品搜索页面（需要登录）
- 输入搜索关键词和查询页数
- 系统自动获取真实闲鱼商品数据
- 商品按"人想要"数量自动排序
- 支持查看商品详情和跳转到闲鱼页面

## 🏗️ 系统架构

```mermaid
graph TD
    A["Web界面 (FastAPI)<br/>用户管理 + 功能界面"] --> B["CookieManager<br/>多账号任务管理"]
    B --> C["XianyuLive (多实例)<br/>WebSocket连接 + 消息处理"]
    C --> D["SQLite数据库<br/>用户数据 + 商品信息 + 配置数据"]
```

## ✨ 核心功能特性

### 🚀 自动回复系统
- **智能关键词匹配** - 支持精确匹配和模糊匹配，灵活配置回复规则
- **AI智能回复** - 集成多种AI模型（通义千问、GPT等），智能理解用户意图
- **多账号管理** - 支持同时管理多个闲鱼账号，独立配置和运行
- **实时消息处理** - WebSocket长连接，毫秒级响应用户消息
- **自定义回复模板** - 支持占位符和动态内容，个性化回复体验

### 🛒 自动发货系统
- **智能订单识别** - 自动识别虚拟商品订单，精准匹配发货规则
- **多重安全验证** - 超级加密保护，防止误操作和数据泄露
- **批量处理能力** - 支持批量确认发货，提高处理效率
- **异常处理机制** - 完善的错误处理和重试机制，确保发货成功
- **多渠道通知** - 支持QQ、钉钉、邮件等多种发货通知方式

### 👥 多用户系统
- **用户注册登录** - 支持邮箱验证和图形验证码，安全可靠
- **权限管理** - 管理员和普通用户权限分离，精细化权限控制
- **数据隔离** - 每个用户的数据完全隔离，保护隐私安全
- **会话管理** - JWT Token认证，支持自动续期和安全登出

### 📊 数据管理
- **商品信息管理** - 自动获取和同步商品信息，实时更新状态
- **订单数据统计** - 详细的订单数据分析和可视化图表
- **关键词管理** - 灵活的关键词配置，支持正则表达式
- **数据导入导出** - 支持Excel格式的批量数据操作
- **自动备份** - 定期自动备份重要数据，防止数据丢失

### 🔍 商品搜索
- **真实数据获取** - 基于Playwright技术，获取真实闲鱼商品数据
- **多页搜索** - 支持分页搜索和批量获取，无限制数据采集
- **数据可视化** - 美观的商品展示界面，支持排序和筛选
- **搜索历史** - 保存搜索历史和结果，方便数据分析

### 📱 通知系统
- **多渠道支持** - QQ、钉钉、邮件、微信、Telegram等6种通知方式
- **智能配置** - 可视化配置界面，支持复杂参数和加密设置
- **实时推送** - 重要事件实时通知，及时了解系统状态
- **通知模板** - 自定义通知内容和格式，个性化消息推送

### 🔐 安全特性
- **Cookie安全管理** - 加密存储用户凭证，定期自动刷新
- **Token自动刷新** - 智能检测和刷新过期Token，保持连接稳定
- **操作日志** - 详细记录所有操作日志，支持审计和追踪
- **异常监控** - 实时监控系统异常和错误，主动预警

### 🎨 用户界面
- **现代化设计** - 基于Bootstrap 5的响应式界面，美观易用
- **多主题支持** - 支持明暗主题切换，个性化界面体验
- **移动端适配** - 完美适配手机和平板设备，随时随地管理
- **实时更新** - 界面数据实时更新，无需手动刷新

## 📁 核心文件功能说明

### 🚀 启动和核心模块
- **`Start.py`** - 项目启动入口，初始化所有服务和组件
- **`XianyuAutoAsync.py`** - 闲鱼WebSocket连接核心，处理消息收发和自动回复
- **`reply_server.py`** - FastAPI Web服务器，提供管理界面和API接口
- **`cookie_manager.py`** - 多账号Cookie管理，负责账号任务的启动和停止

### 🗄️ 数据和配置管理
- **`db_manager.py`** - SQLite数据库管理，处理用户数据、商品信息、关键词等
- **`config.py`** - 配置文件管理，加载和管理全局配置
- **`global_config.yml`** - 全局配置文件，包含所有系统配置项

### 🤖 智能功能模块
- **`ai_reply_engine.py`** - AI智能回复引擎，支持多种AI模型
- **`secure_confirm_ultra.py`** - 自动确认发货模块（超级加密保护）
- **`file_log_collector.py`** - 日志收集和管理，提供实时日志查看

### 🛠️ 工具模块
- **`utils/xianyu_utils.py`** - 闲鱼API工具函数，包含加密解密、签名生成等
- **`utils/message_utils.py`** - 消息格式化工具
- **`utils/ws_utils.py`** - WebSocket客户端工具
- **`utils/item_search.py`** - 商品搜索功能，基于Playwright技术

### 🌐 前端界面
- **`static/index.html`** - 主管理界面，账号管理和系统监控
- **`static/login.html`** - 用户登录页面
- **`static/register.html`** - 用户注册页面，支持邮箱验证
- **`static/user_management.html`** - 用户管理页面（管理员功能）
- **`static/data_management.html`** - 数据管理页面，关键词导入导出
- **`static/log_management.html`** - 日志管理页面，实时日志查看
- **`static/item_search.html`** - 商品搜索页面，获取真实闲鱼数据

### 🐳 部署配置
- **`Dockerfile`** - Docker镜像构建文件，包含完整运行环境
- **`docker-compose.yml`** - Docker Compose配置，支持一键部署
- **`docker-deploy.sh`** - Docker部署脚本，提供完整的部署管理功能
- **`.env`** - 环境变量配置文件，包含所有可配置项
- **`requirements.txt`** - Python依赖包列表

## ⚙️ 配置说明

### 管理员密码配置

**重要**：为了系统安全，强烈建议修改默认管理员密码！

#### 默认密码
- **用户名**：`admin`
- **默认密码**：`admin123`
- **初始化机制**：首次创建数据库时自动创建admin用户


### 全局配置文件
`global_config.yml` 包含详细的系统配置，支持：
- WebSocket连接参数
- API接口配置
- 自动回复设置
- 商品管理配置
- 日志配置等

## 🔧 高级功能

### AI回复配置
1. 在用户设置中配置OpenAI API密钥
2. 选择AI模型（支持GPT-3.5、GPT-4、通义千问等）
3. 设置回复策略和提示词
4. 启用AI回复功能

### 自动发货规则
1. 进入发货管理页面
2. 添加发货规则，设置商品关键词
3. 上传卡密文件或输入发货内容
4. 系统自动匹配商品并发货

### 商品信息管理
1. 系统自动收集消息中的商品信息
2. 通过API获取完整商品详情
3. 支持手动编辑商品信息
4. 为自动发货提供准确的商品数据

## 📊 监控和维护

### 日志管理
- **实时日志**：Web界面查看实时系统日志
- **日志文件**：`logs/` 目录下的按日期分割的日志文件
- **日志级别**：支持DEBUG、INFO、WARNING、ERROR级别


## 🔒 安全特性

- **JWT认证**：安全的用户认证机制
- **图形验证码**：防止自动化攻击
- **邮箱验证**：确保用户邮箱真实性
- **数据隔离**：用户数据完全隔离
- **会话管理**：安全的会话超时机制
- **操作日志**：完整的用户操作记录
- **代码加密**：核心业务逻辑采用多层加密保护

## 🛡️ 技术特性

### 🏗️ 架构设计
- **微服务架构**：模块化设计，易于维护和扩展
- **异步编程**：基于asyncio的高性能异步处理
- **WebSocket长连接**：实时消息处理，低延迟响应
- **RESTful API**：标准化的API接口设计

### 🔧 技术栈
- **后端框架**：FastAPI + Uvicorn
- **数据库**：SQLite（轻量级，无需额外配置）
- **前端技术**：原生HTML/CSS/JavaScript + Bootstrap
- **WebSocket**：实时双向通信
- **容器化**：Docker + Docker Compose

### 🚀 性能优化
- **连接池管理**：高效的数据库连接管理
- **异步处理**：非阻塞I/O操作
- **内存优化**：智能缓存和垃圾回收
- **资源限制**：Docker容器资源限制和监控

### 🔐 安全机制
- **多层加密**：敏感代码采用5层编码混淆
- **变量名随机化**：防止静态分析
- **运行时解密**：代码在内存中动态解密执行
- **防重复机制**：智能防重复确认和发货

## 🤝 贡献指南

欢迎为项目做出贡献！您可以通过以下方式参与：

### 📝 提交问题
- 在 [GitHub Issues](https://github.com/zhinianboke/xianyu-auto-reply/issues) 中报告Bug
- 提出新功能建议和改进意见
- 分享使用经验和最佳实践

### 🔧 代码贡献
- Fork 项目到您的GitHub账号
- 创建功能分支：`git checkout -b feature/your-feature`
- 提交更改：`git commit -am 'Add some feature'`
- 推送分支：`git push origin feature/your-feature`
- 提交 Pull Request


## 📞 技术支持


### 💬 交流群组

欢迎加入我们的技术交流群，获取实时帮助和最新更新：

#### 微信交流群
<img src="static/wechat-group.png" alt="微信群二维码" width="200">

#### QQ交流群
<img src="static/qq-group.png" alt="QQ群二维码" width="200">

### 📧 联系方式
- **技术支持**：遇到问题可在群内咨询
- **功能建议**：欢迎提出改进建议
- **Bug反馈**：发现问题请及时反馈

## 🧸 特别鸣谢

本项目参考了以下开源项目：

- **[XianYuApis](https://github.com/cv-cat/XianYuApis)** - 提供了闲鱼API接口的技术参考
- **[XianyuAutoAgent](https://github.com/shaxiu/XianyuAutoAgent)** - 提供了自动化处理的实现思路
- **[myfish](https://github.com/Kaguya233qwq/myfish)** - 提供了扫码登录的实现思路


感谢这些优秀的开源项目为本项目的开发提供了宝贵的参考和启发！

## ⚖️ 版权声明与使用条款

### 📋 重要声明

**本项目仅供学习和研究使用，严禁商业用途！**

### 🚫 使用限制

- ❌ **禁止商业使用** - 本项目及其衍生作品不得用于任何商业目的
- ❌ **禁止销售** - 不得以任何形式销售本项目或基于本项目的服务
- ❌ **禁止盈利** - 不得通过本项目进行任何形式的盈利活动
- ❌ **禁止违法使用** - 不得将本项目用于任何违法违规活动

### ✅ 允许使用

- ✅ **学习研究** - 可用于个人学习和技术研究
- ✅ **非商业分享** - 可在非商业环境下分享和讨论
- ✅ **开源贡献** - 欢迎为项目贡献代码和改进

### 📝 使用要求

如果您使用、修改或分发本项目，必须：

1. **保留原作者信息** - 必须在显著位置标注原作者和项目来源
2. **保留版权声明** - 不得删除或修改本版权声明
3. **注明修改内容** - 如有修改，需明确标注修改部分
4. **遵守开源协议** - 严格遵守项目的开源许可协议

### 👤 原作者信息

- **项目作者**：zhinianboke
- **项目地址**：https://github.com/zhinianboke/xianyu-auto-reply
- **联系方式**：通过GitHub Issues或项目交流群

### ⚠️ 免责声明

1. **使用风险自负** - 使用本项目产生的任何风险由使用者自行承担
2. **无质量保证** - 本项目按"现状"提供，不提供任何明示或暗示的保证
3. **责任限制** - 作者不对使用本项目造成的任何损失承担责任
4. **合规使用** - 使用者需确保使用行为符合当地法律法规

### 📞 侵权处理

如发现本项目存在侵权内容，请通过以下方式联系：

- **GitHub Issues**：https://github.com/zhinianboke/xianyu-auto-reply/issues
- **邮箱联系**：在项目交流群中获取联系方式

我们将在收到通知后**立即处理**并删除相关内容。

### 🤝 合作与授权

如需商业使用或特殊授权，请通过项目交流群联系作者进行协商。

---

**⚖️ 使用本项目即表示您已阅读、理解并同意遵守以上所有条款。**

---

🎉 **开始使用闲鱼自动回复系统，让您的闲鱼店铺管理更加智能高效！**

**请记住：仅限学习使用，禁止商业用途！**
