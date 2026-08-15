FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY cloud/requirements.txt /app/cloud/requirements.txt
RUN pip install --no-cache-dir -r /app/cloud/requirements.txt

COPY cloud /app/cloud
COPY instagram_autonomous.py /app/instagram_autonomous.py

EXPOSE 8080

CMD ["uvicorn", "cloud.main:app", "--host", "0.0.0.0", "--port", "8080"]
