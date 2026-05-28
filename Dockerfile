FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir poetry==1.8.3 \
 && poetry config virtualenvs.create false

COPY backend/pyproject.toml backend/poetry.lock ./

RUN poetry install --no-root --only main --no-interaction

COPY backend/app ./app

ENV PYTHONUNBUFFERED=1

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
