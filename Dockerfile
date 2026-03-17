FROM python:3.12-slim

WORKDIR /app

# 安装依赖（利用 Docker 层缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 数据库 + 日志持久化目录
VOLUME ["/app/instance", "/app/logs"]

EXPOSE 5000

CMD ["python", "main.py"]
