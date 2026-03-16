import logging
import random
from datetime import datetime, timedelta

from time_parser import parse_chinese_time, format_seconds

logger = logging.getLogger(__name__)

# 同一目标两条消息之间的最短间隔（秒）
SEND_GAP_SECONDS = 10


def _find_send_slot(
    account_id: int, group_id: str, desired_at,
    gap_seconds: int = SEND_GAP_SECONDS, exclude_id: int = None
):
    """
    贪心时间槽算法：为新待发消息找到不与同目标已有消息冲突的最早时间槽。

    对同一 (account_id, group_id) 的未发送消息按计划时间升序遍历，
    若当前 slot 与某已有时间的差值 < gap_seconds，则将 slot 推后至
    该时间 + gap_seconds，继续扫描，直到无冲突为止。

    时间复杂度 O(n)，n 为该目标未发送消息数（实际极小）。
    exclude_id: 更新已有记录时，排除该记录自身避免自比较。
    """
    from datetime import timedelta
    from models import PendingReply

    query = PendingReply.query.filter(
        PendingReply.account_id == account_id,
        PendingReply.group_id == group_id,
        PendingReply.is_sent == False,
        PendingReply.scheduled_at >= desired_at - timedelta(seconds=gap_seconds),
    )
    if exclude_id is not None:
        query = query.filter(PendingReply.id != exclude_id)
    existing = query.order_by(PendingReply.scheduled_at.asc()).all()

    slot = desired_at
    for reply in existing:
        e = reply.scheduled_at
        if e < slot - timedelta(seconds=gap_seconds):
            continue  # 远在 slot 之前，无冲突
        if e >= slot + timedelta(seconds=gap_seconds):
            break     # 恰好满足或超过间隔要求，无冲突，终止扫描
        # 冲突（距离 < gap_seconds）：将 slot 推后至该消息之后
        slot = e + timedelta(seconds=gap_seconds)

    return slot


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


async def check_keywords(manager, account_id: int, client, event, msg, replied_msg,
                         *, is_reply_to_me=False, is_mentioned=False):
    """
    检测消息中的关键词，根据规则自动回复。

    支持三种触发模式（per-rule）：
      - reply_to_me: 有人引用我的消息时检测
      - mention_me: 有人 @提及我时检测
      - all_messages: 所有收到的消息均检测
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
                    if is_reply_to_me:
                        trigger_desc = '有人引用了你的消息'
                    elif is_mentioned:
                        trigger_desc = '有人@提及了你'
                    else:
                        trigger_desc = '检测到消息'
                    await client.send_message(
                        'me',
                        f"\u23f0 非托管时段 ({_account.schedule_start} \u2013 {_account.schedule_end})\n\n"
                        f"{trigger_desc}，关键词规则\u672a\u89e6\u53d1\u3002\n\n"
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
            # 检查触发模式是否匹配当前消息类型
            mode = keyword_rule.trigger_mode or 'reply_to_me'
            if mode == 'reply_to_me' and not is_reply_to_me:
                continue
            if mode == 'mention_me' and not is_mentioned:
                continue
            # mode == 'all_messages' → 不跳过

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
                    # 更新时排除自身，避免与自己比较产生误判
                    scheduled_at = _find_send_slot(
                        account_id, group_id, scheduled_at, exclude_id=existing.id
                    )
                    existing.scheduled_at = scheduled_at
                    existing.triggered_by = triggered_by_text
                    logger.info(f"[随机时间] 更新待发回复，等待 {total_wait}s，调整后执行时间: {scheduled_at}")
                else:
                    scheduled_at = _find_send_slot(account_id, group_id, scheduled_at)
                    pending = PendingReply(
                        account_id=account_id,
                        group_id=group_id,
                        keyword_id=keyword_rule.id,                        topic_id=keyword_rule.topic_id,                        message=keyword_rule.reply_message,
                        scheduled_at=scheduled_at,
                        triggered_by=triggered_by_text,
                    )
                    db.session.add(pending)
                    logger.info(
                        f"[随机时间] 已安排定时回复，调整后执行时间: {scheduled_at}，发送至 {send_group_name}"
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

                # 计算实际缓冲：随机区间优先，否则用固定值
                buf_rmin = keyword_rule.buffer_random_min or 0
                buf_rmax = keyword_rule.buffer_random_max or 0
                if buf_rmax > 0 and buf_rmax >= buf_rmin:
                    buffer_used = random.randint(buf_rmin, buf_rmax)
                    buffer_desc = f'随机缓冲: {buffer_used}s（区间 {buf_rmin}~{buf_rmax}s）'
                else:
                    buffer_used = keyword_rule.time_buffer_seconds
                    buffer_desc = f'固定缓冲: {buffer_used}s'
                total_wait = wait_seconds + buffer_used
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
                    f"{buffer_desc}, "
                    f"触发来源: {group_name}"
                )
                if existing:
                    # 更新时排除自身，避免与自己比较产生误判
                    scheduled_at = _find_send_slot(
                        account_id, group_id, scheduled_at, exclude_id=existing.id
                    )
                    existing.scheduled_at = scheduled_at
                    existing.triggered_by = triggered_by_text
                    logger.info(f"更新已有待发回复，调整后执行时间: {scheduled_at}")
                else:
                    scheduled_at = _find_send_slot(account_id, group_id, scheduled_at)
                    pending = PendingReply(
                        account_id=account_id,
                        group_id=group_id,
                        keyword_id=keyword_rule.id,                        topic_id=keyword_rule.topic_id,                        message=keyword_rule.reply_message,
                        scheduled_at=scheduled_at,
                        triggered_by=triggered_by_text,
                    )
                    db.session.add(pending)
                    logger.info(
                        f"已安排定时回复，调整后执行时间: {scheduled_at}，发送至 {send_group_name}"
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
