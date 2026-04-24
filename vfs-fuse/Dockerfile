FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends fuse3 libfuse2 \
 && rm -rf /var/lib/apt/lists/* \
 && echo "user_allow_other" >> /etc/fuse.conf

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY fuse_fs.py .

CMD ["python", "fuse_fs.py"]
