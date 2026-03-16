"""临时脚本：查看 target_entities 表中与该群相关的记录"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from web.app import create_app
from telegram_manager import TelegramManager

app = create_app(TelegramManager())

with app.app_context():
    from models import TargetEntity
    targets = TargetEntity.query.all()
    print(f"共 {len(targets)} 条目标实体：\n")
    for t in targets:
        d = t.to_dict()
        for k, v in d.items():
            print(f"  {k} = {v!r}")
        print()
