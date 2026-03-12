import asyncio
import logging
import threading
from datetime import datetime, timezone as _tz
from typing import Dict, Optional

from telethon import TelegramClient, events
from telethon.sessions import StringSession

logger = logging.getLogger(__name__)


class TelegramManager:
    """管理多个Telegram用户账号的核心类"""

    def __init__(self):
        self.clients: Dict[int, TelegramClient] = {}   # account_id -> client
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._pending_auth: Dict[str, dict] = {}        # phone -> {client, phone_code_hash}
        self.scheduler = None
        self.app = None   # Flask app，由外部注入

    # ------------------------------------------------------------------
    # 启动 / 停止
    # ------------------------------------------------------------------

    def init_loop(self):
        """在后台线程中启动独立的 asyncio 事件循环"""
        self.loop = asyncio.new_event_loop()
        thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name='TelegramLoop'
        )
        thread.start()
        return thread

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._init())
        self.loop.run_forever()

    async def _init(self):
        """初始化调度器，加载数据库中已授权的账号"""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        self.scheduler = AsyncIOScheduler(timezone='UTC')
        self.scheduler.start()

        # 每 30 秒检查一次待发回复
        self.scheduler.add_job(
            self._check_pending_replies,
            'interval',
            seconds=30,
            id='check_pending_replies'
        )

        await self._load_accounts()
        await self._reload_scheduled_tasks()

        # 每分钟重新加载定时任务（捕获 Web 端新增的任务）
        self.scheduler.add_job(
            self._reload_scheduled_tasks,
            'interval',
            minutes=1,
            id='reload_scheduled_tasks'
        )

        logger.info('TelegramManager 初始化完成')

    # ------------------------------------------------------------------
    # 账号管理
    # ------------------------------------------------------------------

    async def _load_accounts(self):
        """从数据库加载所有已授权的活跃账号"""
        with self.app.app_context():
            from models import Account
            accounts = Account.query.filter_by(is_active=True, status='authorized').all()
            for acc in accounts:
                await self._start_client(
                    acc.id, acc.phone, acc.api_id, acc.api_hash, acc.session_string
                )

    async def _start_client(
        self,
        account_id: int,
        phone: str,
        api_id: int,
        api_hash: str,
        session_string: str,
    ):
        """为指定账号启动 Telethon 客户端并注册消息监听"""
        if account_id in self.clients:
            try:
                await self.clients[account_id].disconnect()
            except Exception:
                pass

        try:
            client = TelegramClient(
                StringSession(session_string),
                api_id,
                api_hash,
            )
            await client.connect()

            if not await client.is_user_authorized():
                logger.warning(f'账号 {phone} 未授权，跳过启动')
                with self.app.app_context():
                    from models import db, Account
                    acc = Account.query.get(account_id)
                    if acc:
                        acc.status = 'error'
                        db.session.commit()
                return

            # 注册消息事件处理器
            @client.on(events.NewMessage(incoming=True))
            async def _on_message(event):
                await self._handle_incoming_message(account_id, client, event)

            self.clients[account_id] = client
            logger.info(f'账号 {phone} 客户端已启动')

        except Exception as e:
            logger.error(f'启动账号 {phone} 客户端失败: {e}')
            with self.app.app_context():
                from models import db, Account
                acc = Account.query.get(account_id)
                if acc:
                    acc.status = 'error'
                    db.session.commit()

    async def _handle_incoming_message(
        self, account_id: int, client: TelegramClient, event
    ):
        """
        处理收到的消息：
        仅当消息是对"我的消息"的回复时，才进行关键词检测
        """
        try:
            msg = event.message
            if not msg.reply_to_msg_id:
                return

            replied_msg = await event.get_reply_message()
            if replied_msg is None or not replied_msg.out:
                return  # 不是对我发出消息的回复

            from message_handler import check_keywords
            await check_keywords(self, account_id, client, event, msg, replied_msg)

        except Exception as e:
            logger.error(f'处理消息时出错: {e}')

    async def reload_account(self, account_id: int):
        """重新加载指定账号（Web 端授权后调用）"""
        with self.app.app_context():
            from models import Account
            acc = Account.query.get(account_id)
            if acc and acc.is_active and acc.status == 'authorized' and acc.session_string:
                await self._start_client(
                    acc.id, acc.phone, acc.api_id, acc.api_hash, acc.session_string
                )

    async def disconnect_account(self, account_id: int):
        """断开指定账号"""
        if account_id in self.clients:
            try:
                await self.clients[account_id].disconnect()
            except Exception:
                pass
            del self.clients[account_id]
            logger.info(f'账号 {account_id} 已断开')

    # ------------------------------------------------------------------
    # 身份验证（供 Web 端调用）
    # ------------------------------------------------------------------

    async def send_code_request(self, phone: str, api_id: int, api_hash: str):
        """向指定手机号发送登录验证码"""
        client = TelegramClient(StringSession(), api_id, api_hash)
        await client.connect()
        result = await client.send_code_request(phone)
        self._pending_auth[phone] = {
            'client': client,
            'phone_code_hash': result.phone_code_hash,
        }
        logger.info(f'验证码已发送至 {phone}')
        return result

    async def sign_in(self, phone: str, code: str, password: str = None) -> str:
        """
        用验证码完成登录，返回 session_string。
        若账号开启了两步验证，需传入 password。
        """
        from telethon.errors import SessionPasswordNeededError

        auth = self._pending_auth.get(phone)
        if not auth:
            raise ValueError(f'未找到 {phone} 的待验证登录，请先发送验证码')

        client: TelegramClient = auth['client']
        try:
            await client.sign_in(phone, code)
        except SessionPasswordNeededError:
            if password:
                await client.sign_in(password=password)
            else:
                raise ValueError('该账号开启了两步验证，请同时填写密码')

        session_string = client.session.save()
        del self._pending_auth[phone]
        logger.info(f'账号 {phone} 登录成功')
        return session_string

    # ------------------------------------------------------------------
    # 定时任务
    # ------------------------------------------------------------------

    async def _reload_scheduled_tasks(self):
        """从数据库重新加载所有定时发送任务，支持断点续时"""
        try:
            with self.app.app_context():
                from models import db, ScheduledTask
                tasks = ScheduledTask.query.filter_by(is_active=True).all()
                task_ids = set()
                needs_commit = False

                for task in tasks:
                    job_id = f'task_{task.id}'
                    task_ids.add(job_id)

                    if task.account_id not in self.clients:
                        continue

                    existing_job = self.scheduler.get_job(job_id)
                    if existing_job:
                        # 将 APScheduler 当前的下次运行时间同步回数据库（每分钟触发一次）
                        if existing_job.next_run_time:
                            nrt = existing_job.next_run_time
                            if nrt.tzinfo is not None:
                                nrt = nrt.astimezone(_tz.utc).replace(tzinfo=None)
                            task.next_run_at = nrt
                            needs_commit = True
                        continue

                    # ---- 任务不存在（首次启动或重启后重建） ----
                    now = datetime.utcnow()
                    args = [task.account_id, task.group_id, task.message, task.topic_id,
                            task.random_delay_min or 0, task.random_delay_max or 0]

                    if task.task_type == 'interval' and task.interval_minutes:
                        job_kwargs = dict(
                            minutes=task.interval_minutes,
                            id=job_id,
                            args=args,
                            replace_existing=True,
                        )
                        # 断点续时：若上次记录的下次运行时间还在未来，直接用它作为起始时间
                        if task.next_run_at and task.next_run_at > now:
                            job_kwargs['start_date'] = task.next_run_at
                            logger.info(
                                f'断点恢复间隔任务 task_{task.id}，'
                                f'将于 {task.next_run_at} 继续执行'
                            )
                        else:
                            logger.info(
                                f'已注册间隔任务 task_{task.id}，'
                                f'每 {task.interval_minutes} 分钟发送一次'
                            )
                        self.scheduler.add_job(
                            self._send_scheduled_message,
                            'interval',
                            **job_kwargs,
                        )

                    elif task.task_type == 'cron' and task.cron_expression:
                        parts = task.cron_expression.strip().split()
                        if len(parts) == 5:
                            minute, hour, day, month, dow = parts
                            self.scheduler.add_job(
                                self._send_scheduled_message,
                                'cron',
                                minute=minute,
                                hour=hour,
                                day=day,
                                month=month,
                                day_of_week=dow,
                                id=job_id,
                                args=args,
                                replace_existing=True,
                            )
                            logger.info(
                                f'已注册 cron 任务 task_{task.id}: {task.cron_expression}'
                            )

                if needs_commit:
                    db.session.commit()

                # 移除数据库中已禁用或删除的任务
                for job in self.scheduler.get_jobs():
                    if job.id.startswith('task_') and job.id not in task_ids:
                        self.scheduler.remove_job(job.id)

        except Exception as e:
            logger.error(f'重新加载定时任务失败: {e}')

    async def remove_task_job(self, task_id: int):
        """移除指定定时任务的调度（供 Web 端调用）"""
        job_id = f'task_{task_id}'
        if self.scheduler and self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

    async def _send_scheduled_message(
        self, account_id: int, group_id: str, message: str, topic_id: int = None,
        random_delay_min: int = 0, random_delay_max: int = 0,
        task_id: int = None, interval_minutes: int = 0
    ):
        """执行定时发送，可附加随机延迟，并记录 last_run_at 用于断点续时"""
        import random
        if random_delay_min > 0 and random_delay_max >= random_delay_min:
            delay = random.randint(random_delay_min, random_delay_max)
            logger.info(f'定时任务随机延迟 {delay} 秒后发送至群 {group_id}')
            await asyncio.sleep(delay)
        client = self.clients.get(account_id)
        if client is None:
            logger.warning(f'定时任务：账号 {account_id} 未连接，跳过')
            return
        try:
            send_kwargs = {}
            if topic_id:
                send_kwargs['reply_to'] = topic_id
            await client.send_message(int(group_id), message, **send_kwargs)
            logger.info(f'定时消息已发送至群 {group_id}')
            with self.app.app_context():
                from models import db, MessageLog, ScheduledTask
                # 记录本次实际执行时间，供下次重启断点续时使用
                if task_id:
                    task = ScheduledTask.query.get(task_id)
                    if task:
                        task.last_run_at = datetime.utcnow()
                        db.session.commit()
                log = MessageLog(
                    account_id=account_id,
                    group_id=group_id,
                    log_type='scheduled_sent',
                    content=message,
                )
                db.session.add(log)
                db.session.commit()
        except Exception as e:
            logger.error(f'定时消息发送失败: {e}')

    async def _check_pending_replies(self):
        """轮询检查到期的待发回复，保证同一目标按时序发送，失败自动重试"""
        try:
            with self.app.app_context():
                from models import db, PendingReply, MessageLog
                now = datetime.utcnow()
                # 按计划时间升序，确保同目标多条消息按正确顺序发出
                due = PendingReply.query.filter(
                    PendingReply.scheduled_at <= now,
                    PendingReply.is_sent == False,
                ).order_by(PendingReply.scheduled_at.asc()).all()

                # 记录本次批次内各目标的最后实际发送时刻，用于控制发送间隔
                last_sent_to = {}   # key: (account_id, group_id)  value: datetime

                for reply in due:
                    client = self.clients.get(reply.account_id)
                    if client is None:
                        continue

                    # ── 同目标间隔保障 ──────────────────────────────────────
                    target_key = (reply.account_id, reply.group_id)
                    if target_key in last_sent_to:
                        elapsed = (datetime.utcnow() - last_sent_to[target_key]).total_seconds()
                        if elapsed < 10:
                            await asyncio.sleep(10 - elapsed)
                    # ───────────────────────────────────────────────────────

                    try:
                        send_kwargs = {}
                        if reply.topic_id:
                            send_kwargs['reply_to'] = reply.topic_id
                        await client.send_message(int(reply.group_id), reply.message, **send_kwargs)
                        reply.is_sent = True
                        reply.sent_at = datetime.utcnow()
                        last_sent_to[target_key] = reply.sent_at

                        log = MessageLog(
                            account_id=reply.account_id,
                            group_id=reply.group_id,
                            log_type='auto_replied',
                            content=reply.message,
                        )
                        db.session.add(log)
                        db.session.commit()
                        logger.info(f'待发回复已发送至群 {reply.group_id}')
                    except Exception as e:
                        # 发送失败：将该消息重新推迟 10 秒入队，等待下次重试
                        logger.error(f'发送待发回复失败: {e}，已重新入队 10 秒后重试')
                        reply.scheduled_at = datetime.utcnow() + timedelta(seconds=10)
                        err_log = MessageLog(
                            account_id=reply.account_id,
                            group_id=reply.group_id,
                            log_type='error',
                            content=f'发送失败，已重新入队 10 秒后重试: {e}',
                        )
                        db.session.add(err_log)
                        db.session.commit()
        except Exception as e:
            logger.error(f'检查待发回复时出错: {e}')

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def submit(self, coro):
        """将协程提交到 Telegram 事件循环（供同步的 Flask 代码调用）"""
        if self.loop is None:
            raise RuntimeError('事件循环尚未启动')
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    @property
    def connected_accounts(self) -> list:
        return list(self.clients.keys())
