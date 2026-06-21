FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY kernel ./kernel
COPY backend ./backend
COPY worker ./worker
COPY migrations ./migrations
COPY alembic.ini ./
RUN pip install --no-cache-dir -e .
CMD ["dramatiq", "worker.main", "--processes", "1", "--threads", "2"]
