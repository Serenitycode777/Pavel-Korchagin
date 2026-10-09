"""Коды доступа к платформе «Целостность».

Использование:
  python3 codes.py new "Имя человека"    выдать новый код (печатает код, его надо отправить человеку)
  python3 codes.py new "Имя" -n 3        выдать несколько кодов сразу
  python3 codes.py new "Имя" --days 90   код на 90 дней (без --days код действует год, 365 дней)
  python3 codes.py new "Имя" --days 0    бессрочный код
  python3 codes.py set 343433 "Базовый тариф" --tariff tarif1   задать свой код (не случайный), а не сгенерировать
  python3 codes.py extend 5 --days 30    продлить код №5 ещё на 30 дней (от сегодня или от конца срока)
  python3 codes.py list                  показать выданные коды (сам код не хранится, только имя и статистика)
  python3 codes.py revoke 5              отозвать код по номеру из списка
  python3 codes.py restore 5             вернуть отозванный код

Код показывается один раз при выдаче: в базе лежит только его хеш.
"""
import argparse
import os
import secrets
import sqlite3
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
ENV = HERE / ".env"

if not ENV.exists() or "PLATFORM_SECRET=" not in ENV.read_text():
    ENV.write_text((ENV.read_text() if ENV.exists() else "") +
                   f"PLATFORM_SECRET={secrets.token_hex(32)}\n")
    os.chmod(ENV, 0o600)
    print("Создан .env с ключом PLATFORM_SECRET. Не теряй его: без него выданные коды перестанут работать.")

sys.path.insert(0, str(HERE))
import app  # noqa: E402  (читает .env и открывает базу)

DB = app.DB


def new_code() -> str:
    raw = "".join(secrets.choice(app.ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def cmd_new(note: str, n: int, days: int = 365, tariff: str = "tarif1"):
    tariff_name = app.C.get("tariffs", {}).get(tariff, tariff)
    for _ in range(n):
        while True:
            code = new_code()
            try:
                expires = time.time() + days * 86400 if days else None
                DB.execute("INSERT INTO codes (code_hash, note, created, expires, tariff) VALUES (?,?,?,?,?)",
                           (app.code_hash(code), note, time.time(), expires, tariff))
                DB.commit()
                break
            except sqlite3.IntegrityError:
                continue
        print(code + f"   (тариф {tariff_name}" + (f", {note})" if note else ")"))


def cmd_set(code: str, note: str, days: int = 365, tariff: str = "tarif1"):
    tariff_name = app.C.get("tariffs", {}).get(tariff, tariff)
    if len(app.normalize(code)) < 6:
        print("Код слишком короткий (минимум 6 знаков).")
        return
    expires = time.time() + days * 86400 if days else None
    try:
        DB.execute("INSERT INTO codes (code_hash, note, created, expires, tariff) VALUES (?,?,?,?,?)",
                   (app.code_hash(code), note, time.time(), expires, tariff))
        DB.commit()
    except sqlite3.IntegrityError:
        print("Такой код уже занят (или совпадает с уже выданным).")
        return
    print(code + f"   (тариф {tariff_name}" + (f", {note})" if note else ")"))


def cmd_list():
    rows = DB.execute("SELECT * FROM codes ORDER BY id").fetchall()
    if not rows:
        print("Кодов пока нет.")
    tariffs = app.C.get("tariffs", {})
    for r in rows:
        used = time.strftime("%d.%m %H:%M", time.localtime(r["last_used"])) if r["last_used"] else "не входил"
        status = "ОТОЗВАН" if r["revoked"] else ("истёк" if r["expires"] and r["expires"] < time.time() else "активен")
        until = f', до {time.strftime("%d.%m.%Y", time.localtime(r["expires"]))}' if r["expires"] else ", бессрочно"
        created = time.strftime("%d.%m.%Y", time.localtime(r["created"]))
        tariff_name = tariffs.get(r["tariff"] or "tarif1", r["tariff"] or "тариф 1")
        print(f'#{r["id"]:<3} {status:<8} {r["note"] or "без имени":<24} {tariff_name:<10} выдан {created}{until}, входов {r["uses"]}, последний {used}')


def cmd_extend(i: int, days: int):
    row = DB.execute("SELECT expires FROM codes WHERE id=?", (i,)).fetchone()
    if not row:
        print("Кода с таким номером нет.")
        return
    start = max(row["expires"] or 0, time.time())
    DB.execute("UPDATE codes SET expires=? WHERE id=?", (start + days * 86400, i))
    DB.commit()
    print("Готово, код действует до", time.strftime("%d.%m.%Y", time.localtime(start + days * 86400)))


def cmd_revoke(i: int, value: int):
    cur = DB.execute("UPDATE codes SET revoked=? WHERE id=?", (value, i))
    DB.commit()
    print("Готово." if cur.rowcount else "Кода с таким номером нет.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new"); p.add_argument("note", nargs="?", default=""); p.add_argument("-n", type=int, default=1); p.add_argument("--days", type=int, default=365)
    p.add_argument("--tariff", choices=["tarif1", "tarif2", "tarif3"], default="tarif1",
                   help="tarif1=Стандарт (по умолчанию), tarif2=Премиум, tarif3=VIP")
    p = sub.add_parser("set"); p.add_argument("code"); p.add_argument("note", nargs="?", default="")
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--tariff", choices=["tarif1", "tarif2", "tarif3"], default="tarif1",
                   help="tarif1=Стандарт (по умолчанию), tarif2=Премиум, tarif3=VIP")
    p = sub.add_parser("extend"); p.add_argument("id", type=int); p.add_argument("--days", type=int, required=True)
    sub.add_parser("list")
    p = sub.add_parser("revoke"); p.add_argument("id", type=int)
    p = sub.add_parser("restore"); p.add_argument("id", type=int)
    a = ap.parse_args()
    if a.cmd == "new":
        cmd_new(a.note, max(1, min(a.n, 100)), a.days, a.tariff)
    elif a.cmd == "set":
        cmd_set(a.code, a.note, a.days, a.tariff)
    elif a.cmd == "extend":
        cmd_extend(a.id, a.days)
    elif a.cmd == "list":
        cmd_list()
    elif a.cmd == "revoke":
        cmd_revoke(a.id, 1)
    elif a.cmd == "restore":
        cmd_revoke(a.id, 0)


if __name__ == "__main__":
    main()
