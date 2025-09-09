import os
import re
import json
import time
from typing import Optional, Dict, List

from dotenv import load_dotenv
from pydantic import BaseModel, EmailStr
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout


STATE_FILE = "processed_ids.json"


class Config(BaseModel):
    START_URL: str
    MIN_NUMBER: int = 399
    MAX_NUMBER: int = 502
    EMAIL_TO: EmailStr
    HEADLESS: bool = False
    SLOW_MO_MS: int = 80
    DRY_RUN: bool = False
    PAUSE_BETWEEN_MS: int = 800


def load_config() -> Config:
    load_dotenv()
    return Config(
        START_URL=os.getenv("START_URL"),
        MIN_NUMBER=int(os.getenv("MIN_NUMBER", "399")),
        MAX_NUMBER=int(os.getenv("MAX_NUMBER", "502")),
        EMAIL_TO=os.getenv("EMAIL_TO"),
        HEADLESS=os.getenv("HEADLESS", "false").lower() == "true",
        SLOW_MO_MS=int(os.getenv("SLOW_MO_MS", "80")),
        DRY_RUN=os.getenv("DRY_RUN", "false").lower() == "true",
        PAUSE_BETWEEN_MS=int(os.getenv("PAUSE_BETWEEN_MS", "800")),
    )


def load_state() -> Dict[str, bool]:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state: Dict[str, bool]):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def extract_leading_number(text: str) -> Optional[int]:
    m = re.match(r"\s*(\d{1,5})\b", text or "")
    return int(m.group(1)) if m else None


def ensure_download_panel(page):
    """Открыть левую панель 'Download', если она не открыта."""
    try:
        page.locator("text=Download volledige reeks bestanden").first.wait_for(timeout=2000)
        return
    except PWTimeout:
        pass

    # Пытаемся кликнуть по иконке 'Download' в левом тулбаре
    # Пробуем разные варианты с title/aria-label/текстом
    candidates = [
        "a[title*='Download']",
        "button[title*='Download']",
        "a[aria-label*='Download']",
        "button[aria-label*='Download']",
        "text=Download"  # если кнопка с текстом
    ]
    for sel in candidates:
        try:
            page.locator(sel).first.click(timeout=1500)
            break
        except Exception:
            continue

    page.locator("text=Download volledige reeks bestanden").first.wait_for(timeout=6000)


def submit_email_for_full_series(page, email_to: str, dry_run: bool = False):
    """На вкладке Download заполнить E-mail и нажать 'Verstuur'."""
    ensure_download_panel(page)

    email_input = page.locator("input[type='email'], input[placeholder='E-mail']").first
    email_input.wait_for(state="visible", timeout=6000)

    if dry_run:
        # Ничего не отправляем
        return

    email_input.fill("")  # очистить на всякий
    email_input.type(email_to, delay=20)

    # Кнопка 'Verstuur'
    send_btn = page.locator("button:has-text('Verstuur'), input[type='submit'][value='Verstuur']").first
    send_btn.wait_for(state="visible", timeout=4000)
    send_btn.click()

    # Небольшое ожидание (почти всегда сервер шлёт без явного алерта)
    page.wait_for_timeout(800)


def close_viewer(page):
    """Закрыть просмотрщик (кнопка 'Sluiten' с красным 'X')."""
    for sel in ["text=Sluiten", "button:has-text('Sluiten')", "a:has-text('Sluiten')"]:
        try:
            page.locator(sel).first.click(timeout=1500)
            return
        except Exception:
            pass
    # запасной вариант: нажать ESC
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    page.wait_for_timeout(300)


def scrape_and_send(cfg: Config):
    state = load_state()
    processed_now: List[int] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=cfg.HEADLESS, slow_mo=cfg.SLOW_MO_MS)
        context = browser.new_context(
            viewport={'width': 1400, 'height': 920},
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"),
        )
        page = context.new_page()

        print("Открываю список:", cfg.START_URL)
        page.goto(cfg.START_URL, wait_until="domcontentloaded", timeout=90_000)

        # Куки-баннер (если появится)
        for sel in ["button:has-text('Akkoord')", "button:has-text('Accept')", "text=Akkoord", "text=Accept all"]:
            try:
                page.locator(sel).first.click(timeout=1500)
                print("Закрыл баннер:", sel)
                break
            except Exception:
                pass

        items_locator = page.locator("a.mi_tree_content.mi_hyperlink")
        count = items_locator.count()
        print("Найдено позиций:", count)

        for i in range(count):
            link = items_locator.nth(i)
            try:
                raw_text = (link.text_content(timeout=6000) or "").strip()
            except PWTimeout:
                continue

            num = extract_leading_number(raw_text)
            if num is None or num < cfg.MIN_NUMBER or num > cfg.MAX_NUMBER:
                continue

            key = str(num)
            if state.get(key):
                print(f"[{i+1}/{count}] №{num} уже обработан — пропуск")
                continue

            print(f"[{i+1}/{count}] Обрабатываю №{num}: {raw_text}")

            # Открыть карточку (вьювер)
            try:
                link.click(timeout=10_000)
            except PWTimeout:
                print("  ⚠ Не получилось кликнуть — пропуск")
                continue

            # Ждём появления панели с кнопками или миниатюр
            try:
                page.locator("text=Bestand").first.wait_for(timeout=6000)
            except PWTimeout:
                # если такой надписи нет, просто подождём подгрузку
                page.wait_for_load_state("networkidle", timeout=8000)

            # Отправка e-mail для полной серии
            try:
                submit_email_for_full_series(page, cfg.EMAIL_TO, cfg.DRY_RUN)
                processed_now.append(num)
                state[key] = True
                save_state(state)
                print(f"  ✅ Отправлено на {cfg.EMAIL_TO} (№{num})" if not cfg.DRY_RUN else f"  [DRY RUN] имитация отправки (№{num})")
            except PWTimeout:
                print("  ❌ Не нашёл форму Download/Verstuur — пропуск")
            except Exception as e:
                print("  ❌ Ошибка при отправке:", e)

            # Закрыть просмотрщик и вернуться к списку
            close_viewer(page)

            # Обновить локатор после возврата
            items_locator = page.locator("a.mi_tree_content.mi_hyperlink")

            # Небольшая пауза между отправками
            page.wait_for_timeout(cfg.PAUSE_BETWEEN_MS)

        browser.close()

    print("\nИтого обработано в этом запуске:", len(processed_now))


def main():
    cfg = load_config()
    print("== Memories Project — email-ссылка полной серии ==")
    print(f"Диапазон: {cfg.MIN_NUMBER}..{cfg.MAX_NUMBER}  | DRY_RUN={cfg.DRY_RUN}")
    scrape_and_send(cfg)


if __name__ == "__main__":
    main()
