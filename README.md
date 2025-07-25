# 🐟 闲鱼自动回复系统

[![GitHub](https://img.shields.io/badge/GitHub-zhinianboke%2Fxianyu--auto--reply-blue?logo=github)](https://github.com/zhinianboke/xianyu-auto-reply)
[![Docker](https://img.shields.io/badge/Docker-一键部署-blue?logo=docker)](https://github.com/zhinianboke/xianyu-auto-reply#-快速开始)

一个功能完整的闲鱼自动回复和管理系统，支持多用户、多账号管理，具备智能回复、自动发货、商品管理等企业级功能。

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
- **AI智能回复** - 集成OpenAI API，支持上下文理解
- **变量替换** - 回复内容支持动态变量（用户名、商品信息等）
- **优先级策略** - 关键词回复优先，AI回复兜底

### 🚚 自动发货功能
- **智能匹配** - 基于商品信息自动匹配发货规则
- **多种触发** - 支持付款消息、小刀消息等多种触发条件
- **防重复发货** - 智能防重复机制，避免重复发货
- **卡密发货** - 支持文本内容和卡密文件发货

### 🛍️ 商品管理
- **自动收集** - 消息触发时自动收集商品信息
- **API获取** - 通过闲鱼API获取完整商品详情
- **批量管理** - 支持批量查看、编辑商品信息
- **智能去重** - 自动去重，避免重复存储

### 📊 系统监控
- **实时日志** - 完整的操作日志记录和查看
- **性能监控** - 系统资源使用情况监控
- **健康检查** - 服务状态健康检查
- **数据备份** - 自动数据备份和恢复

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

### 方式三：本地部署

```bash
# 1. 克隆项目
git clone https://github.com/zhinianboke/xianyu-auto-reply.git
cd xianyu-auto-reply

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动系统
python Start.py

# 4. 访问系统
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
- 系统检测到付款消息时自动发货

## 🏗️ 系统架构

```
┌─────────────────────────────────────┐
│           Web界面 (FastAPI)         │
│         用户管理 + 功能界面          │
└─────────────┬───────────────────────┘
              │
┌─────────────▼───────────────────────┐
│        CookieManager               │
│         多账号任务管理              │
└─────────────┬───────────────────────┘
              │
┌─────────────▼───────────────────────┐
│      XianyuLive (多实例)           │
│     WebSocket连接 + 消息处理        │
└─────────────┬───────────────────────┘
              │
┌─────────────▼───────────────────────┐
│        SQLite数据库                │
│   用户数据 + 商品信息 + 配置数据     │
└─────────────────────────────────────┘
```

## 📁 项目结构

```
xianyu-auto-reply/
├── Start.py                    # 主启动文件
├── XianyuAutoAsync.py         # 闲鱼WebSocket客户端核心
├── reply_server.py            # FastAPI Web服务器
├── db_manager.py              # 数据库管理模块
├── cookie_manager.py          # Cookie和任务管理
├── ai_reply_engine.py         # AI回复引擎
├── config.py                  # 配置管理
├── file_log_collector.py      # 日志收集器
├── global_config.yml          # 全局配置文件
├── requirements.txt           # Python依赖
├── docker-compose.yml         # Docker编排配置
├── Dockerfile                 # Docker镜像构建
├── static/                    # 前端静态文件
│   ├── index.html            # 主界面
│   ├── login.html            # 登录页面
│   ├── register.html         # 注册页面
│   └── ...                   # 其他页面和资源
├── logs/                      # 日志文件目录
├── data/                      # 数据库文件目录
└── backups/                   # 备份文件目录
```

## ⚙️ 配置说明


### 管理员密码配置

**重要**：为了系统安全，强烈建议修改默认管理员密码！

#### 默认密码
- **用户名**：`admin`
- **默认密码**：`admin123`
- **初始化机制**：首次创建数据库时自动创建admin用户

#### 修改密码方式

**方式一：Web界面修改（推荐）**
1. 使用默认密码登录系统
2. 进入系统设置页面
3. 在"修改密码"区域输入当前密码和新密码
4. 点击"修改密码"按钮完成修改


**密码管理机制**：
- 数据库初始化时创建admin用户，密码为 `admin123`
- 重启时如果用户表已存在，不重新初始化
- 所有用户（包括admin）统一使用用户表验证
- 密码修改后立即生效，无需重启

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

### 数据备份
```bash
# 手动备份
./docker-deploy.sh backup

# 查看备份
ls backups/
```

### 健康检查
```bash
# 检查服务状态
curl http://localhost:8080/health

# 查看系统状态
./docker-deploy.sh status
```

## 🔒 安全特性

- **JWT认证**：安全的用户认证机制
- **图形验证码**：防止自动化攻击
- **邮箱验证**：确保用户邮箱真实性
- **数据隔离**：用户数据完全隔离
- **会话管理**：安全的会话超时机制
- **操作日志**：完整的用户操作记录

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

### 📖 文档贡献
- 改进现有文档
- 添加使用示例
- 翻译文档到其他语言

## 📞 技术支持

### 🔧 故障排除
如遇问题，请：
1. 查看日志：`docker-compose logs -f`
2. 检查状态：`./docker-deploy.sh status`
3. 健康检查：`curl http://localhost:8080/health`

### 💬 交流群组

欢迎加入我们的技术交流群，获取实时帮助和最新更新：

#### 微信交流群
<img src="wechat-group.png" alt="微信群二维码" width="200">

#### QQ交流群
<img src="qq-group.png" alt="QQ群二维码" width="200">

### 📧 联系方式
- **技术支持**：遇到问题可在群内咨询
- **功能建议**：欢迎提出改进建议
- **Bug反馈**：发现问题请及时反馈

---

🎉 **开始使用闲鱼自动回复系统，让您的闲鱼店铺管理更加智能高效！**
