"""
列出指定超群组的所有话题（Forum Topics）及其 ID。
原理：从消息的 reply_to 字段中收集 reply_to_top_id，即为各话题 ID。
用法：python list_topics.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telethon import TelegramClient
from telethon.sessions import StringSession


# ── 配置：填写要查询的群组/频道 ID ──────────────────────
TARGET_ID = -1001680975844   # 替换为你的群组 ID
SCAN_LIMIT = 500             # 扫描最近多少条消息来发现话题
# ────────────────────────────────────────────────────────


def get_credentials():
    from web.app import create_app
    from telegram_manager import TelegramManager
    from models import Account
    app = create_app(TelegramManager())
    with app.app_context():
        acc = Account.query.filter_by(status='authorized').first()
        if not acc:
            raise RuntimeError('没有已授权账号，请先在 Web 界面完成授权')
        return acc.api_id, acc.api_hash, acc.session_string


async def main():
    api_id, api_hash, session_string = get_credentials()

    async with TelegramClient(StringSession(session_string), api_id, api_hash) as client:
        try:
            entity = await client.get_entity(TARGET_ID)
        except Exception as e:
            print(f'获取实体失败: {e}')
            return

        title = getattr(entity, 'title', str(TARGET_ID))
        is_forum = getattr(entity, 'forum', False)
        linked = getattr(entity, 'linked_chat_id', None)

        print(f'群组名称  : {title}')
        print(f'群组 ID   : {TARGET_ID}')
        print(f'Forum模式 : {"是" if is_forum else "否"}')
        if linked:
            print(f'关联频道  : -100{linked}')
        print()

        if not is_forum:
            print('该群组未开启话题模式，无需话题 ID，直接用群组 ID 发消息即可。')
            if linked:
                print(f'\n如果你想发到关联的频道，请使用 ID: -100{linked}')
            return

        # 扫描最近消息，收集所有出现的 top_id（话题 ID）
        print(f'正在扫描最近 {SCAN_LIMIT} 条消息以发现话题…')
        topic_ids = {}   # top_id -> 第一条消息的文本（用于猜名字）

        async for msg in client.iter_messages(entity, limit=SCAN_LIMIT):
            rt = msg.reply_to
            if rt is None:
                continue
            top_id = getattr(rt, 'reply_to_top_id', None) or getattr(rt, 'reply_to_msg_id', None)
            if top_id and getattr(rt, 'forum_topic', False):
                if top_id not in topic_ids:
                    topic_ids[top_id] = ''

        if not topic_ids:
            # 降级：收集所有 reply_to_top_id（有些版本 forum_topic 字段不存在）
            async for msg in client.iter_messages(entity, limit=SCAN_LIMIT):
                rt = msg.reply_to
                if rt is None:
                    continue
                top_id = getattr(rt, 'reply_to_top_id', None)
                if top_id:
                    topic_ids[top_id] = topic_ids.get(top_id, '')

        # 尝试获取每个话题的起始消息来确认名字
        for top_id in list(topic_ids.keys()):
            try:
                first_msg = await client.get_messages(entity, ids=top_id)
                if first_msg and first_msg.action:
                    action = first_msg.action
                    topic_ids[top_id] = getattr(action, 'title', f'(话题 #{top_id})')
                else:
                    topic_ids[top_id] = f'(话题 #{top_id})'
            except Exception:
                topic_ids[top_id] = f'(话题 #{top_id})'

        if topic_ids:
            print(f'\n共发现 {len(topic_ids)} 个话题：\n')
            print(f'{"话题名称":<30} {"话题 ID":>12}')
            print('-' * 44)
            for tid, tname in sorted(topic_ids.items()):
                print(f'{tname:<30} {tid:>12}')
            print()
            print('在关键词规则中，"目标群组 ID" 填写群组 ID，')
            print('如需发到特定话题，请告知我，我会为规则增加 reply_to（话题 ID）支持。')
        else:
            print('未能从最近消息中发现话题 ID，请尝试增大 SCAN_LIMIT 或手动在 Telegram App 中查看话题的链接。')
            print()
            print('在 Telegram App 中获取话题 ID 的方法：')
            print('  1. 进入群组，点击某个话题')
            print('  2. 长按话题内任意消息 → 复制链接')
            print('  3. 链接格式：https://t.me/c/<频道数字ID>/<话题ID>/<消息ID>')


if __name__ == '__main__':
    asyncio.run(main())
