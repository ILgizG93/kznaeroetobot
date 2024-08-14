import asyncio
import logging

from aiohttp import ClientSession, ClientResponse
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.bot import DefaultBotProperties

from config import TOKEN, API_URL
from handlers.private import private_router
from common.commands_list import private

logging.basicConfig(level=logging.INFO)

# ALLOWED_UPDATES = ['message', 'callback_query']

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode = ParseMode.HTML))
disp = Dispatcher()

disp.include_routers(private_router)

async def on_startup() -> None:
    async with ClientSession() as api_session:
        async with api_session.post(API_URL+'delete_chat_id', params={ 'delete_all': 'True' }) as resp:
            response: ClientResponse = resp

async def main() -> None:
    disp.startup.register(on_startup)
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.delete_my_commands(scope=types.BotCommandScopeAllPrivateChats())
    await bot.set_my_commands(commands = private, scope = types.BotCommandScopeAllPrivateChats())
    await disp.start_polling(bot, allowed_updates=disp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
