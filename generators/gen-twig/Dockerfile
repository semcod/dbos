FROM php:8.3-cli-alpine

# pdo_pgsql for Postgres access
RUN apk add --no-cache postgresql-dev git unzip \
 && docker-php-ext-install pdo pdo_pgsql

# Composer
COPY --from=composer:2 /usr/bin/composer /usr/bin/composer

WORKDIR /app
COPY composer.json ./
RUN composer install --no-dev --no-interaction --optimize-autoloader

COPY index.php ./

EXPOSE 6002
CMD ["php", "-S", "0.0.0.0:6002", "index.php"]
