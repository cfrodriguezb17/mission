FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --create-home datapulse && chown -R datapulse:datapulse /app
USER datapulse
EXPOSE 8000
CMD ["sh", "deployment/start.sh"]
