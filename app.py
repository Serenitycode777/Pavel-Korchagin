"""Платформа «Целостность»: вход по коду доступа, без логина и пароля.

Настройки: .env (PLATFORM_SECRET, PLATFORM_HOST, PLATFORM_PORT, COOKIE_SECURE).
Тексты и материалы: content.yaml. Коды: data/platform.sqlite (выдаются через codes.py).
"""
import base64
import hashlib
import hmac
import html
import os
import re
import sqlite3
import time
from pathlib import Path

import yaml
from aiohttp import web
from typo import fix_html

HERE = Path(__file__).parent
ENV = HERE / ".env"
if ENV.exists():
    for line in ENV.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

SECRET = os.environ.get("PLATFORM_SECRET", "").encode()
HOST = os.environ.get("PLATFORM_HOST", "127.0.0.1")
PORT = int(os.environ.get("PLATFORM_PORT", "8090"))
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"  # 1, когда сайт открыт по https
TRUST_PROXY = os.environ.get("TRUST_PROXY", "0") == "1"       # 1, если стоит nginx/caddy и передаёт X-Forwarded-For
COOKIE = "celostnost"
SESSION_DAYS = 90

ALPHABET = "ABEKMHPCTX23456789"  # буквы, одинаково выглядящие в латинице и кириллице
LOOKALIKE = str.maketrans("АВЕКМНОРСТХ", "ABEKMHOPCTX")

C = yaml.safe_load((HERE / "content.yaml").read_text(encoding="utf-8"))

(HERE / "data").mkdir(exist_ok=True)
DB = sqlite3.connect(HERE / "data" / "platform.sqlite", check_same_thread=False)
DB.row_factory = sqlite3.Row
DB.execute("""CREATE TABLE IF NOT EXISTS codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, code_hash TEXT UNIQUE, note TEXT, created REAL,
    revoked INTEGER DEFAULT 0, last_used REAL, uses INTEGER DEFAULT 0)""")
try:  # срок действия кода (пусто = бессрочно)
    DB.execute("ALTER TABLE codes ADD COLUMN expires REAL")
except sqlite3.OperationalError:
    pass
try:  # тариф кода (tarif1/tarif2/tarif3); старые коды без тарифа считаются tarif1
    DB.execute("ALTER TABLE codes ADD COLUMN tariff TEXT")
except sqlite3.OperationalError:
    pass
DB.commit()


# ---------- коды и сессии ----------
def normalize(code: str) -> str:
    code = code.strip().upper().translate(LOOKALIKE)
    return re.sub(r"[^A-Z0-9]", "", code)


def code_hash(code: str) -> str:
    return hmac.new(SECRET, normalize(code).encode(), hashlib.sha256).hexdigest()


def sign(payload: str) -> str:
    sig = hmac.new(SECRET, payload.encode(), hashlib.sha256).hexdigest()[:32]
    return base64.urlsafe_b64encode(f"{payload}.{sig}".encode()).decode()


def read_session(token: str):
    """Возвращает строку кода (id, tariff), если сессия подлинная, не просрочена и код не отозван."""
    try:
        payload, sig = base64.urlsafe_b64decode(token.encode()).decode().rsplit(".", 1)
        good = hmac.new(SECRET, payload.encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(sig, good):
            return None
        code_id, issued = payload.split(":")
        if time.time() - float(issued) > SESSION_DAYS * 86400:
            return None
        row = DB.execute("SELECT id, tariff FROM codes WHERE id=? AND revoked=0 AND (expires IS NULL OR expires>?)", (int(code_id), time.time())).fetchone()
        return row
    except Exception:
        return None


def authed(request) -> bool:
    return read_session(request.cookies.get(COOKIE, "")) is not None


# ---------- защита от подбора ----------
FAILS = {}  # ip -> [время неудачных попыток]
MAX_FAILS, WINDOW = 8, 600


def client_ip(request) -> str:
    if TRUST_PROXY:
        fwd = request.headers.get("X-Forwarded-For", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.remote or "?"


def too_many(ip) -> bool:
    now = time.time()
    FAILS[ip] = [t for t in FAILS.get(ip, []) if now - t < WINDOW]
    return len(FAILS[ip]) >= MAX_FAILS


# ---------- страницы ----------
E = html.escape


def page(title: str, body: str, body_class: str = "") -> str:
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#5b3d9b">
<meta name="format-detection" content="telephone=no">
<title>{E(title)}</title>
<link rel="stylesheet" href="/static/fonts.css">
<link rel="stylesheet" href="/static/style.css">
<link rel="stylesheet" href="/static/dark.css" id="dark-css" media="(prefers-color-scheme: dark)">
<script src="/static/theme.js"></script>
</head>
<body class="{body_class}">
<button class="theme-toggle" type="button" data-theme-toggle aria-label="Сменить тему: светлая или тёмная"><svg class="i-moon" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/></svg><svg class="i-sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg></button>
{body}
</body>
</html>"""


def login_page(error: str = "") -> str:
    L, S = C["login"], C["site"]
    err_cls = " err" if error else ""
    body = f"""<main class="login-page">
  <div class="login-card">
    <div class="brand-box cosmic">
      <p class="brand">{E(S["title"])}</p>
      <p class="brand-sub">{E(S["author"])}</p>
    </div>
    <h1>{E(L["heading"])}</h1>
    <p class="hint">{E(L["hint"])}</p>
    <form method="post" action="/enter" autocomplete="off">
      <input class="code-input{err_cls}" name="code" type="text" inputmode="text" autocapitalize="characters"
             autocomplete="off" autocorrect="off" spellcheck="false" maxlength="24"
             placeholder="{E(L["placeholder"])}" aria-label="{E(L["placeholder"])}" required autofocus>
      <button class="btn" type="submit">{E(L["button"])}</button>
      <p class="error" role="alert">{E(error)}</p>
    </form>
  </div>
</main>"""
    return page(f'{S["title"]}: вход', body)


def how_html(items) -> str:
    out = []
    for it in items:
        out.append(f'<h4>{E(it["h"])}</h4>')
        if it.get("p"):
            out.append(f'<p>{E(it["p"])}</p>')
        if it.get("steps"):
            out.append("<ol>" + "".join(f"<li>{E(s)}</li>" for s in it["steps"]) + "</ol>")
    return "".join(out)


def practice_card(p: dict) -> str:
    H = C["home"]
    tag = f'<span class="tag">{E(p["tag"])}</span>' if p.get("tag") else ""
    cover = (f'<span class="p-kicker">Техника №{p["number"]}</span>'
             f'<span class="p-title">{E(p["title"])}</span>'
             f'<span class="p-sub">{E(p["subtitle"])}</span>')
    if p.get("video_file") and (HERE / "files" / p["video_file"]).exists():
        video = (f'<button class="poster" type="button" data-video-file="/files/{E(p["video_file"])}" '
                 f'data-title="{E(p["title"])}" aria-label="Смотреть видео: {E(p["title"])}">{cover}'
                 f'<span class="play-btn" aria-hidden="true"></span></button>')
    elif p.get("video"):
        video = (f'<button class="poster" type="button" data-video="{E(p["video"])}" data-title="{E(p["title"])}" '
                 f'aria-label="Смотреть видео: {E(p["title"])}">{cover}<span class="play-btn" aria-hidden="true"></span></button>')
    else:
        video = f'<div class="poster soon">{cover}<span class="soon-pill">{E(H["video_soon"])}</span></div>'
    info = ""
    if p.get("when") or p.get("gives"):
        info = '<div class="info">'
        if p.get("when"):
            info += f'<div><b>{E(H["when_label"])}</b><p>{E(p["when"])}</p></div>'
        if p.get("gives"):
            info += f'<div><b>{E(H["gives_label"])}</b><p>{E(p["gives"])}</p></div>'
        info += "</div>"
    more = ""
    if p.get("how"):
        did = f'how-{p["number"]}'
        actions = ""
        if p.get("pdf") and (HERE / "files" / p["pdf"]).exists():
            actions += f'<a class="act primary" href="/files/{E(p["pdf"])}" download>{E(H["save_pdf"])}</a>'
        more = f"""<button class="more" type="button" data-open="{did}">{E(H["more_button"])}</button>
  <dialog id="{did}" class="modal" aria-labelledby="{did}-t">
    <div class="modal-head">
      <h3 id="{did}-t">{E(p["title"])}</h3>
      <button class="x" type="button" data-close aria-label="{E(H["close"])}">&times;</button>
    </div>
    <div class="modal-body">{how_html(p["how"])}</div>
    <div class="modal-actions">{actions}<button class="act" type="button" data-close>{E(H["back_to_list"])}</button></div>
  </dialog>"""
    return f"""<details class="practice" id="p{p["number"]}">
  <summary class="p-head">
    <div class="num">{p["number"]}</div>
    <div class="p-head-text">
      <h3>{E(p["title"])}</h3>{tag}
      <p class="subtitle">{E(p["subtitle"])}</p>
    </div>
    <span class="chev" aria-hidden="true"></span>
  </summary>
  <div class="p-body">
    <p class="lead">{E(p["lead"])}</p>
    {info}
    {video}
    {more}
  </div>
</details>"""


def intro_steps_html(sections) -> tuple[str, int]:
    out = []
    for i, s in enumerate(sections, start=1):
        body = f'<h4>{E(s["h"])}</h4>'
        if s.get("p"):
            body += f'<p>{E(s["p"])}</p>'
        if s.get("items"):
            body += "<ul>" + "".join(f"<li>{E(it)}</li>" for it in s["items"]) + "</ul>"
        hidden = "" if i == 1 else " hidden"
        out.append(f'<div class="intro-step" data-step="{i}"{hidden}>{body}</div>')
    return "".join(out), len(sections)


def home_page(tariff: str = "") -> str:
    H, S = C["home"], C["site"]
    cards = "\n".join(practice_card(p) for p in C["practices"])
    initials = "".join(w[0] for w in S["author"].split()[:2]).upper()
    intro_body, intro_total = intro_steps_html(H["intro_sections"])
    tariff = tariff or "tarif1"
    tariff_name = C.get("tariffs", {}).get(tariff, "")
    badge = f'<span class="tariff-tag">{E(tariff_name)}</span>' if tariff_name else '<span></span>'
    EX = C.get("extra_actions", {})
    links, note = "", ""
    if tariff in ("tarif2", "tarif3") and EX.get("diagnostics"):
        d = EX["diagnostics"]
        links += f'<a href="{E(d["url"])}" target="_blank" rel="noopener">{E(d["text"])}</a>'
    if tariff == "tarif3" and EX.get("question"):
        q = EX["question"]
        tg_url = f'https://t.me/{S["telegram"]}'
        links += f'<a class="gold" href="{E(tg_url)}" target="_blank" rel="noopener">{E(q["text"])}</a>'
        note = q.get("note", "")
    extra_html = ""
    if links:
        extra_html = f'<div class="top-links">{links}</div>'
        if note:
            extra_html += f'<p class="top-note">{E(note)}</p>'
    body = f"""<header class="top">
  <div class="wrap">
    <div class="top-card cosmic">
      <div class="top-head">
        {badge}
        <a class="logout" href="/logout">Выйти</a>
      </div>
      <p class="brand">{E(S["title"])}</p>
      <h1>{E(H["heading"])}</h1>
      <p>{E(H["intro"])}</p>
      <p>{E(H["intro_note"])}</p>
      {extra_html}
    </div>
  </div>
</header>
<main class="wrap">
  {cards}
  <div class="author">
    <div class="mono">{E(initials)}</div>
    <div><b>{E(S["author"])}</b><span>{E(S["author_role"])}</span></div>
  </div>
</main>
<footer class="wrap">{E(H["footer"])} <a href="https://t.me/{E(S["telegram"])}" rel="noopener">@{E(S["telegram"])}</a></footer>
<dialog id="intro" class="modal" aria-labelledby="intro-t">
  <div class="modal-head">
    <h3 id="intro-t">{E(H["intro_title"])}</h3>
    <span class="intro-count"><span id="introPos">1</span> / {intro_total}</span>
  </div>
  <div class="modal-body">{intro_body}</div>
  <div class="modal-actions">
    <button class="act primary" type="button" id="introNext" data-next-label="{E(H["intro_next"])}" data-finish-label="{E(H["intro_button"])}">{E(H["intro_next"])}</button>
  </div>
</dialog>
<script src="/static/app.js"></script>"""
    return page(f'{S["title"]}: практики', body)


# ---------- обработчики ----------
HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                                "frame-src https://www.youtube-nocookie.com; frame-ancestors 'none'"),
}


def html_response(text, status=200):
    resp = web.Response(text=fix_html(text), status=status, content_type="text/html", headers=HEADERS)
    resp.enable_compression()  # страница на слабом интернете грузится быстрее
    return resp


async def index(request):
    if authed(request):
        raise web.HTTPFound("/practices")
    return html_response(login_page())


async def enter(request):
    ip = client_ip(request)
    if too_many(ip):
        return html_response(login_page(C["login"]["too_many"]), 429)
    data = await request.post()
    code = str(data.get("code", ""))
    row = None
    if len(normalize(code)) >= 6:
        row = DB.execute("SELECT id FROM codes WHERE code_hash=? AND revoked=0 AND (expires IS NULL OR expires>?)", (code_hash(code), time.time())).fetchone()
    if not row:
        FAILS.setdefault(ip, []).append(time.time())
        return html_response(login_page(C["login"]["error"]), 401)
    DB.execute("UPDATE codes SET last_used=?, uses=uses+1 WHERE id=?", (time.time(), row["id"]))
    DB.commit()
    resp = web.HTTPFound("/practices")
    resp.set_cookie(COOKIE, sign(f'{row["id"]}:{time.time()}'), max_age=SESSION_DAYS * 86400, httponly=True,
                    samesite="Lax", secure=COOKIE_SECURE, path="/")
    raise resp


async def practices(request):
    row = read_session(request.cookies.get(COOKIE, ""))
    if not row:
        raise web.HTTPFound("/")
    return html_response(home_page(row["tariff"]))


async def files(request):
    if not authed(request):
        raise web.HTTPFound("/")
    name = request.match_info["name"]
    pdfs = {p["pdf"] for p in C["practices"] if p.get("pdf")}
    videos = {p["video_file"] for p in C["practices"] if p.get("video_file")}
    path = HERE / "files" / name
    if name not in (pdfs | videos) or not path.exists():
        raise web.HTTPNotFound()
    from urllib.parse import quote
    # PDF скачивается (attachment), видео проигрывается в теге <video> (inline, не download)
    disposition = "inline" if name in videos else "attachment"
    return web.FileResponse(path, headers={"Cache-Control": "private, max-age=3600",
                                           "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(name)}",
                                           "X-Content-Type-Options": "nosniff"})


async def health(request):
    """Для проверки, что платформа жива (мониторинг)."""
    DB.execute("SELECT 1").fetchone()
    return web.Response(text="ok", headers={"Cache-Control": "no-store"})


async def logout(request):
    resp = web.HTTPFound("/")
    resp.del_cookie(COOKIE, path="/")
    raise resp


async def _static_cache(request, response):
    if request.path.startswith("/static/") and response.status == 200:
        response.headers["Cache-Control"] = "public, max-age=3600"


def make_app():
    if not SECRET:
        raise SystemExit("Нет PLATFORM_SECRET. Запусти: python3 codes.py new (создаст .env), либо заполни .env по .env.example.")
    app = web.Application()
    app.add_routes([web.get("/", index), web.post("/enter", enter), web.get("/practices", practices),
                    web.get("/files/{name}", files), web.get("/logout", logout), web.get("/health", health),
                    web.static("/static", HERE / "static")])
    app.on_response_prepare.append(_static_cache)
    return app


if __name__ == "__main__":
    web.run_app(make_app(), host=HOST, port=PORT)
