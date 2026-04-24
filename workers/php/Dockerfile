FROM php:8.3-cli-alpine

RUN apk add --no-cache postgresql-dev \
 && docker-php-ext-install pdo pdo_pgsql

WORKDIR /app
COPY worker.php ./

EXPOSE 5002
CMD ["php", "-S", "0.0.0.0:5002", "worker.php"]
