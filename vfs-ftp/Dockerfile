FROM python:3.12-slim
WORKDIR /app

COPY vfs-ftp/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Shared storage library
COPY libs/platform_storage /app/platform_storage

COPY vfs-ftp/app.py /app/app.py

ENV PYTHONPATH=/app
EXPOSE 2121 30000-30100

CMD ["python", "-u", "/app/app.py"]
