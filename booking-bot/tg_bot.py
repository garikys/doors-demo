"""Адаптер Telegram (aiogram 3). Запуск: python tg_bot.py"""
import asyncio, os
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from core import Booking, Reply, Storage

bot = Bot(os.environ["TG_TOKEN"])
dp = Dispatcher()
flow = Booking(Storage(os.getenv("DB_PATH", "bookings.db")), "telegram")
ADMIN = os.getenv("TG_ADMIN_CHAT_ID")


def kb(r: Reply):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=p) for t, p in row] for row in r.buttons])


async def admin(r: Reply):
    if r.notify_admin and ADMIN:
        await bot.send_message(ADMIN, r.notify_admin)


@dp.message(CommandStart())
async def start(m: Message):
    r = flow.start(str(m.from_user.id), m.from_user.first_name or "")
    await m.answer(r.text, reply_markup=kb(r))


@dp.callback_query(F.data)
async def cb(c: CallbackQuery):
    r = flow.handle(str(c.from_user.id), c.data, c.from_user.first_name or "")
    await c.message.edit_text(r.text, reply_markup=kb(r))
    await c.answer()
    await admin(r)


@dp.message()
async def other(m: Message):
    r = flow.handle(str(m.from_user.id), "?", m.from_user.first_name or "")
    await m.answer(r.text, reply_markup=kb(r))


if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))
