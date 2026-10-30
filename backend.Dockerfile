FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/backend
COPY backend/requirements.txt ./
COPY requirements-lock.txt ./constraints.txt
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt
COPY backend/ ./
RUN useradd --create-home app && mkdir -p data && chown -R app:app /app
USER app
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
