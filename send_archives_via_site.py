import os
import re
import json
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Optional, Dict

from dotenv import load_dotenv
from pydantic import EmailStr
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout, Error as PWError

# ─────────────────────────── Config ───────────────────────────
START_URL = (
    "https://hetutrechtsarchief.nl/onderzoek/resultaten/archieven"
    "?mizig=210&miadt=39&miaet=1&micode=337-7&minr=5611808&miview=inv2"
)
START_NUMBER = 399                   # начинать с этого номера инвентаря
STATE_FILE = Path("state.json")      # хранит уже отправленные заголовки
HEADLESS = False                     # можно True, если не хочешь видеть браузер
OPEN_DELAY_SEC = 0.7                 # мягкая пауза между действиями
# ──────────────────────────────────────────────────────────────

def load_state() -> Dict[str, bool]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def save_state(state: Dict[str, bool]) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

def parse_number(text: str) -> Optional[int]:
    """Из '399 1877 jan.-mrt.' достаём 399."""
    m = re.match(r"^\s*(\d+)\b", text or "")
    return int(m.group(1)) if m else None

def get_durable_url(page) -> str:
    """
    В открытой карточке: нажимаем «поделиться» и читаем textarea с 'Duurzaam webadres'.
    Возвращаем сам URL.
    """
    share_btn = page.locator("button.mi_button_a_style").first
    share_btn.wait_for(state="visible", timeout=10_000)
    share_btn.click()
    page.wait_for_timeout(int(OPEN_DELAY_SEC * 1000))

    textarea = page.locator("div.mi_link_box textarea").first
    textarea.wait_for(state="visible", timeout=10_000)
    url = textarea.input_value().strip()
    if not url:
        raise RuntimeError("Пустой durable url")
    return url

def send_email_smtp(to_email: EmailStr, subject: str, body: str):
    """
    Простой SMTP (Gmail/любой). Читает SMTP_* из .env.
    """
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    pwd  = os.getenv("SMTP_PASS")
    if not (host and user and pwd):
        raise RuntimeError("Не настроены SMTP_HOST/SMTP_USER/SMTP_PASS в .env")

    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = str(to_email)
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(host, port) as s:
        s.starttls()
        s.login(user, pwd)
        s.send_message(msg)

def scrape_and_send(url: str, email_to: EmailStr):
    """
    Открываем список, идём по пунктам ≥ START_NUMBER, шлём письма с durable-ссылкой.
    """
    # Windows не требует DISPLAY; строка ниже нужна только для linux/Xvfb,
    # можно смело удалить на Windows:
    # os.environ['DISPLAY'] = ':1'

    sent = load_state()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, slow_mo=50 if not HEADLESS else 0)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=90_000)

        items = page.locator("a.mi_tree_content.mi_hyperlink")
        count = items.count()
        print(f"Найдено элементов: {count}")

        for i in range(count):
            link = items.nth(i)

            # берём заголовок элемента
            try:
                title = (link.text_content(timeout=7000) or "").strip()
            except PWTimeout:
                print(f"[{i+1}/{count}] не удалось прочитать текст — пропуск")
                continue

            num = parse_number(title)
            if num is None or num < START_NUMBER:
                continue

            if title in sent:
                print(f"[{i+1}/{count}] #{num} уже отправлен — пропуск")
                continue

            print(f"\n[{i+1}/{count}] Обрабатываю: {title}")
            try:
                link.click()
                page.wait_for_timeout(int(OPEN_DELAY_SEC * 1000))

                durable = get_durable_url(page)

                subject = f"Het Utrechts Archief — {title}"
                body = f"{title}\n{durable}\n\nИсточник раздела:\n{START_URL}"

                send_email_smtp(email_to, subject, body)
                print(f"  ✔ Письмо отправлено на {email_to}")

                sent[title] = True
                save_state(sent)
            except (PWError, PWTimeout, Exception) as e:
                print(f"  ✖ Ошибка: {e} — продолжаю со следующей")

        browser.close()

def main():
    load_dotenv()
    email_to = os.getenv("TARGET_EMAIL", "memoriesretrieval@gmail.com")
    scrape_and_send(START_URL, email_to)

if __name__ == "__main__":
    main()
