$phone = ""
$password = ""
$baseUrl = "http://localhost:8000"

Write-Host "--- Запуск входа для $phone ---" -ForegroundColor Cyan

# 1. Попытка полного входа
$resp = Invoke-RestMethod -Method Post -Uri "$baseUrl/login/full" -ContentType "application/json" -Body (@{phone=$phone; password=$password} | ConvertTo-Json)
$s = $resp.session_id

if ($resp.status -eq "waiting_captcha") {
    Write-Host "[!] Требуется ввод капчи!" -ForegroundColor Yellow
    
    # Сохраняем и открываем капчу
    $captchaPath = "$(Get-Location)\captcha.png"
    [IO.File]::WriteAllBytes($captchaPath, [Convert]::FromBase64String($resp.captcha_image))
    Start-Process $captchaPath
    
    $captchaText = Read-Host "Введите текст с открывшейся картинки (captcha.png)"
    
    # Отправляем капчу
    Write-Host "Отправка капчи..."
    $capResp = Invoke-RestMethod -Method Post -Uri "$baseUrl/login/captcha" -ContentType "application/json" -Body (@{session_id=$s; captcha_text=$captchaText} | ConvertTo-Json)
    
    # После капчи пробуем войти по паролю
    Write-Host "Завершение входа по паролю..."
    $finalResp = Invoke-RestMethod -Method Post -Uri "$baseUrl/login/password" -ContentType "application/json" -Body (@{session_id=$s; password=$password} | ConvertTo-Json)
} else {
    $finalResp = $resp
}

if ($finalResp.success) {
    Write-Host "`n[OK] Вход выполнен успешно!" -ForegroundColor Green
    Write-Host "Ваш Access Token:" -ForegroundColor Gray
    Write-Host $finalResp.tokens.access_token
    
    # Сохраняем результат в файл для проверки
    $finalResp | ConvertTo-Json | Out-File "login_result.json"
    Write-Host "`nПолный ответ сохранен в login_result.json"
} else {
    Write-Host "`n[Ошибка] Не удалось войти:" -ForegroundColor Red
    $finalResp | Format-List
}
