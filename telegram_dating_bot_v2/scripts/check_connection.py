"""Run from the project root: python scripts/check_connection.py."""

import asyncio
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.bot_factory import create_bot
from app.config import Settings


async def main():
    try:
        cfg = Settings()
    except ValueError:
        print("Ошибка .env. Проверьте формат настроек; не отправляйте токены в переписку.")
        return 1
    loop = asyncio.get_running_loop()
    try:
        await asyncio.wait_for(loop.getaddrinfo("api.telegram.org", 443, type=socket.SOCK_STREAM), 5)
        print("DNS: api.telegram.org разрешается")
    except (OSError, TimeoutError):
        print("DNS: ошибка или таймаут")
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection("api.telegram.org", 443), 5)
        writer.close()
        await writer.wait_closed()
        print("Прямой TCP: доступен")
    except (OSError, TimeoutError):
        print("Прямой TCP: недоступен; возможно, нужен ваш HTTP/SOCKS5 прокси")
    if cfg.proxy_url.get_secret_value():
        import aiohttp
        from aiohttp_socks import ProxyConnector

        try:
            connector = ProxyConnector.from_url(cfg.proxy_url.get_secret_value())
            async with aiohttp.ClientSession(
                connector=connector, timeout=aiohttp.ClientTimeout(total=10)
            ) as session:
                async with session.get("https://api.telegram.org") as response:
                    print("HTTPS через настроенный прокси: соединение установлено, статус", response.status)
        except Exception:
            print("Прокси: ошибка подключения, авторизации или TLS. Проверьте настройки провайдера.")
    else:
        print("Прокси не настроен, getMe использует прямое подключение")
    if not cfg.bot_token.get_secret_value():
        print("getMe пропущен: заполните BOT_TOKEN в .env")
        return 1
    bot = None
    try:
        bot = create_bot(cfg)
        await bot.get_me()
        print("getMe: успешно, токен действителен")
        return 0
    except Exception:
        print("getMe: ошибка. Проверьте токен, сеть и прокси. Секреты скрыты.")
        return 1
    finally:
        if bot:
            await bot.session.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
