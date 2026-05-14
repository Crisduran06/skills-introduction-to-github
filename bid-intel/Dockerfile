FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV AUTOSEED_FIXTURES=false
ENV AUTOFETCH_LIVE=true
ENV SCHEDULER_ENABLED=true
ENV FETCH_INTERVAL_HOURS=6

EXPOSE 7860

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
