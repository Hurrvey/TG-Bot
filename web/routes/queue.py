from datetime import datetime, timezone
from flask import Blueprint, render_template, jsonify, request, current_app
from models import db, PendingReply, ScheduledTask, Account, TargetEntity

queue_bp = Blueprint('queue', __name__)


@queue_bp.route('/')
def index():
    return render_template('queue.html')


@queue_bp.route('/api')
def api():
    """返回所有等待发送任务的 JSON 数据，包含剩余秒数"""
    now = datetime.utcnow()
    result = []

    # --- 1. 关键词触发的待发回复 (PendingReply) ---
    pending_replies = (
        PendingReply.query
        .filter_by(is_sent=False)
        .order_by(PendingReply.scheduled_at)
        .all()
    )
    # 构建 account_id -> name 映射
    account_map = {a.id: a.name for a in Account.query.all()}
    # 构建 entity_id -> name 映射（用于 pending_reply 的 group_name）
    target_map = {t.entity_id: t.name for t in TargetEntity.query.all()}

    for r in pending_replies:
        remaining = (r.scheduled_at - now).total_seconds()
        result.append({
            'type': 'pending_reply',
            'type_label': '关键词回复',
            'id': r.id,
            'account': account_map.get(r.account_id, str(r.account_id)),
            'group_id': r.group_id,
            'group_name': target_map.get(r.group_id, ''),
            'topic_id': r.topic_id,
            'message': r.message[:80] + ('…' if len(r.message) > 80 else ''),
            'scheduled_at': r.scheduled_at.strftime('%Y-%m-%d %H:%M:%S UTC'),
            'remaining_seconds': max(0, int(remaining)),
            'triggered_by': r.triggered_by or '',
        })

    # --- 2. 定时任务 (ScheduledTask) 的下次运行时间 ---
    manager = current_app.telegram_manager
    tasks = ScheduledTask.query.filter_by(is_active=True).order_by(ScheduledTask.id).all()
    for task in tasks:
        next_run = None
        remaining_sec = None
        if manager and manager.scheduler:
            job = manager.scheduler.get_job(f'task_{task.id}')
            if job and job.next_run_time:
                # next_run_time 是带时区的 datetime，统一转换为 UTC naive 做差值
                nrt = job.next_run_time
                if nrt.tzinfo is not None:
                    nrt_utc = nrt.astimezone(timezone.utc).replace(tzinfo=None)
                else:
                    nrt_utc = nrt
                remaining_sec = max(0, int((nrt_utc - now).total_seconds()))
                next_run = nrt.strftime('%Y-%m-%d %H:%M:%S %Z')

        task_info = task.task_type
        if task.task_type == 'interval' and task.interval_minutes:
            task_info = f'每 {task.interval_minutes} 分钟'
        elif task.task_type == 'cron' and task.cron_expression:
            task_info = f'Cron: {task.cron_expression}'

        result.append({
            'type': 'scheduled_task',
            'type_label': '定时任务',
            'id': task.id,
            'account': account_map.get(task.account_id, str(task.account_id)),
            'group_id': task.group_id,
            'group_name': task.group_name or '',
            'topic_id': task.topic_id,
            'message': task.message[:80] + ('…' if len(task.message) > 80 else ''),
            'task_info': task_info,
            'scheduled_at': next_run or '—',
            'remaining_seconds': remaining_sec,  # None 表示未加载到 scheduler
            'random_delay': (
                f'+{task.random_delay_min}~{task.random_delay_max}s 随机延迟'
                if (task.random_delay_max or 0) > 0 else ''
            ),
        })

    # 按剩余秒数排序（None 排末尾）
    result.sort(key=lambda x: x['remaining_seconds'] if x['remaining_seconds'] is not None else 999999)
    return jsonify(result)


@queue_bp.route('/api/delete', methods=['POST'])
def delete_items():
    """删除指定的待发送任务（支持 pending_reply 类型）"""
    data = request.get_json(silent=True)
    if not data or 'items' not in data:
        return jsonify({'error': '缺少 items 参数'}), 400

    items = data['items']
    deleted = 0
    for item in items:
        item_type = item.get('type')
        item_id = item.get('id')
        if not item_type or not item_id:
            continue
        if item_type == 'pending_reply':
            row = PendingReply.query.filter_by(id=item_id, is_sent=False).first()
            if row:
                db.session.delete(row)
                deleted += 1

    db.session.commit()
    return jsonify({'deleted': deleted})


@queue_bp.route('/api/clear', methods=['POST'])
def clear_all():
    """清空所有未发送的 pending_reply"""
    deleted = PendingReply.query.filter_by(is_sent=False).delete()
    db.session.commit()
    return jsonify({'deleted': deleted})
