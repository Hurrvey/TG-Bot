from flask import Blueprint, render_template, request
from models import MessageLog, Account, PendingReply

logs_bp = Blueprint('logs', __name__)


@logs_bp.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    account_id = request.args.get('account_id', type=int)
    log_type = request.args.get('log_type', '')

    query = MessageLog.query
    if account_id:
        query = query.filter_by(account_id=account_id)
    if log_type:
        query = query.filter_by(log_type=log_type)

    logs = query.order_by(MessageLog.created_at.desc()).paginate(
        page=page, per_page=50, error_out=False
    )
    accounts = Account.query.all()
    pending = PendingReply.query.filter_by(is_sent=False).order_by(
        PendingReply.scheduled_at
    ).all()

    log_types = [
        'keyword_matched', 'auto_replied', 'scheduled_sent', 'error'
    ]

    return render_template(
        'logs.html',
        logs=logs,
        accounts=accounts,
        pending=pending,
        log_types=log_types,
        current_account_id=account_id,
        current_log_type=log_type,
    )
