import logging
import random
from datetime import datetime, timedelta

from time_parser import parse_chinese_time, format_seconds

logger = logging.getLogger(__name__)


def _is_in_schedule(start_str: str, end_str: str) -> bool:
    """判断当前本地时间是否在托管时段内，支持跨午夜（如 18:00 → 次日 08:00）"""
    now = datetime.now()
    cur = now.hour * 60 + now.minute
    try:
        sh, sm = map(int, (start_str or '18:00').split(':'))
        eh, em = map(int, (end_str or '08:00').split(':'))
    except Exception:
        return True   # 格式错误时全天托管
    s, e = sh * 60 + sm, eh * 60 + em
    if s <= e:          # 普通段：如 08:00~18:00
        return s <= cur <= e
    else:               # 跨午夜：如 18:00~08:00
        return cur >= s or cur <= e


async def check_keywords(manager, account_id: int, client, event, msg, replied_msg):
    """
    检测消息中的关键词，根据规则自动回复。

    仅处理"回复了我的消息"的消息：
      - 若关键词无时间要求，立即回复
      - 若关键词有时间要求，从消息中提取时间，加上缓冲秒数后定时回复
    """
    text = msg.text or ''
    if not text:
        return

    # ── 托管时间检查 ─────────────────────────────────────────
    with manager.app.app_context():
        from models import Account
        _account = Account.query.get(account_id)
        if _account and _account.schedule_enabled:
            if not _is_in_schedule(_account.schedule_start, _account.schedule_end):
                logger.debug(
                    f'[账号{account_id}] 当前不在托管时段 '
                    f'({_account.schedule_start}~{_account.schedule_end})，发通知'
                )
                try:
                    sender_name = getattr(msg.sender, 'first_name', '') or str(msg.sender_id)
                    await client.send_message(
                        'me',
                        f"\u23f0 非托管时段 ({_account.schedule_start} \u2013 {_account.schedule_end})\n\n"
                        f"有人引用了你的消息，关键词规则\u672a\u89e6\u53d1\u3002\n\n"
                        f"\U0001f464 发送者: {sender_name} ({msg.sender_id})\n"
                        f"\U0001f4ac 消息内容:\n{text[:400]}"
                    )
                except Exception as _e:
                    logger.warning(f'发送非托管通知失败: {_e}')
                return
    # ────────────────────────────────────────────────────────

    # ── 白名单检查 ──────────────────────────────────────────
    with manager.app.app_context():
        from models import db, Whitelist
        active_entries = Whitelist.query.filter(
            Whitelist.is_active == True,
            db.or_(
                Whitelist.account_id == account_id,
                Whitelist.account_id == None
            )
        ).all()

        if active_entries:
            sender_id = str(msg.sender_id) if msg.sender_id else ''
            allowed_ids = {e.entity_id for e in active_entries}
            if sender_id not in allowed_ids:
                logger.debug(
                    f'[账号{account_id}] 发送者 {sender_id} 不在白名单中，忽略'
                )
                return
    # ────────────────────────────────────────────────────────

    try:
        chat = await event.get_chat()
    except Exception:
        return

    trigger_group_id = str(chat.id)
    group_name = getattr(chat, 'title', '') or getattr(chat, 'username', '') or trigger_group_id

    with manager.app.app_context():
        from models import db, Keyword, PendingReply, MessageLog

        # 查找适用于此账号的关键词（账号专属 或 全局）
        keywords = Keyword.query.filter(
            Keyword.is_active == True,
            db.or_(
                Keyword.account_id == account_id,
                Keyword.account_id == None
            )
        ).all()

        for keyword_rule in keywords:
            if keyword_rule.keyword.lower() not in text.lower():
                continue

            # 确定实际发送目标：优先使用规则中指定的目标群组
            if keyword_rule.target_group_id:
                group_id = keyword_rule.target_group_id
                send_group_name = keyword_rule.target_group_name or keyword_rule.target_group_id
            else:
                group_id = trigger_group_id
                send_group_name = group_name

            logger.info(
                f"[账号{account_id}] 关键词 '{keyword_rule.keyword}' "
                f"在 {group_name} 匹配，将发送至 {send_group_name}"
            )

            # 记录匹配日志
            match_log = MessageLog(
                account_id=account_id,
                group_id=group_id,
                group_name=send_group_name,
                log_type='keyword_matched',
                content=f'关键词: {keyword_rule.keyword}\n触发来源: {group_name}\n消息内容: {text[:500]}'
            )
            db.session.add(match_log)

            if keyword_rule.use_random_time:
                # 随机等待时间模式：在 [min, max] 秒内随机选取
                rmin = keyword_rule.random_min_seconds or 60
                rmax = keyword_rule.random_max_seconds or 300
                if rmin > rmax:
                    rmin, rmax = rmax, rmin
                total_wait = random.randint(rmin, rmax)
                scheduled_at = datetime.utcnow() + timedelta(seconds=total_wait)

                existing = PendingReply.query.filter_by(
                    account_id=account_id,
                    group_id=group_id,
                    keyword_id=keyword_rule.id,
                    is_sent=False
                ).first()
                triggered_by_text = (
                    f"关键词: {keyword_rule.keyword}, "
                    f"随机等待: {total_wait}s（区间 {rmin}~{rmax}s）, "
                    f"触发来源: {group_name}"
                )
                if existing:
                    existing.scheduled_at = scheduled_at
                    existing.triggered_by = triggered_by_text
                    logger.info(f"[随机时间] 更新待发回复，等待 {total_wait}s，新执行时间: {scheduled_at}")
                else:
                    pending = PendingReply(
                        account_id=account_id,
                        group_id=group_id,
                        keyword_id=keyword_rule.id,                        topic_id=keyword_rule.topic_id,                        message=keyword_rule.reply_message,
                        scheduled_at=scheduled_at,
                        triggered_by=triggered_by_text,
                    )
                    db.session.add(pending)
                    logger.info(
                        f"[随机时间] 已安排定时回复，等待 {format_seconds(total_wait)} 后发送至 {send_group_name}"
                    )

            elif keyword_rule.has_time_requirement:
                # 从消息中解析等待时间
                wait_seconds = parse_chinese_time(text)
                if wait_seconds is None:
                    logger.warning(
                        f"关键词 '{keyword_rule.keyword}' 需要时间但消息中未找到时间: {text[:100]}"
                    )
                    db.session.commit()
                    continue

                total_wait = wait_seconds + keyword_rule.time_buffer_seconds
                scheduled_at = datetime.utcnow() + timedelta(seconds=total_wait)

                # 检查是否已有相同规则的未发送回复（避免重复）
                existing = PendingReply.query.filter_by(
                    account_id=account_id,
                    group_id=group_id,
                    keyword_id=keyword_rule.id,
                    is_sent=False
                ).first()
                triggered_by_text = (
                    f"关键词: {keyword_rule.keyword}, "
                    f"解析时间: {format_seconds(wait_seconds)}, "
                    f"缓冲: {keyword_rule.time_buffer_seconds}s, "
                    f"触发来源: {group_name}"
                )
                if existing:
                    existing.scheduled_at = scheduled_at
                    existing.triggered_by = triggered_by_text
                    logger.info(f"更新已有待发回复，新执行时间: {scheduled_at}")
                else:
                    pending = PendingReply(
                        account_id=account_id,
                        group_id=group_id,
                        keyword_id=keyword_rule.id,                        topic_id=keyword_rule.topic_id,                        message=keyword_rule.reply_message,
                        scheduled_at=scheduled_at,
                        triggered_by=triggered_by_text,
                    )
                    db.session.add(pending)
                    logger.info(
                        f"已安排定时回复，等待 {format_seconds(total_wait)} 后发送至 {send_group_name}"
                    )

            else:
                # 无时间要求，立即回复
                try:
                    send_kwargs = {}
                    if keyword_rule.topic_id:
                        send_kwargs['reply_to'] = keyword_rule.topic_id
                    await client.send_message(int(group_id), keyword_rule.reply_message, **send_kwargs)
                    reply_log = MessageLog(
                        account_id=account_id,
                        group_id=group_id,
                        group_name=send_group_name,
                        log_type='auto_replied',
                        content=keyword_rule.reply_message
                    )
                    db.session.add(reply_log)
                    logger.info(f"已立即回复 {send_group_name}")
                except Exception as e:
                    logger.error(f"立即回复失败: {e}")
                    err_log = MessageLog(
                        account_id=account_id,
                        group_id=group_id,
                        group_name=send_group_name,
                        log_type='error',
                        content=f'立即回复失败: {e}'
                    )
                    db.session.add(err_log)

            db.session.commit()
            # 每条消息只匹配第一个关键词规则，避免重复触发
            break
