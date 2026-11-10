"""Сценарий записи — общий для Telegram и MAX.

Ядро ничего не знает о мессенджере: получает id пользователя и действие
(текст кнопки-payload), возвращает Reply — текст и кнопки. Адаптеры
tg_bot.py и max_bot.py только переводят это в формат своей платформы.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

# ---------- Настройки салона (меняются без программиста) ----------
SALON = "Барбершоп «Бритва»"
ADDRESS = "ул. Примерная, 10"
SERVICES = {  # id: (название, цена ₽, длительность мин)
    "cut": ("Мужская стрижка", 1800, 60),
    "beard": ("Оформление бороды", 1200, 30),
    "combo": ("Стрижка + борода", 2700, 90),
    "kids": ("Детская стрижка", 1300, 45),
}
MASTERS = {"ivan": "Иван", "artem": "Артём", "any": "Любой мастер"}
WORK_HOURS = range(10, 21)  # слоты с 10:00 до 20:00
DAYS_AHEAD = 6


@dataclass
class Reply:
    text: str
    buttons: list[list[tuple[str, str]]] = field(default_factory=list)  # [[(текст, payload)]]
    notify_admin: str | None = None  # сообщение администратору, если есть


class Storage:
    def __init__(self, path: str = "bookings.db"):
        self.db = sqlite3.connect(path)
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS bookings(
               id INTEGER PRIMARY KEY, platform TEXT, user_id TEXT, name TEXT,
               service TEXT, master TEXT, day TEXT, hour INTEGER, created TEXT,
               status TEXT DEFAULT 'active')"""
        )
        self.state: dict[str, dict] = {}  # черновик записи по пользователю

    def busy(self, master: str, day: str) -> set[int]:
        q = "SELECT hour FROM bookings WHERE day=? AND status='active'"
        args: tuple = (day,)
        if master != "any":
            q += " AND master=?"
            args += (master,)
        return {h for (h,) in self.db.execute(q, args)}

    def add(self, platform: str, uid: str, d: dict) -> int:
        cur = self.db.execute(
            "INSERT INTO bookings(platform,user_id,name,service,master,day,hour,created) VALUES(?,?,?,?,?,?,?,?)",
            (platform, uid, d.get("name", ""), d["service"], d["master"], d["day"], d["hour"], datetime.now().isoformat()),
        )
        self.db.commit()
        return cur.lastrowid

    def my(self, platform: str, uid: str):
        return self.db.execute(
            "SELECT id,service,master,day,hour FROM bookings WHERE platform=? AND user_id=? AND status='active' AND day>=? ORDER BY day,hour",
            (platform, uid, date.today().isoformat()),
        ).fetchall()

    def cancel(self, platform: str, uid: str, bid: int) -> bool:
        cur = self.db.execute(
            "UPDATE bookings SET status='cancelled' WHERE id=? AND platform=? AND user_id=?", (bid, platform, uid)
        )
        self.db.commit()
        return cur.rowcount > 0


WD = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def fmt_day(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{WD[d.weekday()]}, {d.day:02d}.{d.month:02d}"


MAIN_MENU = [[("✂️ Записаться", "book")], [("📋 Мои записи", "my"), ("💈 Цены", "prices")], [("📍 Как добраться", "where")]]


class Booking:
    def __init__(self, storage: Storage, platform: str, today: date | None = None):
        self.s, self.p = storage, platform
        self.today = today or date.today()

    def start(self, uid: str, name: str = "") -> Reply:
        self.s.state[uid] = {"name": name}
        hi = f"Здравствуйте, {name}! " if name else "Здравствуйте! "
        return Reply(f"{hi}Это бот записи в {SALON}.\nВыберите, что нужно:", MAIN_MENU)

    def handle(self, uid: str, action: str, name: str = "") -> Reply:
        st = self.s.state.setdefault(uid, {"name": name})
        if action in ("start", "menu"):
            return self.start(uid, st.get("name") or name)
        if action == "prices":
            lines = [f"• {n} — {p} ₽ ({m} мин)" for n, p, m in SERVICES.values()]
            return Reply("💈 Услуги и цены:\n" + "\n".join(lines), [[("✂️ Записаться", "book")], [("⬅️ В меню", "menu")]])
        if action == "where":
            return Reply(f"📍 {SALON}\n{ADDRESS}\nЕжедневно 10:00–21:00", [[("⬅️ В меню", "menu")]])
        if action == "book":
            return Reply("Выберите услугу:", [[(f"{n} · {p} ₽", f"svc:{k}")] for k, (n, p, _) in SERVICES.items()] + [[("⬅️ В меню", "menu")]])
        if action.startswith("svc:"):
            st["service"] = action[4:]
            return Reply("К какому мастеру?", [[(v, f"mst:{k}")] for k, v in MASTERS.items()] + [[("⬅️ Назад", "book")]])
        need = {"mst:": ["service"], "day:": ["service", "master"], "time:": ["service", "master", "day"]}
        for pre, keys in need.items():
            if action.startswith(pre) and any(k not in st for k in keys):
                return self.handle(uid, "book")  # черновик устарел — начинаем выбор заново
        if action.startswith("mst:"):
            st["master"] = action[4:]
            days = [(self.today + timedelta(days=i)).isoformat() for i in range(DAYS_AHEAD)]
            rows = [[(("Сегодня" if i == 0 else "Завтра" if i == 1 else fmt_day(d)), f"day:{d}") for i, d in list(enumerate(days))[j:j + 3]] for j in (0, 3)]
            return Reply("Выберите день:", rows + [[("⬅️ Назад", f"svc:{st['service']}")]])
        if action.startswith("day:"):
            st["day"] = action[4:]
            busy = self.s.busy(st["master"], st["day"])
            now_h = datetime.now().hour if st["day"] == self.today.isoformat() else -1
            free = [h for h in WORK_HOURS if h not in busy and h > now_h]
            if not free:
                return Reply("На этот день всё занято 😔 Выберите другой:", [[("⬅️ К выбору дня", f"mst:{st['master']}")]])
            rows = [[(f"{h}:00", f"time:{h}") for h in free[i:i + 4]] for i in range(0, len(free), 4)]
            return Reply(f"Свободное время на {fmt_day(st['day'])}:", rows + [[("⬅️ Назад", f"mst:{st['master']}")]])
        if action.startswith("time:"):
            st["hour"] = int(action[5:])
            n, p, m = SERVICES[st["service"]]
            text = (f"Проверьте запись:\n\n✂️ {n}\n👤 {MASTERS[st['master']]}\n📅 {fmt_day(st['day'])}, {st['hour']}:00\n"
                    f"⏱ {m} мин · 💳 {p} ₽")
            return Reply(text, [[("✅ Подтвердить", "confirm")], [("⬅️ Изменить время", f"day:{st['day']}")]])
        if action == "confirm":
            if not all(k in st for k in ("service", "master", "day", "hour")):
                return self.start(uid, st.get("name", ""))
            if st["hour"] in self.s.busy(st["master"], st["day"]):
                return Reply("Это время только что заняли 😔 Выберите другое:", [[("Выбрать время", f"day:{st['day']}")]])
            bid = self.s.add(self.p, uid, st)
            n, p, _ = SERVICES[st["service"]]
            admin = f"🆕 Запись №{bid} ({self.p})\n{st.get('name') or 'Клиент'} · {n}\n{MASTERS[st['master']]} · {fmt_day(st['day'])} {st['hour']}:00"
            reply = Reply(f"Готово! Вы записаны ✅\n\n{n}, {fmt_day(st['day'])} в {st['hour']}:00\n{ADDRESS}\n\nЖдём вас! Если планы изменятся — отмените запись в «Мои записи».",
                          [[("📋 Мои записи", "my")], [("⬅️ В меню", "menu")]], notify_admin=admin)
            self.s.state[uid] = {"name": st.get("name", "")}
            return reply
        if action == "my":
            rows = self.s.my(self.p, uid)
            if not rows:
                return Reply("У вас пока нет записей.", [[("✂️ Записаться", "book")], [("⬅️ В меню", "menu")]])
            text = "📋 Ваши записи:\n" + "\n".join(f"№{i}: {SERVICES[s][0]}, {fmt_day(d)} {h}:00" for i, s, _, d, h in rows)
            return Reply(text, [[(f"❌ Отменить №{i}", f"cancel:{i}")] for i, *_ in rows] + [[("⬅️ В меню", "menu")]])
        if action.startswith("cancel:"):
            bid = int(action[7:])
            ok = self.s.cancel(self.p, uid, bid)
            return Reply("Запись отменена." if ok else "Запись не найдена.", [[("⬅️ В меню", "menu")]],
                         notify_admin=f"❌ Отмена записи №{bid}" if ok else None)
        return Reply("Не понял вас 🙂 Выберите действие кнопкой:", MAIN_MENU)
