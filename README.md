# TG Bot — Telegram 多账号自动化助手

基于 [Telethon](https://github.com/LonamiWebs/Telethon) 和 Flask 构建的 Telegram 账号自动化管理工具，提供 Web 管理界面，支持多账号、关键词自动回复、定时发送、Forum 话题、白名单等功能。

---

## 功能特性

### 账号管理
- 多账号同时在线（每个账号独立 Session）
- 通过 Web 界面完成手机号 + 验证码 + 2FA 登录授权
- 账号在线状态实时显示
- **托管时间段**：可为每个账号设置仅在指定时间段内（如 18:00～次日 08:00）执行自动回复，支持跨午夜区间

### 关键词自动回复
- 监听"别人引用了我的消息"的回复，检测消息正文中的关键词
- 触发后自动发送预设回复内容
- 可指定适用账号（或对全部账号生效）
- **三种等待模式**：
  - **立即回复**：匹配后立刻发送
  - **解析等待时间**：从触发消息中提取中文时间（如"1小时48秒"），到期后再发送，支持额外缓冲秒数
  - **随机等待时间**：忽略消息中的时间，在自定义 [最小, 最大] 秒区间内随机取值后发送
- 可启用 / 停用单条规则，不删除保留配置

### 目标发送 & Forum 话题
- 每条规则和定时任务均可指定**任意发送目标**：用户、机器人、群组、超级群、频道（数字 ID）
- 输入目标 ID 后**实时识别实体类型**，显示类型标签（用户 / 机器人 / 群组 / 超级群 / 频道）及名称
- 若目标是 **Forum 频道**，自动拉取全部话题列表并提供下拉选择（调用 Telegram 官方 `GetForumTopicsRequest`，显示官方话题标题）
- 不指定话题时发送到默认（通用）话题

### 定时发送任务
- 多种调度方式：
  - **按间隔**：每 N 分钟执行一次
  - **Cron 表达式**：精确控制执行时间（如 `0 9 * * *` 每天 09:00 UTC）
- 支持指定目标类型（用户/机器人/群组/频道）和 Forum 话题
- 任务列表显示当前状态，支持启动 / 停止 / 删除

### 白名单
- 配置白名单用户，只对白名单中的用户触发关键词回复
- 留空则对所有人生效

### 操作日志
- 记录关键词匹配、自动回复、定时发送、错误等事件
- 可在 Web 界面中实时查看日志

---

## 技术栈

| 组件 | 版本要求 |
|------|---------|
| Python | 3.10+ |
| Telethon | ≥ 1.36.0 |
| Flask | ≥ 3.0.0 |
| Flask-SQLAlchemy | ≥ 3.1.0 |
| APScheduler | ≥ 3.10.4 |
| python-dotenv | ≥ 1.0.0 |
| 数据库 | SQLite（默认） |

---

## 快速开始

### 1. 克隆 & 安装依赖

```bash
git clone https://github.com/yourname/tgbot.git
cd tgbot
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`：

```env
SECRET_KEY=换成你的随机字符串
DATABASE_URL=sqlite:///tgbot.db
WEB_HOST=127.0.0.1
WEB_PORT=5000
DEBUG=False
```

### 3. 启动

```bash
python main.py
```

服务启动后访问 `http://127.0.0.1:5000`。

---

## 使用流程

### 添加账号

1. 进入**账号管理**页面，点击「添加账号」
2. 填写：
   - **显示名称**（便于识别）
   - **手机号**（含国际区号，如 `+8613800138000`）
   - **API ID** 和 **API Hash**（在 [my.telegram.org](https://my.telegram.org) 获取）
3. 点击「添加」后跳转验证页面，填入收到的验证码，若有两步验证再填密码
4. 授权成功后账号状态变为「已连接」

### 获取 Telegram API 凭据

1. 打开 [my.telegram.org](https://my.telegram.org)，用手机号登录
2. 进入 **API development tools**
3. 创建应用，获取 `api_id` 和 `api_hash`

### 配置关键词规则

1. 进入**关键词回复**页面
2. 填写：
   - **适用账号**：留空则全部账号生效
   - **关键词**：在"别人引用我消息的回复"中检测此文本
   - **等待模式**：选择立即回复、解析时间、或随机等待
   - **回复内容**：触发后发送的消息
   - **发送目标 ID**（可选）：填入数字 ID 后自动识别类型；Forum 频道会自动显示话题下拉菜单
   - **目标备注**（可选）：便于识别

### 配置定时任务

1. 进入**定时任务**页面
2. 选择账号，填入目标 ID（支持实时识别）
3. 选择调度类型：「按间隔」填写分钟数，「Cron 表达式」填写标准 5 字段 Cron
4. 若目标是 Forum 频道，选择话题
5. 填写消息内容后添加

### 托管时间段（账号级别）

在账号管理页面，每个账号可配置：

- **开启托管时间**：仅在指定时间段内执行自动回复
- **开始时间 / 结束时间**：支持跨午夜区间（如 `18:00` ~ `08:00`）
- 非托管时段触发的关键词会发送通知到「已保存的消息（Saved Messages）」，不在目标群组发送

---

## 项目结构

```
tgbot/
├── main.py                 # 入口：启动 Flask + Telethon 事件监听
├── telegram_manager.py     # Telethon 客户端管理、定时任务、待回复轮询
├── message_handler.py      # 关键词检测逻辑、等待时间解析
├── time_parser.py          # 中文时间解析（小时/分钟/秒）
├── models.py               # SQLAlchemy 数据模型
├── config.py               # Flask 配置读取
├── migrate.py              # 数据库结构迁移（幂等）
├── fetch_messages.py       # 工具脚本：导出群组消息到本地文件
├── requirements.txt
├── .env.example
└── web/
    ├── app.py              # Flask 应用工厂
    └── routes/
    │   ├── accounts.py     # 账号管理、授权、群组/话题发现 API
    │   ├── keywords.py     # 关键词规则 CRUD
    │   ├── tasks.py        # 定时任务 CRUD
    │   ├── whitelist.py    # 白名单管理
    │   └── logs.py         # 日志查看
    └── templates/
        ├── base.html
        ├── accounts.html
        ├── account_auth.html
        ├── keywords.html
        ├── keyword_edit.html
        ├── tasks.html
        ├── whitelist.html
        ├── logs.html
        └── index.html
```

---

## API 接口（内部使用）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/accounts/<id>/dialogs` | 获取账号所在群组/频道列表（含 is_forum 标记） |
| GET | `/accounts/<id>/dialogs/<group_id>/topics` | 获取 Forum 频道下的话题列表（官方标题） |
| GET | `/accounts/<id>/resolve/<target_id>` | 解析任意目标 ID，返回实体类型、名称、是否 Forum |

---

## 数据库迁移

当模型结构有新增列时，运行迁移脚本（幂等，列已存在时自动跳过）：

```bash
python migrate.py
```

---

## 注意事项

- 本工具仅用于个人账号自动化，请遵守 [Telegram 使用条款](https://telegram.org/tos)
- 频繁自动发送消息可能触发 Telegram 的频率限制或账号封禁风险，建议合理配置等待时间
- API ID 和 API Hash 属于敏感信息，请勿提交到公开仓库，`.env` 已在 `.gitignore` 中排除
- SQLite 数据库文件 `instance/tgbot.db` 包含 Session 字符串，请妥善保管
 - Telegram 账号自动化管理工具

## 功能

- **多账号管理**：在 Web UI 中添加、授权、启停多个 Telegram 用户账号
- **关键词自动回复**：监听"别人引用你消息的回复"，匹配关键词后自动发送预设消息
- **定时解析等待时间**：从消息中提取中文时间（如"1小时48秒"），加上缓冲时间后定时发送
- **定时任务**：按固定间隔或 Cron 表达式向指定群组发送消息
- **运行日志**：实时查看匹配、回复、定时发送等操作记录


## 使用说明

### 添加账号

1. 进入 **账号管理** → 填写名称、手机号、API ID、API Hash
2. 跳转到授权页面 → 点击"发送验证码"
3. 填入收到的验证码（如开启了两步验证需同时填写密码）→ 完成授权

### 配置关键词回复

| 字段 | 示例值 |
|------|--------|
| 关键词 | `还需时间` |
| 需要解析等待时间 |  `开启` |
| 额外缓冲时间 | `30`（秒） |
| 回复内容 | `关键词` |

**触发逻辑**：当别人引用你发的消息，且回复内容包含"还需时间"，
系统自动提取其中的中文时间（如 `1小时48秒` = 3648秒），
加上 30 秒缓冲（共 3678 秒后），发送"灵树灌溉"到同一群组。

### 配置定时任务

| 类型 | 说明 | 示例 |
|------|------|------|
| 按间隔 | 每 N 分钟发一次 | `60` → 每小时 |
| Cron | 标准 5 字段 Cron | `0 9 * * *` → 每天 09:00 UTC |

群组 ID 获取方法：将账号拉入群组后，在群组头像上右键 → 复制链接，
从链接末尾获取数字部分；超级群组需在前面加 `-100`。

---

## 项目结构

```
tgbot/
├── main.py                # 启动入口
├── config.py              # 配置读取
├── models.py              # 数据库模型
├── time_parser.py         # 中文时间解析
├── message_handler.py     # 消息关键词处理
├── telegram_manager.py    # Telethon 客户端管理
├── requirements.txt
├── .env.example
└── web/
    ├── app.py             # Flask 应用工厂
    ├── routes/
    │   ├── main.py        # 控制台
    │   ├── accounts.py    # 账号管理
    │   ├── keywords.py    # 关键词规则
    │   ├── tasks.py       # 定时任务
    │   └── logs.py        # 日志查看
    └── templates/         # HTML 模板（Bootstrap 5）
```

---

## 注意事项

- Web 界面默认仅监听 `127.0.0.1`，**不要暴露到公网**
- Session 字符串以明文存储在 SQLite 数据库中，请妥善保管 `tgbot.db`
- Telegram 对自动化操作有频率限制，避免在极短时间内大量发送消息
- 本工具操控的是**用户账号**（非 Bot），请遵守 Telegram 服务条款
