from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify
from models import db, Account

accounts_bp = Blueprint('accounts', __name__)


@accounts_bp.route('/<int:account_id>/dialogs/<group_id>/topics')
def topics(account_id, group_id):
    """使用 GetForumTopicsRequest 直接获取 Forum 话题列表（含官方标题）"""
    manager = current_app.telegram_manager
    account = Account.query.get_or_404(account_id)

    if account_id not in manager.connected_accounts:
        return jsonify({'error': '账号未连接'}), 400

    async def _get_topics():
        from telethon.tl.functions.messages import GetForumTopicsRequest
        client = manager.clients[account_id]
        try:
            entity = await client.get_entity(int(group_id))
        except Exception as e:
            return {'error': f'获取群组失败: {e}'}

        if not getattr(entity, 'forum', False):
            return {'topics': [], 'is_forum': False}

        topics = []
        offset_date = None
        offset_id = 0
        offset_topic = 0
        limit = 100

        while True:
            result = await client(GetForumTopicsRequest(
                peer=entity,
                offset_date=offset_date,
                offset_id=offset_id,
                offset_topic=offset_topic,
                limit=limit,
                q=None,
            ))
            for t in result.topics:
                # ForumTopic.id, ForumTopic.title
                tid = getattr(t, 'id', None)
                title = getattr(t, 'title', None)
                if tid is not None and title is not None:
                    topics.append({'id': tid, 'title': title})
            if not result.topics or len(result.topics) < limit:
                break
            # 翻页：用最后一个话题的信息继续
            last = result.topics[-1]
            offset_topic = getattr(last, 'id', offset_topic)
            offset_date = getattr(last, 'date', offset_date)
            offset_id = getattr(last, 'top_message', offset_id)

        # 按 id 排序，id=1 的通用话题排首位
        topics.sort(key=lambda x: x['id'])
        # 为 id=1 的话题补充括号说明（如果后端返回的标题较短）
        for t in topics:
            if t['id'] == 1 and '默认' not in t['title'] and '通用' not in t['title']:
                t['title'] = t['title'] + '（默认话题）'

        return {'topics': topics, 'is_forum': True}

    try:
        future = manager.submit(_get_topics())
        result = future.result(timeout=40)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@accounts_bp.route('/<int:account_id>/resolve/<target_id>')
def resolve_entity(account_id, target_id):
    """解析任意 Telegram 实体（用户/机器人/群组/频道），返回类型、名称和是否 Forum"""
    manager = current_app.telegram_manager
    account = Account.query.get_or_404(account_id)

    if account_id not in manager.connected_accounts:
        return jsonify({'error': '账号未连接'}), 400

    async def _resolve():
        client = manager.clients[account_id]
        try:
            try:
                eid = int(target_id)
            except ValueError:
                eid = target_id
            entity = await client.get_entity(eid)
        except Exception as e:
            return {'error': f'无法解析: {e}'}

        etype = type(entity).__name__
        is_forum = getattr(entity, 'forum', False)
        is_bot = getattr(entity, 'bot', False)
        is_megagroup = getattr(entity, 'megagroup', False)

        if etype == 'User':
            kind = 'bot' if is_bot else 'user'
        elif etype == 'Chat':
            kind = 'group'
        elif etype == 'Channel':
            kind = 'supergroup' if is_megagroup else 'channel'
        else:
            kind = 'unknown'

        first = getattr(entity, 'first_name', '') or ''
        last = getattr(entity, 'last_name', '') or ''
        title = getattr(entity, 'title', None)
        name = title or f'{first} {last}'.strip() or target_id

        return {'kind': kind, 'name': name, 'is_forum': is_forum, 'id': entity.id}

    try:
        future = manager.submit(_resolve())
        result = future.result(timeout=15)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@accounts_bp.route('/<int:account_id>/dialogs')
def dialogs(account_id):
    """获取指定账号所在的群组/频道列表（含 ID）"""
    manager = current_app.telegram_manager
    account = Account.query.get_or_404(account_id)

    if account_id not in manager.connected_accounts:
        return jsonify({'error': f'账号 {account.name} 未连接，请先确认已授权且在线'}), 400

    async def _get_dialogs():
        client = manager.clients[account_id]
        result = []
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            entity_type = type(entity).__name__
            # 只返回群组和频道，过滤掉私聊
            if entity_type in ('Chat', 'Channel'):
                result.append({
                    'name': dialog.name,
                    'id': dialog.id,
                    'type': 'Channel' if entity_type == 'Channel' else 'Group',
                    'is_forum': getattr(entity, 'forum', False),
                })
        return result

    try:
        future = manager.submit(_get_dialogs())
        groups = future.result(timeout=30)
        return jsonify({'groups': groups})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@accounts_bp.route('/')
def index():
    accounts = Account.query.order_by(Account.created_at.desc()).all()
    manager = current_app.telegram_manager
    connected_ids = manager.connected_accounts if manager else []
    return render_template('accounts.html', accounts=accounts, connected_ids=connected_ids)


@accounts_bp.route('/add', methods=['POST'])
def add():
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    api_id = request.form.get('api_id', '').strip()
    api_hash = request.form.get('api_hash', '').strip()

    if not all([name, phone, api_id, api_hash]):
        flash('所有字段均为必填项', 'danger')
        return redirect(url_for('accounts.index'))

    if not api_id.isdigit():
        flash('API ID 必须是数字', 'danger')
        return redirect(url_for('accounts.index'))

    if Account.query.filter_by(phone=phone).first():
        flash(f'手机号 {phone} 已存在', 'warning')
        return redirect(url_for('accounts.index'))

    account = Account(
        name=name,
        phone=phone,
        api_id=int(api_id),
        api_hash=api_hash,
        status='pending',
    )
    db.session.add(account)
    db.session.commit()
    flash('账号已添加，请完成登录授权', 'success')
    return redirect(url_for('accounts.auth', account_id=account.id))


@accounts_bp.route('/<int:account_id>/auth')
def auth(account_id):
    account = Account.query.get_or_404(account_id)
    return render_template('account_auth.html', account=account)


@accounts_bp.route('/<int:account_id>/send_code', methods=['POST'])
def send_code(account_id):
    account = Account.query.get_or_404(account_id)
    manager = current_app.telegram_manager

    if manager is None:
        flash('Telegram 管理器未启动', 'danger')
        return redirect(url_for('accounts.auth', account_id=account_id))

    try:
        future = manager.submit(
            manager.send_code_request(account.phone, account.api_id, account.api_hash)
        )
        future.result(timeout=30)
        flash('验证码已发送，请查收短信或 Telegram 应用中的通知', 'success')
    except Exception as e:
        flash(f'发送验证码失败: {e}', 'danger')

    return redirect(url_for('accounts.auth', account_id=account_id))


@accounts_bp.route('/<int:account_id>/verify', methods=['POST'])
def verify(account_id):
    account = Account.query.get_or_404(account_id)
    code = request.form.get('code', '').strip()
    password = request.form.get('password', '').strip() or None
    manager = current_app.telegram_manager

    if not code:
        flash('请输入验证码', 'danger')
        return redirect(url_for('accounts.auth', account_id=account_id))

    try:
        future = manager.submit(manager.sign_in(account.phone, code, password))
        session_string = future.result(timeout=30)

        account.session_string = session_string
        account.status = 'authorized'
        db.session.commit()

        # 启动该账号的 Telethon 客户端
        manager.submit(manager.reload_account(account.id))

        flash('授权成功！账号已开始运行', 'success')
        return redirect(url_for('accounts.index'))
    except Exception as e:
        flash(f'验证失败: {e}', 'danger')
        return redirect(url_for('accounts.auth', account_id=account_id))


@accounts_bp.route('/<int:account_id>/toggle', methods=['POST'])
def toggle(account_id):
    account = Account.query.get_or_404(account_id)
    manager = current_app.telegram_manager
    account.is_active = not account.is_active
    db.session.commit()

    if account.is_active and account.status == 'authorized':
        manager.submit(manager.reload_account(account.id))
        flash(f'账号 {account.name} 已启用', 'success')
    else:
        manager.submit(manager.disconnect_account(account.id))
        flash(f'账号 {account.name} 已停用', 'warning')

    return redirect(url_for('accounts.index'))


@accounts_bp.route('/<int:account_id>/delete', methods=['POST'])
def delete(account_id):
    account = Account.query.get_or_404(account_id)
    manager = current_app.telegram_manager

    manager.submit(manager.disconnect_account(account.id))
    db.session.delete(account)
    db.session.commit()
    flash(f'账号 {account.name} 已删除', 'success')
    return redirect(url_for('accounts.index'))


@accounts_bp.route('/<int:account_id>/schedule', methods=['POST'])
def schedule(account_id):
    """保存账号的托管时间设置"""
    account = Account.query.get_or_404(account_id)
    account.schedule_enabled = request.form.get('schedule_enabled') == 'on'
    start = request.form.get('schedule_start', '18:00').strip()
    end = request.form.get('schedule_end', '08:00').strip()
    # 简单格式校验
    import re
    if re.match(r'^\d{2}:\d{2}$', start):
        account.schedule_start = start
    if re.match(r'^\d{2}:\d{2}$', end):
        account.schedule_end = end
    db.session.commit()
    status = f'{start} \u2013 {end}' if account.schedule_enabled else '全天托管'
    flash(f'账号 {account.name} 托管时间已设置（{status}）', 'success')
    return redirect(url_for('accounts.index'))
