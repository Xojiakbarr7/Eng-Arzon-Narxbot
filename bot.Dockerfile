FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY bot/requirements.txt ./requirements.txt
COPY requirements-lock.txt ./constraints.txt
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt
COPY bot/ ./bot/
RUN useradd --create-home app && chown -R app:app /app
USER app
CMD ["python", "-m", "bot.main"]
