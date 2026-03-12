from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Account(db.Model):
    """Telegram账号"""
    __tablename__ = 'accounts'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    api_id = db.Column(db.Integer, nullable=False)
    api_hash = db.Column(db.String(100), nullable=False)
    session_string = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    # pending / authorized / error
    status = db.Column(db.String(50), default='pending')
    # 托管时间限制：False=全天，True=仅 start~end 时段自动执行
    schedule_enabled = db.Column(db.Boolean, default=False)
    schedule_start = db.Column(db.String(5), default='18:00')   # HH:MM
    schedule_end = db.Column(db.String(5), default='08:00')     # HH:MM
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    keywords = db.relationship('Keyword', backref='account', lazy=True,
                               foreign_keys='Keyword.account_id')
    scheduled_tasks = db.relationship('ScheduledTask', backref='account', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'phone': self.phone,
            'api_id': self.api_id,
            'is_active': self.is_active,
            'status': self.status,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        }


class Keyword(db.Model):
    """关键词规则：检测回复中的关键词并自动回复"""
    __tablename__ = 'keywords'

    id = db.Column(db.Integer, primary_key=True)
    # NULL 表示对所有账号生效
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True)
    keyword = db.Column(db.String(500), nullable=False)
    # 是否需要从消息中解析等待时间
    has_time_requirement = db.Column(db.Boolean, default=False)
    # 在解析出的时间基础上额外等待的秒数（固定缓冲）
    time_buffer_seconds = db.Column(db.Integer, default=30)
    # 随机缓冲：若 buffer_random_max > 0，则缓冲时间从 [buffer_random_min, buffer_random_max] 随机取
    buffer_random_min = db.Column(db.Integer, default=0)
    buffer_random_max = db.Column(db.Integer, default=0)
    reply_message = db.Column(db.Text, nullable=False)
    # 指定发送目标群组（可选）。填写后回复固定发到此群组，而非触发消息所在的聊天
    target_group_id = db.Column(db.String(100))
    target_group_name = db.Column(db.String(200), default='')
    # 指定发送到群组内的哪个话题（Forum Topic ID），None 表示不指定（发到默认/通用话题）
    topic_id = db.Column(db.Integer, nullable=True)
    # 随机等待时间：开启后忽略解析时间，在 [min, max] 秒内随机选一个等待时间
    use_random_time = db.Column(db.Boolean, default=False)
    random_min_seconds = db.Column(db.Integer, default=60)
    random_max_seconds = db.Column(db.Integer, default=300)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'account_id': self.account_id,
            'keyword': self.keyword,
            'has_time_requirement': self.has_time_requirement,
            'time_buffer_seconds': self.time_buffer_seconds,
            'buffer_random_min': self.buffer_random_min,
            'buffer_random_max': self.buffer_random_max,
            'reply_message': self.reply_message,
            'target_group_id': self.target_group_id,
            'target_group_name': self.target_group_name,
            'topic_id': self.topic_id,
            'use_random_time': self.use_random_time,
            'random_min_seconds': self.random_min_seconds,
            'random_max_seconds': self.random_max_seconds,
            'is_active': self.is_active,
        }


class ScheduledTask(db.Model):
    """定时发送消息任务"""
    __tablename__ = 'scheduled_tasks'

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False)
    group_id = db.Column(db.String(100), nullable=False)
    group_name = db.Column(db.String(200), default='')
    topic_id = db.Column(db.Integer, nullable=True)   # Forum 话题 ID
    message = db.Column(db.Text, nullable=False)
    # interval: 按间隔；cron: 按cron表达式
    task_type = db.Column(db.String(20), default='interval')
    interval_minutes = db.Column(db.Integer)
    cron_expression = db.Column(db.String(100))
    # 随机延迟：在触发时间后额外随机等待 [min, max] 秒，0 表示不启用
    random_delay_min = db.Column(db.Integer, default=0)
    random_delay_max = db.Column(db.Integer, default=0)
    # 上次实际执行时间（记录于 _send_scheduled_message 执行成功后，用于断点续时）
    last_run_at = db.Column(db.DateTime, nullable=True)
    # 上次调度器记录的下次运行时间（辅助字段，保留备用）
    next_run_at = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'account_id': self.account_id,
            'group_id': self.group_id,
            'group_name': self.group_name,
            'message': self.message,
            'task_type': self.task_type,
            'interval_minutes': self.interval_minutes,
            'cron_expression': self.cron_expression,
            'random_delay_min': self.random_delay_min,
            'random_delay_max': self.random_delay_max,
            'is_active': self.is_active,
        }


class PendingReply(db.Model):
    """待发送的定时回复（由关键词+时间规则触发）"""
    __tablename__ = 'pending_replies'

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False)
    group_id = db.Column(db.String(100), nullable=False)
    keyword_id = db.Column(db.Integer, db.ForeignKey('keywords.id'), nullable=True)
    topic_id = db.Column(db.Integer, nullable=True)   # Forum 话题 ID，None 表示不指定
    message = db.Column(db.Text, nullable=False)
    scheduled_at = db.Column(db.DateTime, nullable=False)
    is_sent = db.Column(db.Boolean, default=False)
    sent_at = db.Column(db.DateTime)
    triggered_by = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class MessageLog(db.Model):
    """操作日志"""
    __tablename__ = 'message_logs'

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True)
    group_id = db.Column(db.String(100), default='')
    group_name = db.Column(db.String(200), default='')
    # sent / keyword_matched / auto_replied / scheduled_sent / error
    log_type = db.Column(db.String(50))
    content = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Whitelist(db.Model):
    """白名单：只有列表中的实体（用户/频道/机器人）引用我的消息时才响应"""
    __tablename__ = 'whitelist'

    id = db.Column(db.Integer, primary_key=True)
    # NULL 表示对所有账号生效
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True)
    # Telegram 实体 ID（正数为用户/机器人，负数为频道）
    entity_id = db.Column(db.String(50), nullable=False)
    entity_name = db.Column(db.String(200), default='')
    # user / bot / channel
    entity_type = db.Column(db.String(20), default='user')
    note = db.Column(db.String(200), default='')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'account_id': self.account_id,
            'entity_id': self.entity_id,
            'entity_name': self.entity_name,
            'entity_type': self.entity_type,
            'note': self.note,
            'is_active': self.is_active,
        }


class TargetEntity(db.Model):
    """目标列表：保存曾使用过的发送目标（群组/频道/用户/机器人）"""
    __tablename__ = 'target_entities'

    id = db.Column(db.Integer, primary_key=True)
    entity_id = db.Column(db.String(50), unique=True, nullable=False)  # Telegram 数字 ID
    name = db.Column(db.String(200), default='')   # 显示名称
    # user / bot / group / supergroup / channel / unknown
    entity_type = db.Column(db.String(20), default='unknown')
    note = db.Column(db.String(200), default='')
    topic_id = db.Column(db.Integer, nullable=True)   # 关联的 Forum 话题 ID（可选）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'entity_id': self.entity_id,
            'name': self.name,
            'entity_type': self.entity_type,
            'note': self.note,
            'topic_id': self.topic_id,
        }
