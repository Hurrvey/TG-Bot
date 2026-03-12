# TG Bot — Telegram 多账号自动化助手

基于 [Telethon](https://github.com/LonamiWebs/Telethon) 和 Flask 构建的 Telegram 账号自动化管理工具，提供 Web 管理界面，支持多账号、关键词自动回复、定时发送、Forum 话题、白名单、发送队列可视化等功能。

---

## 功能特性

### 账号管理
- 多账号同时在线（每个账号独立 Session）
- 通过 Web 界面完成手机号 + 验证码 + 2FA 登录授权
- 账号在线状态实时显示
- **托管时间段**：可为每个账号设置仅在指定时间段内（如 18:00～次日 08:00）执行自动回复，支持跨午夜区间；非托管时段触发时向「已保存的消息」发送通知

### 关键词自动回复
- 监听"别人引用了我的消息"的回复，检测消息正文中的关键词
- 触发后自动发送预设回复内容
- 可指定适用账号（或对全部账号生效）
- **三种等待模式**：
  - **立即回复**：匹配后立刻发送
  - **解析等待时间**：从触发消息中提取中文时间（如"1小时48秒"），到期后再发送，支持固定缓冲秒数或随机缓冲区间
  - **随机等待时间**：忽略消息中的时间，在自定义 \[最小, 最大\] 秒区间内随机取值后发送
- 可启用 / 停用单条规则，不删除保留配置

### 目标列表 & Forum 话题
- 维护可复用的目标实体列表（用户/机器人/群组/超级群/频道）
- 输入目标 ID 后**实时识别实体类型**并自动填充名称
- 若目标是 **Forum 频道**，自动拉取全部话题列表并提供下拉选择
- 支持为目标绑定默认 Forum 话题 ID

### 定时发送任务
- 多种调度方式：
  - **按间隔**：每 N 分钟执行一次
  - **Cron 表达式**：精确控制执行时间（如 `0 9 * * *` 每天 09:00 UTC）
- 支持随机延迟：在触发后额外等待 \[最小, 最大\] 秒再发送
- **断点续时**：程序重启后，间隔任务会根据上次实际发送时间（`last_run_at`）自动计算剩余等待时间并从断点继续，而非从头计时

### 发送队列（实时可视化）
- 专属页面展示所有等待中的任务（关键词回复 + 定时任务）
- 每条任务显示：类型徽章、账号、目标、消息预览、计划发送时间、**倒计时进度条**
- 进度条颜色随剩余时间动态变化（绿→橙→红）
- 每秒本地倒计时 + 每 5 秒从服务器同步，确保数据准确

### 消息防冲突 & 自动重试
- **入队时防冲突**：新任务入队时使用贪心时间槽算法，自动检测同一目标 10 秒内的已有任务并向后推移，支持多米诺效应级联处理
- **执行时顺序保障**：同一目标的到期消息按计划时间升序发送；若连续发送间隔不足 10 秒则自动 sleep 补齐
- **失败自动重试**：发送异常时将该消息推迟 10 秒重新入队，记录错误日志，下次轮询自动重试

### 白名单
- 配置白名单实体（用户/机器人/频道），只对名单中的发送者触发关键词回复
- 留空则对所有人生效

### 操作日志
- 记录关键词匹配、自动回复、定时发送、错误等全部事件
- 可在 Web 界面中实时查看

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

### 3. 初始化数据库

```bash
python migrate.py
```

### 4. 启动

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

1. 进入**关键词回复**页面，点击「添加规则」
2. 填写：
   - **适用账号**：留空则全部账号生效
   - **关键词**：在"别人引用我消息的回复"中检测此文本
   - **等待模式**：选择立即回复、解析时间（含缓冲）、或随机等待
   - **回复内容**：触发后发送的消息
   - **发送目标 ID**（可选）：填入数字 ID 后自动识别类型；Forum 频道自动弹出话题下拉菜单
3. 可随时启用 / 停用规则而无需删除

### 配置定时任务

1. 进入**定时任务**页面
2. 选择账号，填入目标 ID（自动识别类型）
3. 选择调度类型：「按间隔」填写分钟数，「Cron 表达式」填写标准 5 字段 Cron
4. 若目标是 Forum 频道，选择话题
5. 可配置随机延迟区间（在触发后额外随机等待）
6. 填写消息内容后添加；程序重启后自动从断点续时

### 查看发送队列

进入**发送队列**页面，实时查看所有待发任务（关键词回复 + 定时任务）：

- **类型**：青色 = 关键词回复，紫色 = 定时任务
- **倒计时**：精确到秒，带颜色进度条（≥2分钟绿色 / ≤2分钟橙色 / ≤30秒红色）
- 每 5 秒自动从服务器同步一次数据

### 托管时间段（账号级别）

在账号管理页面，每个账号可配置：

- **开启托管时间**：仅在指定时间段内执行自动回复
- **开始时间 / 结束时间**：支持跨午夜区间（如 `18:00` ~ `08:00`）
- 非托管时段触发的关键词会发送通知到「已保存的消息（Saved Messages）」

---

## 项目结构

```
tgbot/
├── main.py                 # 入口：启动 Flask + Telethon 事件监听
├── telegram_manager.py     # Telethon 客户端管理、定时任务、待回复轮询、防冲突执行
├── message_handler.py      # 关键词检测、时间解析、贪心时间槽入队算法
├── time_parser.py          # 中文时间解析（小时/分钟/秒）
├── models.py               # SQLAlchemy 数据模型
├── config.py               # Flask 配置读取
├── migrate.py              # 数据库结构迁移（幂等，列已存在自动跳过）
├── fetch_messages.py       # 工具脚本：导出群组消息到本地文件
├── requirements.txt
├── .env.example
└── web/
    ├── app.py              # Flask 应用工厂，注册所有 Blueprint
    └── routes/
    │   ├── accounts.py     # 账号管理、授权、群组/话题发现 API
    │   ├── keywords.py     # 关键词规则 CRUD
    │   ├── tasks.py        # 定时任务 CRUD
    │   ├── queue.py        # 发送队列页面 & JSON API
    │   ├── whitelist.py    # 白名单管理
    │   └── logs.py         # 日志查看
    └── templates/
        ├── base.html
        ├── accounts.html
        ├── account_auth.html
        ├── keywords.html
        ├── keyword_edit.html
        ├── tasks.html
        ├── queue.html       # 发送队列实时倒计时页面
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
| GET | `/queue/` | 发送队列页面 |
| GET | `/queue/api` | 发送队列 JSON 数据（按剩余时间升序） |

---

## 核心机制说明

### 消息防冲突（贪心时间槽算法）

同一目标（account + group）短时间内有多条待发消息时，入队时自动调整计划时间，确保相邻两条间隔 ≥ 10 秒：

1. 查询同目标已有的未发送消息，按计划时间升序排列
2. 从期望时间 `slot` 开始，逐一与已有消息比较：若 `|e - slot| < 10s`，则 `slot = e + 10s`
3. 自动级联处理多米诺效应（连续冲突时 slot 持续后移直到无冲突）

执行时额外保障：到期消息按时间升序批量发送，同目标连续发送间隔不足 10 秒则 sleep 补齐；发送失败自动推迟 10 秒重试。

### 断点续时（last_run_at 机制）

间隔型定时任务每次成功发送后将当前时间写入 `last_run_at`。程序重启时：

```
expected_next = last_run_at + interval
if expected_next > now:
    start_date = expected_next   # 从剩余时间继续，而非重新计时
```

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
