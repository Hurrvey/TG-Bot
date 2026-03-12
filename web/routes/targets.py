from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from models import db, TargetEntity, Account

targets_bp = Blueprint('targets', __name__)


def upsert_target(entity_id: str, name: str = '', entity_type: str = 'unknown',
                  note: str = '', topic_id: int = None):
    """创建或更新目标记录（幂等），entity_id 唯一键。"""
    if not entity_id:
        return
    existing = TargetEntity.query.filter_by(entity_id=str(entity_id)).first()
    if existing:
        if name and not existing.name:
            existing.name = name
        if entity_type and entity_type != 'unknown':
            existing.entity_type = entity_type
        if note and not existing.note:
            existing.note = note
        if topic_id and not existing.topic_id:
            existing.topic_id = topic_id
    else:
        db.session.add(TargetEntity(
            entity_id=str(entity_id),
            name=name or '',
            entity_type=entity_type or 'unknown',
            note=note or '',
            topic_id=topic_id,
        ))
    db.session.commit()


@targets_bp.route('/')
def index():
    targets = TargetEntity.query.order_by(TargetEntity.created_at.desc()).all()
    accounts = Account.query.filter_by(status='authorized').all()
    return render_template('targets.html', targets=targets, accounts=accounts)


@targets_bp.route('/api')
def api_list():
    """返回目标列表 JSON，供前端下拉选择使用"""
    targets = TargetEntity.query.order_by(TargetEntity.name).all()
    return jsonify([t.to_dict() for t in targets])


@targets_bp.route('/add', methods=['POST'])
def add():
    entity_id = request.form.get('entity_id', '').strip()
    name = request.form.get('name', '').strip()
    entity_type = request.form.get('entity_type', 'unknown')
    note = request.form.get('note', '').strip()
    topic_id_raw = request.form.get('topic_id', '').strip()
    topic_id = int(topic_id_raw) if topic_id_raw.lstrip('-').isdigit() else None

    if not entity_id:
        flash('目标 ID 为必填项', 'danger')
        return redirect(url_for('targets.index'))

    upsert_target(entity_id, name, entity_type, note, topic_id)
    flash(f'已保存目标 {name or entity_id}', 'success')
    return redirect(url_for('targets.index'))


@targets_bp.route('/<int:target_id>/delete', methods=['POST'])
def delete(target_id):
    t = TargetEntity.query.get_or_404(target_id)
    name = t.name or t.entity_id
    db.session.delete(t)
    db.session.commit()
    flash(f'已删除目标 {name}', 'success')
    return redirect(url_for('targets.index'))
