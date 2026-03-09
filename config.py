import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///tgbot.db')
    WEB_HOST = os.getenv('WEB_HOST', '127.0.0.1')
    WEB_PORT = int(os.getenv('WEB_PORT', 5000))
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
