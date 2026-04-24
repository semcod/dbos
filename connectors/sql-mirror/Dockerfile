FROM python:3.12-slim
WORKDIR /app

COPY connectors/sql-mirror/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY libs/platform_storage        /app/platform_storage
COPY connectors/_base             /app/_base
COPY connectors/sql-mirror/app.py /app/app.py

ENV PYTHONPATH=/app
CMD ["python", "-u", "/app/app.py"]
