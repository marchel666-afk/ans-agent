# Доступ к агенту по ссылке (agent.ansservice.ru) через твой nginx + Cloudflare

Схема на VPS: весь `:443` перехватывает **stream-блок** nginx по SNI (`ssl_preread`)
и раздаёт по внутренним портам; спереди **Cloudflare в режиме Full** (самоподписанный
сертификат на VPS допустим). Поэтому обычный `listen 443 ssl` не подойдёт — нужны два шага.

Внутренний порт для агента: **10447** (свободен; заняты 10443–10446, 7080).
Контейнер агента слушает `127.0.0.1:8899` — публично он не открыт, только через nginx.

## 1. DNS в Cloudflare
Добавь запись: `agent` → A/CNAME на IP VPS (`45.88.173.84`), **оранжевое облако (Proxied)**.
SSL/TLS режим — **Full** (не Strict, т.к. на VPS самоподписанный сертификат).

## 2. Самоподписанный сертификат на VPS
```
sudo mkdir -p /etc/nginx/ssl
sudo openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
  -keyout /etc/nginx/ssl/agent.ansservice.ru.key \
  -out    /etc/nginx/ssl/agent.ansservice.ru.crt \
  -subj "/CN=agent.ansservice.ru"
```

## 3. Запись в SNI stream-карте
В `/etc/nginx/nginx.conf`, в блоке `stream { map $ssl_preread_server_name $backend { … } }`,
добавь строку рядом с остальными:
```
        agent.ansservice.ru 127.0.0.1:10447;
```

## 4. HTTP-блок агента
```
sudo cp deploy/nginx-agent.conf /etc/nginx/conf.d/ans-agent.conf
sudo nginx -t && sudo systemctl reload nginx
```
Если `nginx -t` ругается на дубль `map … $ans_conn_upgrade` — значит имя всё же занято;
переименуй переменную в `nginx-agent.conf` и повтори. (Штатно имя уникальное.)

## 5. Проверка
- Локально на VPS: `curl -k https://127.0.0.1:10447/health` → `{"status":"ok",...}`
- С любого устройства: открой **https://agent.ansservice.ru** → страница входа →
  вставь токен из `cat /opt/ans-agent/data/auth.token` → готово.

## Безопасность (агент выполняет код — считать привилегированным)
- Вход по токену уже включён. Токен = пароль, храни его как пароль.
- Рекомендую добавить **Cloudflare Access** на `agent.ansservice.ru` (вход по email-коду) —
  второй рубеж перед приложением.
- Смена токена: `rm /opt/ans-agent/data/auth.token` и перезапуск контейнера
  (`docker compose -f deploy/docker-compose.prod.yml restart ans-agent`).
- `ANS_BIND` оставь `127.0.0.1` — наружу агент смотрит только через nginx.
