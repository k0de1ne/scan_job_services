# Развертывание Scan Job (LLM Proxy & Auth HH)

Эта конфигурация позволяет запустить оба сервера в Docker-контейнерах с автоматическим получением SSL-сертификатов (HTTPS) через Caddy.

## Предварительные требования
- Docker и Docker Compose
- Доменное имя (или IP-адрес)
- Открытые порты 80 и 443 на сервере

## Быстрый старт

1. **Настройка переменных окружения**
   Скопируйте файлы `.env.example` в `.env` и заполните их:
   ```bash
   cp server_llm_api/.env.example server_llm_api/.env
   cp server_auth_hh/.env.example server_auth_hh/.env
   ```
   *Обязательно добавьте `OPENAI_API_KEY` в `server_llm_api/.env`.*

2. **Настройка HTTPS (Caddyfile)**
   Откройте `Caddyfile` и замените `:443` на ваше доменное имя:
   ```caddy
   api.scanjob.ru {
       ...
   }
   ```
   Если у вас только IP-адрес (например, `1.2.3.4`), используйте `1.2.3.4.sslip.io`:
   ```caddy
   1.2.3.4.sslip.io {
       ...
   }
   ```

3. **Запуск**
   ```bash
   docker-compose up -d --build
   ```

## Настройка клиентского приложения (Flutter)

Для того чтобы подписи запросов совпадали, необходимо передать ту же соль (`SALT`) при сборке Flutter-приложения через `--dart-define`:

```bash
flutter build apk --dart-define=APP_SALT=ваша_соль_из_env
```

Или при запуске для отладки:
```bash
flutter run --dart-define=APP_SALT=ваша_соль_из_env
```

## API Эндпоинты

После запуска ваши API будут доступны по следующим путям:
- LLM API: `https://your-domain.com/llm/v1/chat/completions`
- Auth HH: `https://your-domain.com/auth/login/phone`
- Проверка шлюза: `https://your-domain.com/` (должно вернуть "Scan Job API Gateway")

## Обновление серверов
Для обновления кода и перезапуска используйте:
```bash
git pull
docker-compose up -d --build
```

## Логи
Просмотр логов всех сервисов:
```bash
docker-compose logs -f
```
Или конкретного сервиса:
```bash
docker-compose logs -f llm_api
docker-compose logs -f auth_hh
```
