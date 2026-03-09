import logging
import logging.handlers
import time

from config import Config
from telegram_manager import TelegramManager
from web.app import create_app

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(
            'tgbot.log',
            maxBytes=5 * 1024 * 1024,  # 单文件最大 5 MB
            backupCount=3,             # 保留最近 3 个备份
            encoding='utf-8',
        ),
    ],
)


def main():
    # 初始化 Telegram 管理器
    manager = TelegramManager()

    # 创建 Flask 应用（传入 manager 引用）
    app = create_app(telegram_manager=manager)
    manager.app = app

    # 在后台线程中启动 asyncio 事件循环（Telethon + APScheduler）
    manager.init_loop()

    # 等待事件循环初始化完成
    time.sleep(2)

    # 启动 Flask Web 服务（主线程）
    logging.getLogger(__name__).info(
        f'Web 管理界面已启动: http://{Config.WEB_HOST}:{Config.WEB_PORT}'
    )
    app.run(
        host=Config.WEB_HOST,
        port=Config.WEB_PORT,
        debug=Config.DEBUG,
        use_reloader=False,   # 关闭 reloader，避免双进程冲突
    )


if __name__ == '__main__':
    main()
