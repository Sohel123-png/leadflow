
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Run migrations, create missing demo users without adding fake leads,
# then start FastAPI on Render's assigned port.
CMD ["sh", "-c", "alembic upgrade head && python -m scripts.seed --leads 0 && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
