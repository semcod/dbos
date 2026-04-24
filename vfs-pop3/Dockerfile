FROM python:3.12-slim
WORKDIR /app

COPY vfs-pop3/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY libs/platform_storage /app/platform_storage
COPY vfs-pop3/app.py /app/app.py

ENV PYTHONPATH=/app
EXPOSE 1110

CMD ["python", "-u", "/app/app.py"]
