from flask import Blueprint, render_template, current_app
from models import Account, Keyword, ScheduledTask, PendingReply, MessageLog

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    manager = current_app.telegram_manager
    total_accounts = Account.query.count()
    active_accounts = Account.query.filter_by(is_active=True, status='authorized').count()
    connected = len(manager.connected_accounts) if manager else 0
    total_keywords = Keyword.query.filter_by(is_active=True).count()
    total_tasks = ScheduledTask.query.filter_by(is_active=True).count()
    pending_replies = PendingReply.query.filter_by(is_sent=False).count()
    recent_logs = MessageLog.query.order_by(MessageLog.created_at.desc()).limit(20).all()

    return render_template(
        'index.html',
        total_accounts=total_accounts,
        active_accounts=active_accounts,
        connected=connected,
        total_keywords=total_keywords,
        total_tasks=total_tasks,
        pending_replies=pending_replies,
        recent_logs=recent_logs,
    )
