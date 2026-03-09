from flask import Flask
from config import Config
from models import db


def create_app(telegram_manager=None):
    app = Flask(__name__, template_folder='templates')
    app.config['SQLALCHEMY_DATABASE_URI'] = Config.DATABASE_URL
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = Config.SECRET_KEY

    db.init_app(app)

    # 将 telegram_manager 注入到 app 上，供路由使用
    app.telegram_manager = telegram_manager

    with app.app_context():
        db.create_all()

    from web.routes.main import main_bp
    from web.routes.accounts import accounts_bp
    from web.routes.keywords import keywords_bp
    from web.routes.tasks import tasks_bp
    from web.routes.logs import logs_bp
    from web.routes.whitelist import whitelist_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(accounts_bp, url_prefix='/accounts')
    app.register_blueprint(keywords_bp, url_prefix='/keywords')
    app.register_blueprint(tasks_bp, url_prefix='/tasks')
    app.register_blueprint(logs_bp, url_prefix='/logs')
    app.register_blueprint(whitelist_bp, url_prefix='/whitelist')

    return app
