from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import get_setting, set_setting

settings_bp = Blueprint('settings', __name__)


@settings_bp.route('/')
def index():
    settings = {
        'smart_dedup_enabled': get_setting('smart_dedup_enabled', 'false'),
        'smart_dedup_threshold_minutes': get_setting('smart_dedup_threshold_minutes', '60'),
    }
    return render_template('settings.html', settings=settings)


@settings_bp.route('/save', methods=['POST'])
def save():
    # 智能去重开关
    enabled = 'true' if request.form.get('smart_dedup_enabled') == 'on' else 'false'
    set_setting('smart_dedup_enabled', enabled)

    # 时间阈值
    threshold = request.form.get('smart_dedup_threshold_minutes', '60').strip()
    try:
        threshold = str(max(1, int(threshold)))
    except ValueError:
        threshold = '60'
    set_setting('smart_dedup_threshold_minutes', threshold)

    flash('设置已保存', 'success')
    return redirect(url_for('settings.index'))
