FROM python:3.12-slim
WORKDIR /app

COPY vfs-imap/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY libs/platform_storage /app/platform_storage
COPY vfs-imap/app.py /app/app.py

ENV PYTHONPATH=/app
EXPOSE 1143

CMD ["python", "-u", "/app/app.py"]
