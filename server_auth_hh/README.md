# HH Auth Server (Python + Playwright)
$resp = Invoke-RestMethod -Method Post -Uri http://localhost:8000/login/full -ContentType "application/json" -Body (@{phone='89898291878'; password='fedor233'} | ConvertTo-Json)
$s = $resp.session_id
[IO.File]::WriteAllBytes("$(Get-Location)\captcha.png", [Convert]::FromBase64String($resp.captcha_image))
echo "Капча сохранена в файл captcha.png. Откройте его и посмотрите текст."
Сервер для автоматизации процесса авторизации на hh.ru. Позволяет избежать повторного открытия WebView при входе через телефон.

## Установка и запуск

1. Установите зависимости (если еще не установлены):
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

2. Запустите сервер:
   ```bash
   python main.py
   ```
   Сервер будет доступен по адресу: `http://localhost:8000`

## API Endpoints

### 1. Инициация входа (по номеру телефона)
**POST** `/login/phone`
```json
{
  "phone": "79991234567"
}
```
**Ответ:**
```json
{
  "session_id": "uuid-string",
  "status": "waiting_otp",
  "message": "Proceed to /login/code"
}
```

### 2. Проверка статуса сессии
**GET** `/status/{session_id}`
**Ответ:**
```json
{
  "status": "waiting_otp"
}
```

### 3. Ввод SMS кода
**POST** `/login/code`
```json
{
  "session_id": "uuid-string",
  "code": "12345"
}
```
**Ответ:**
```json
{
  "cookies": [...],
  "success": true
}
```

## Как протестировать вручную

Вы можете использовать `curl` для тестирования:

1. **Шаг 1: Запросить код**
   ```bash
   curl -X POST http://localhost:8000/login/phone \
        -H "Content-Type: application/json" \
        -d '{"phone": "ВАШ_НОМЕР"}'
   ```
   Сохраните полученный `session_id`.

2. **Шаг 2: Ввести полученный из СМС код**
   ```bash
   curl -X POST http://localhost:8000/login/code \
        -H "Content-Type: application/json" \
        -d '{"session_id": "SESSION_ID_ИЗ_ШАГА_1", "code": "12345"}'
   ```

Если все успешно, вы получите массив cookies, которые можно будет использовать в приложении или для других запросов к HH API.
