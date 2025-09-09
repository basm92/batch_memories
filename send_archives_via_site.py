# -*- coding: utf-8 -*-
"""
Memories Project — автопереход во viewer и отправка на e-mail ссылки
'Download volledige reeks bestanden' для дел 399..502 на Het Utrechts Archief.

Поток:
1) Открываем список (инвентарь).
2) Идём по ссылкам-делам: 399..502.
3) Для каждого дела:
   - кликаем заголовок дела (карточка раскрывается),
   - кликаем ПЕРВУЮ миниатюру (a.mi_stripthumb) внутри карточки → открывается viewer,
   - во viewer вводим e-mail и жмём 'Verstuur' (если DRY_RUN=false),
   - закрываем viewer ('Sluiten') и продолжаем.

Повторы исключаем через processed_ids.json.
"""

from __future__ import annotations
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

# --- СУПЕР-ГРОМКИЕ МЕТКИ, чтобы понять, что запускается ИМЕННО ЭТОТ ФАЙЛ ---
print(">>> BUILD TAG: v3")
print(">>> ABSOLUTE FILE:", Path(__file__).resolve())

from dotenv import load_dotenv
from pydantic import BaseModel, EmailStr
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout


STATE_FILE = "processed_ids.json"


# -----------------------------------------------------------------------------
# Конфиг из .env
# -----------------------------------------------------------------------------
class Config(BaseModel):
    START_URL: str
    MIN_NUMBER: int = 399
    MAX_NUMBER: int = 502
    EMAIL_TO: EmailStr
    HEADLESS: bool = False
    SLOW_MO_MS: int = 200
    DRY_RUN: bool = True
    PAUSE_BETWEEN_MS: int = 1200


def load_config() -> Config:
    load_dotenv()
    return Config(
        START_URL=os.getenv("START_URL", "").strip(),
        MIN_NUMBER=int(os.getenv("MIN_NUMBER", "399")),
        MAX_NUMBER=int(os.getenv("MAX_NUMBER", "502")),
        EMAIL_TO=os.getenv("EMAIL_TO", "").strip(),
        HEADLESS=os.getenv("HEADLESS", "false").lower() == "true",
        SLOW_MO_MS=int(os.getenv("SLOW_MO_MS", "200")),
        DRY_RUN=os.getenv("DRY_RUN", "true").lower() == "true",
        PAUSE_BETWEEN_MS=int(os.getenv("PAUSE_BETWEEN_MS", "1200")),
    )


# -----------------------------------------------------------------------------
# Состояние
# -----------------------------------------------------------------------------
def load_state() -> Dict[str, bool]:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_state(state: Dict[str, bool]) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# -----------------------------------------------------------------------------
# Утилиты
# -----------------------------------------------------------------------------
NUM_RE = re.compile(r"^\s*(\d{1,4})\b")


def extract_leading_number(text: str) -> Optional[int]:
    m = NUM_RE.search(text or "")
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def get_list_locator(page):
    """Локатор ссылок в списке дел (страница инвентаря)."""
    for css in [
        "a.mi_tree_content.mi_hyperlink",
        "a.mi_hyperlink.mi_tree_content",
        "div.mi_tree_content a.mi_hyperlink",
        "a.mi_hyperlink",
    ]:
        loc = page.locator(css)
        if loc.count() > 0:
            return loc
    return page.locator("a.mi_hyperlink")


def close_viewer(page) -> None:
    """Закрыть viewer (крестик/Sluiten) и вернуться к списку."""
    for sel in [
        "text=Sluiten",
        "button:has-text('Sluiten')",
        "a:has-text('Sluiten')",
        "button[title*='Sluiten']",
        "a[title*='Sluiten']",
    ]:
        try:
            page.locator(sel).first.click(timeout=1500)
            page.wait_for_load_state("networkidle", timeout=6000)
            return
        except Exception:
            pass
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass


# -----------------------------------------------------------------------------
# Открытие viewer: кликаем миниатюру внутри раскрытой карточки
# -----------------------------------------------------------------------------
def open_viewer_from_card(page, link_locator, num: Optional[int] = None) -> None:
    """
    Мы уже кликнули ссылку дела (карточка раскрыта).
    Кликаем ПЕРВУЮ миниатюру (a.mi_stripthumb) внутри этой карточки,
    чтобы попасть в viewer (слева панель 'Download').
    """
    print(f">>> CALL open_viewer_from_card num={num}")

    # ближайший контейнер карточки
    container = link_locator.locator("xpath=ancestor::div[contains(@class,'mi')][1]")

    # миниатюра внутри этой карточки
    thumb = container.locator("a.mi_stripthumb").first
    thumb.wait_for(timeout=8000)
    thumb.click(timeout=4000)

    # во viewer ждём панель/поле E-mail
    try:
        page.locator("text=Download").first.wait_for(timeout=8000)
    except Exception:
        pass
    page.locator("input[placeholder*='E-mail' i], input[type='email']").first.wait_for(timeout=8000)


# --- АЛИАС: если где-то осталось старое имя, всё равно пойдём в новую функцию
def open_viewer_from_record(*args, **kwargs):
    # важно: это определение ДОЛЖНО быть единственным с таким именем
    return open_viewer_from_card(*args, **kwargs)


def submit_email_for_full_series(page, email: str, dry_run: bool) -> None:
    """
    Во viewer:
      - находим поле E-mail,
      - вводим адрес,
      - нажимаем 'Verstuur' (если не DRY_RUN).
    """
    email_input = page.locator("input[placeholder*='E-mail' i], input[type='email']").first
    email_input.fill(email)
    if not dry_run:
        page.locator("button:has-text('Verstuur')").first.click(timeout=4000)
        page.wait_for_timeout(1200)


# -----------------------------------------------------------------------------
# Основной сценарий
# -----------------------------------------------------------------------------
def scrape_and_send(cfg: Config) -> None:
    state = load_state()
    processed_now: List[int] = []

    from playwright.sync_api import Error as PWError

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=cfg.HEADLESS, slow_mo=cfg.SLOW_MO_MS)
        context = browser.new_context(
            viewport={"width": 1400, "height": 920},
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"),
        )
        page = context.new_page()

        print("Открываю список:", cfg.START_URL)
        page.goto(cfg.START_URL, wait_until="domcontentloaded", timeout=90_000)
        page.wait_for_load_state("networkidle", timeout=30_000)

        # Cookie-баннер (если появится)
        for sel in ["button:has-text('Akkoord')", "button:has-text('Accept')",
                    "text=Akkoord", "text=Accept all"]:
            try:
                page.locator(sel).first.click(timeout=1500)
                break
            except Exception:
                pass

        # дождаться хотя бы одной ссылки
        try:
            page.locator("a.mi_hyperlink").first.wait_for(timeout=15_000)
        except Exception:
            pass

        items = get_list_locator(page)
        count = items.count()
        if count == 0:
            print("❌ Не найден список дел — проверь URL/верстку.")
            browser.close()
            return

        # быстрый листинг
        print("Первые записи:")
        for i in range(min(15, count)):
            try:
                t = (items.nth(i).text_content(timeout=3000) or "").strip()
            except Exception:
                t = "<непрочитано>"
            print(" -", t)

        # цикл по делам
        for i in range(count):
            link = items.nth(i)
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

            # 1) открыть карточку дела
            try:
                link.scroll_into_view_if_needed(timeout=2000)
            except Exception:
                pass
            try:
                link.click(timeout=10_000)
                page.wait_for_load_state("networkidle", timeout=8000)
            except (PWTimeout, PWError):
                print("  ⚠ Не получилось кликнуть — пропуск")
                continue

            # 2) кликнуть миниатюру -> войти во viewer
            try:
                # если вдруг где-то осталось старое имя — сработает алиас
                open_viewer_from_card(page, link, num)
            except Exception as e:
                print(f"  ❌ Не удалось открыть viewer для №{num}: {e}")
                close_viewer(page)
                continue

            # 3) отправка e-mail (или имитация)
            try:
                submit_email_for_full_series(page, cfg.EMAIL_TO, cfg.DRY_RUN)
                processed_now.append(num)
                state[key] = True
                save_state(state)
                print(f"  {'[DRY RUN] имитация' if cfg.DRY_RUN else '✅ Отправлено'} (№{num})")
            except PWTimeout:
                print("  ❌ Не нашёл поле E-mail/кнопку Verstuur — пропуск")
            except Exception as e:
                print("  ❌ Ошибка при отправке:", e)

            # 4) закрыть viewer и вернуться к списку
            close_viewer(page)

            # DOM мог измениться — пересоберём локатор
            items = get_list_locator(page)
            page.wait_for_timeout(cfg.PAUSE_BETWEEN_MS)

        browser.close()

    print("\nИтого обработано в этом запуске:", len(processed_now))


def main():
    cfg = load_config()
    print("== Memories Project — e-mail ссылки на полные серии ==")
    print(f"Диапазон: {cfg.MIN_NUMBER}..{cfg.MAX_NUMBER}   |   DRY_RUN={cfg.DRY_RUN}")
    print(f"Адресат: {cfg.EMAIL_TO}")
    print(f"Стартовая страница:\n{cfg.START_URL}\n")
    scrape_and_send(cfg)


if __name__ == "__main__":
    main()
