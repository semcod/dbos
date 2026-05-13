FROM python:3.12-slim
WORKDIR /app

COPY sync-outbound/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY sync-outbound/app.py /app/app.py

ENV OUTBOUND_DIR=/data
ENV OUTBOUND_POLL_SECONDS=3

CMD ["python", "-u", "/app/app.py"]
