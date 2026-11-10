"""Адаптер MAX (библиотека maxapi). Запуск: python max_bot.py"""
import asyncio, os
from maxapi import Bot, Dispatcher
from maxapi.types import BotStarted, CallbackButton, Command, MessageCallback, MessageCreated
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder
from core import Booking, Reply, Storage

bot = Bot(os.environ["MAX_TOKEN"])
dp = Dispatcher()
flow = Booking(Storage(os.getenv("DB_PATH", "bookings.db")), "max")
ADMIN = os.getenv("MAX_ADMIN_CHAT_ID")


def kb(r: Reply):
    b = InlineKeyboardBuilder()
    for row in r.buttons:
        b.row(*[CallbackButton(text=t, payload=p) for t, p in row])
    return [b.as_markup()]


async def admin(r: Reply):
    if r.notify_admin and ADMIN:
        await bot.send_message(chat_id=int(ADMIN), text=r.notify_admin)


@dp.bot_started()
async def started(e: BotStarted):
    r = flow.start(str(e.user.user_id), e.user.first_name or "")
    await bot.send_message(chat_id=e.chat_id, text=r.text, attachments=kb(r))


@dp.message_created(Command("start"))
async def start(e: MessageCreated):
    u = e.message.sender
    r = flow.start(str(u.user_id), u.first_name or "")
    await e.message.answer(text=r.text, attachments=kb(r))


@dp.message_callback()
async def cb(e: MessageCallback):
    u = e.callback.user
    r = flow.handle(str(u.user_id), e.callback.payload or "", u.first_name or "")
    await e.answer(new_text=r.text, attachments=kb(r))
    await admin(r)


if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))
