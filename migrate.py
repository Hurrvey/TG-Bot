"""数据库迁移：为各表添加新列（幂等，列已存在时自动跳过）"""
from web.app import create_app
from telegram_manager import TelegramManager
import sqlalchemy as sa

app = create_app(TelegramManager())
with app.app_context():
    from models import db
    conn = db.engine.connect()

    migrations = [
        # keywords 表
        ('ALTER TABLE keywords ADD COLUMN target_group_id VARCHAR(100)', 'keywords.target_group_id'),
        ('ALTER TABLE keywords ADD COLUMN target_group_name VARCHAR(200) DEFAULT ""', 'keywords.target_group_name'),
        ('ALTER TABLE keywords ADD COLUMN use_random_time BOOLEAN DEFAULT 0', 'keywords.use_random_time'),
        ('ALTER TABLE keywords ADD COLUMN random_min_seconds INTEGER DEFAULT 60', 'keywords.random_min_seconds'),
        ('ALTER TABLE keywords ADD COLUMN random_max_seconds INTEGER DEFAULT 300', 'keywords.random_max_seconds'),
        # accounts 表
        ('ALTER TABLE accounts ADD COLUMN schedule_enabled BOOLEAN DEFAULT 0', 'accounts.schedule_enabled'),
        ('ALTER TABLE accounts ADD COLUMN schedule_start VARCHAR(5) DEFAULT "18:00"', 'accounts.schedule_start'),
        ('ALTER TABLE accounts ADD COLUMN schedule_end VARCHAR(5) DEFAULT "08:00"', 'accounts.schedule_end'),
        # keywords 表 — topic_id
        ('ALTER TABLE keywords ADD COLUMN topic_id INTEGER', 'keywords.topic_id'),
        # pending_replies 表 — topic_id
        ('ALTER TABLE pending_replies ADD COLUMN topic_id INTEGER', 'pending_replies.topic_id'),
        # scheduled_tasks 表 — topic_id
        ('ALTER TABLE scheduled_tasks ADD COLUMN topic_id INTEGER', 'scheduled_tasks.topic_id'),
        # scheduled_tasks 表 — 随机延迟
        ('ALTER TABLE scheduled_tasks ADD COLUMN random_delay_min INTEGER DEFAULT 0', 'scheduled_tasks.random_delay_min'),
        ('ALTER TABLE scheduled_tasks ADD COLUMN random_delay_max INTEGER DEFAULT 0', 'scheduled_tasks.random_delay_max'),
        # keywords 表 — 随机缓冲时间
        ('ALTER TABLE keywords ADD COLUMN buffer_random_min INTEGER DEFAULT 0', 'keywords.buffer_random_min'),
        ('ALTER TABLE keywords ADD COLUMN buffer_random_max INTEGER DEFAULT 0', 'keywords.buffer_random_max'),
        # target_entities 表 — 关联话题
        ('ALTER TABLE target_entities ADD COLUMN topic_id INTEGER', 'target_entities.topic_id'),
        # scheduled_tasks 表 — 断点续时
        ('ALTER TABLE scheduled_tasks ADD COLUMN next_run_at DATETIME', 'scheduled_tasks.next_run_at'),
        ('ALTER TABLE scheduled_tasks ADD COLUMN last_run_at DATETIME', 'scheduled_tasks.last_run_at'),
    ]

    for sql, label in migrations:
        try:
            conn.execute(sa.text(sql))
            print(f'✓ 添加 {label}')
        except Exception as e:
            print(f'  跳过 {label}（已存在）')

    conn.commit()
    conn.close()
    print('迁移完成')
