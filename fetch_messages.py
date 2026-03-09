"""
抓取指定频道下群组的历史消息。
用法：python fetch_messages.py
依赖已有的数据库（tgbot.db），使用第一个已授权账号的 session。
"""
import asyncio
import json
import os
import sys
from datetime import datetime

# 将项目根目录加入路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import (
    User, Chat, Channel,
    PeerUser, PeerChat, PeerChannel,
)

# ── 配置 ────────────────────────────────────────────────
TARGET_CHANNEL_ID = -1001001680975844   # 父频道 ID（仅用于关联查找）
FETCH_LIMIT = 100                        # 每个群组抓取条数
OUTPUT_DIR = "fetched_messages"          # 输出目录

# 直接指定要抓取的群组（ID 或 @username 或邀请链接），留空则自动查找
# 示例: DIRECT_TARGETS = [-1001234567890, '@mygroup', 'https://t.me/joinchat/xxxx']
DIRECT_TARGETS = []
# ────────────────────────────────────────────────────────


def get_account_credentials():
    """从数据库读取第一个已授权账号的凭证"""
    from web.app import create_app
    from telegram_manager import TelegramManager
    from models import Account

    app = create_app(TelegramManager())
    with app.app_context():
        acc = Account.query.filter_by(status='authorized').first()
        if not acc:
            raise RuntimeError('数据库中没有已授权的账号，请先在 Web 界面完成授权')
        return acc.api_id, acc.api_hash, acc.session_string


def sender_info(msg, entities_cache: dict):
    """提取消息发送者信息，返回 dict"""
    # 優先使用 entities_cache 中的完整实体
    sender_id = None
    username = None
    display_name = None
    sender_type = 'unknown'

    if msg.sender_id is not None:
        sender_id = msg.sender_id

    entity = entities_cache.get(sender_id)

    if entity is None:
        # 无法解析实体，只返回 ID
        return {
            'id': sender_id,
            'username': None,
            'display_name': None,
            'type': 'unknown',
        }

    if isinstance(entity, User):
        sender_type = 'bot' if entity.bot else 'user'
        username = entity.username
        display_name = ' '.join(filter(None, [entity.first_name, entity.last_name]))
    elif isinstance(entity, Channel):
        sender_type = 'channel'
        username = entity.username
        display_name = entity.title
    elif isinstance(entity, Chat):
        sender_type = 'group'
        username = None
        display_name = entity.title
    else:
        sender_type = type(entity).__name__.lower()
        display_name = getattr(entity, 'title', None) or getattr(entity, 'first_name', None)
        username = getattr(entity, 'username', None)

    return {
        'id': sender_id,
        'username': username,
        'display_name': display_name,
        'type': sender_type,
    }


async def fetch_group_messages(client: TelegramClient, group_entity, limit: int):
    """抓取指定群组的历史消息，返回结构化列表"""
    messages = []
    entities_cache = {}

    # 批量获取消息及其发送者实体
    async for msg in client.iter_messages(group_entity, limit=limit):
        # 缓存实体
        if msg.sender_id and msg.sender_id not in entities_cache:
            try:
                entity = await client.get_entity(msg.sender_id)
                entities_cache[msg.sender_id] = entity
            except Exception:
                entities_cache[msg.sender_id] = None

        sender = sender_info(msg, entities_cache)

        # 媒体类型说明
        media_type = None
        if msg.photo:
            media_type = 'photo'
        elif msg.video:
            media_type = 'video'
        elif msg.document:
            media_type = 'document'
        elif msg.sticker:
            media_type = 'sticker'
        elif msg.voice:
            media_type = 'voice'
        elif msg.gif:
            media_type = 'gif'

        messages.append({
            'msg_id': msg.id,
            'date': msg.date.strftime('%Y-%m-%d %H:%M:%S UTC'),
            'sender': sender,
            'text': msg.text or '',
            'media_type': media_type,
            'reply_to_msg_id': msg.reply_to_msg_id,
            'views': msg.views,
            'forwards': msg.forwards,
        })

    return messages


async def main():
    api_id, api_hash, session_string = get_account_credentials()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    async with TelegramClient(StringSession(session_string), api_id, api_hash) as client:

        # ── 方式一：直接指定目标 ──────────────────────────────
        if DIRECT_TARGETS:
            target_groups = []
            for target in DIRECT_TARGETS:
                try:
                    entity = await client.get_entity(target)
                    class _D:  # 模拟 dialog 对象
                        def __init__(self, e):
                            self.entity = e
                            self.name = getattr(e, 'title', None) or getattr(e, 'first_name', str(e.id))
                            self.id = e.id
                    target_groups.append(_D(entity))
                    print(f'  找到：{target_groups[-1].name} (ID: {entity.id})')
                except Exception as e:
                    print(f'  无法获取 {target}: {e}')
            if not target_groups:
                print('DIRECT_TARGETS 中的目标均无法访问，退出')
                return
            print(f'\n将抓取 {len(target_groups)} 个群组，每个各 {FETCH_LIMIT} 条消息\n')

        else:
        # ── 方式二：从对话列表中查找 ─────────────────────────────
            print(f'已连接，正在获取频道 {TARGET_CHANNEL_ID} 下的对话列表…')

            target_groups = []
            async for dialog in client.iter_dialogs():
                entity = dialog.entity
                if isinstance(entity, Channel) and hasattr(entity, 'linked_chat_id'):
                    if entity.linked_chat_id and -int(f'100{entity.linked_chat_id}') == TARGET_CHANNEL_ID:
                        target_groups.append(dialog)
                        print(f'  找到关联群组: {dialog.name} (ID: {dialog.id})')
                if dialog.name in ('闲聊扯淡', '修仙游戏'):
                    if dialog not in target_groups:
                        target_groups.append(dialog)
                        print(f'  找到命名匹配群组: {dialog.name} (ID: {dialog.id})')

            if not target_groups:
                print('\n未通过关联关系找到群组，改为列出所有群组/频道供你选择：')
                all_groups = []
                async for dialog in client.iter_dialogs():
                    if isinstance(dialog.entity, (Channel, Chat)):
                        all_groups.append(dialog)
                        print(f'  [{len(all_groups)}] {dialog.name} (ID: {dialog.id})')

                if not all_groups:
                    print('没有找到任何群组，退出')
                    return

                print('\n请输入要抓取的群组编号（逗号分隔，如 1,3），或直接回车抓取前两个：')
                choice = input('> ').strip()
                if choice:
                    indices = [int(x.strip()) - 1 for x in choice.split(',')]
                else:
                    indices = list(range(min(2, len(all_groups))))
                target_groups = [all_groups[i] for i in indices if 0 <= i < len(all_groups)]

            print(f'\n将抓取 {len(target_groups)} 个群组，每个各 {FETCH_LIMIT} 条消息\n')

        for dialog in target_groups:
            group_name = dialog.name
            safe_name = group_name.replace('/', '_').replace('\\', '_')
            output_file = os.path.join(OUTPUT_DIR, f'{safe_name}.json')
            txt_file = os.path.join(OUTPUT_DIR, f'{safe_name}.txt')

            print(f'正在抓取「{group_name}」(ID: {dialog.id})…')
            messages = await fetch_group_messages(client, dialog.entity, FETCH_LIMIT)
            print(f'  抓取完成，共 {len(messages)} 条')

            # 保存 JSON
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'group_name': group_name,
                    'group_id': dialog.id,
                    'fetched_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'),
                    'total': len(messages),
                    'messages': messages,
                }, f, ensure_ascii=False, indent=2)
            print(f'  → JSON 已保存: {output_file}')

            # 保存可读 TXT
            with open(txt_file, 'w', encoding='utf-8') as f:
                f.write(f'群组：{group_name}  (ID: {dialog.id})\n')
                f.write(f'抓取时间：{datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")}\n')
                f.write(f'共 {len(messages)} 条消息\n')
                f.write('=' * 60 + '\n\n')
                for m in messages:
                    s = m['sender']
                    sender_str = (
                        f"{s['display_name'] or '(无名称)'}"
                        f"  [@{s['username']}]" if s['username'] else
                        f"{s['display_name'] or '(无名称)'}"
                    )
                    f.write(f"[{m['date']}] [{m['msg_id']}]\n")
                    f.write(f"发送者: {sender_str}  ID:{s['id']}  类型:{s['type']}\n")
                    if m['reply_to_msg_id']:
                        f.write(f"回复消息 ID: {m['reply_to_msg_id']}\n")
                    if m['media_type']:
                        f.write(f"媒体: [{m['media_type']}]\n")
                    f.write(f"{m['text']}\n")
                    f.write('-' * 40 + '\n')
            print(f'  → TXT 已保存: {txt_file}\n')

    print('全部完成！文件保存在:', os.path.abspath(OUTPUT_DIR))


if __name__ == '__main__':
    asyncio.run(main())
