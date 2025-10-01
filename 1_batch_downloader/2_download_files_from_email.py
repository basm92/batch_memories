"""
Automate downloading attachments from Gmail using Playwright.

Plan:
1) Open browser and go to Gmail
2) Allow manual login (script waits until inbox is visible)
3) Search for relevant emails and download their attachments

Notes:
- This script intentionally leaves login manual for security. It waits until the inbox UI is detected.
- Configure SEARCH_QUERY to match your archive emails. Default targets emails with attachments from the last 14 days.
- Downloads are saved into DOWNLOAD_DIR. Ensure the directory exists or the script can create it.
"""

import os
import re
import time
from pathlib import Path
from typing import Iterable

from playwright.sync_api import Error, TimeoutError as PlaywrightTimeoutError, sync_playwright


# ----------------------------
# Configuration
# ----------------------------
# Adjust this query to match your archive emails. Examples:
# - 'has:attachment newer_than:14d'
# - 'from:(inlichtingen@hetutrechtsarchief.nl) newer_than:60d'
# - 'subject:(Uw verzoek) newer_than:60d'
SEARCH_QUERY: str = "from:(inlichtingen@hetutrechtsarchief.nl) newer_than:60d"

# Directory where attachments will be saved
DOWNLOAD_DIR: str = str(Path.cwd() / "downloads")

# Maximum threads (email conversations) to open from the search results. Set to None for no limit.
MAX_THREADS: int = 25

# How long to wait (seconds) for manual login before timing out
WAIT_LOGIN_TIMEOUT_SECONDS: int = 600  # 10 minutes

# Per-page timeouts
DEFAULT_TIMEOUT_MS: int = 30000

# Use real Chrome with a persistent user profile so Gmail trusts the browser
# Close all Chrome windows before running this script.
USER_DATA_DIR: str = str(Path.home() / ".playwright_chrome_profile_gmail")

# Alternative: Attach to your already running Chrome (your real daily profile)
# 1) Close all Chrome windows
# 2) Start Chrome manually with: chrome.exe --remote-debugging-port=9222
# 3) Run this script and it will connect to that Chrome instance
USE_EXISTING_CHROME: bool = True
CHROME_CDP_URLS: list[str] = [
    "http://127.0.0.1:9222",   # prefer IPv4
    "http://localhost:9222",   # fallback
    "http://[::1]:9222",       # IPv6 localhost
]


def ensure_directory(path: str) -> None:
    directory = Path(path)
    if not directory.exists():
        directory.mkdir(parents=True, exist_ok=True)


def generate_safe_filename(original_filename: str) -> str:
    # Remove characters not allowed in Windows filenames and trim excessive whitespace
    safe = re.sub(r"[\\/:*?\"<>|]", "_", original_filename).strip()
    # Avoid empty filenames
    return safe or "attachment"


def wait_for_gmail_inbox(page) -> None:
    """Wait until the Gmail inbox UI is visible after manual login (locale-agnostic)."""
    # Signals of inbox loaded regardless of language:
    # - URL contains /mail/
    # - Main content area exists: div[role='main']
    # - Search form exists: form[role='search'] with input[name='q'] or a combobox
    deadline = time.time() + WAIT_LOGIN_TIMEOUT_SECONDS
    while time.time() < deadline:
        current_url: str = page.url or ""
        if "/mail/" in current_url:
            try:
                page.wait_for_selector("div[role='main']", timeout=5000)
                # Prefer the classic query input
                try:
                    page.wait_for_selector("form[role='search'] input[name='q']", timeout=2000)
                except PlaywrightTimeoutError:
                    # Fallback to any combobox in the search form
                    page.wait_for_selector("form[role='search'] [role='combobox']", timeout=2000)
                return
            except PlaywrightTimeoutError:
                pass
        time.sleep(1.0)
    raise TimeoutError("Timed out waiting for Gmail inbox after manual login.")


def search_emails(page, query: str) -> None:
    """Run a Gmail search for the provided query (locale-agnostic)."""
    search_box = page.locator("form[role='search'] input[name='q']")
    if search_box.count() == 0:
        search_box = page.locator("form[role='search'] [role='combobox']")
    target = search_box.first
    target.click()
    target.fill(SEARCH_QUERY)
    target.press("Enter")
    page.wait_for_load_state("domcontentloaded")
    # Wait until results render (threads with class .zA are Gmail rows)
    page.wait_for_selector("div[role='main'] .zA", timeout=DEFAULT_TIMEOUT_MS)


def iter_search_result_threads(page) -> Iterable:
    """Yield locators for each thread row in the results."""
    # Each email row in results is commonly tr.zA or div.zA under role=main; target broadly
    return page.locator("div[role='main'] .zA").all()


def open_thread_and_download_attachments(page, thread_locator, download_dir: str) -> int:
    """Open a thread and download resources.

    Strategy:
    1) Try classic Gmail attachment download buttons (if any).
    2) Also scan the email body for anchor links whose text or href indicates a direct download
       (e.g., contains 'download', 'bestand', 'mijnstudiezaal', 'archieven').
    """
    thread_locator.click()
    page.wait_for_load_state("domcontentloaded")

    total_downloaded = 0

    # Attachments section renders chips/cards with a download button. Try multiple selectors.
    # Primary: buttons with data-tooltip="Download"
    attachment_download_buttons = page.locator("[data-tooltip='Download']")

    # Fallbacks: aria-label contains Download, or command="dl"
    if attachment_download_buttons.count() == 0:
        attachment_download_buttons = page.locator("[aria-label^='Download']")
    if attachment_download_buttons.count() == 0:
        attachment_download_buttons = page.locator("[command='dl']")

    # Some attachments render as list with role button and has a title attribute
    # We'll attempt to capture file names from sibling attributes when possible

    button_count = attachment_download_buttons.count()
    for i in range(button_count):
        button = attachment_download_buttons.nth(i)
        try:
            with page.expect_download(timeout=DEFAULT_TIMEOUT_MS) as download_info:
                button.click()
            download = download_info.value
            suggested_name = generate_safe_filename(download.suggested_filename)
            target_path = str(Path(download_dir) / suggested_name)
            download.save_as(target_path)
            print(f"Downloaded: {target_path}")
            total_downloaded += 1
        except PlaywrightTimeoutError:
            print("Timed out waiting for a download from this attachment button; skipping.")
        except Error as e:
            print(f"Playwright error while downloading attachment: {e}")

    # 2) Look for download links inside the email body
    # Gmail message body container often has role="listitem" and content area div[role='listitem'] article or just a div inside [role='main']
    # We'll search broadly for anchors with href and matching text/href
    candidate_links = page.locator(
        "div[role='main'] a[href]"
    ).filter(
        has_text=re.compile(r"download|bestand|bestanden|mijnstudiezaal|archieven", re.IGNORECASE)
    )

    # If no text match, try href match
    if candidate_links.count() == 0:
        candidate_links = page.locator("div[role='main'] a[href*='download'], div[role='main'] a[href*='mijnstudiezaal'], div[role='main'] a[href*='archieven']")

    link_count = candidate_links.count()
    for i in range(link_count):
        link = candidate_links.nth(i)
        # Prefer handling popup tabs as some links open in new tab
        try:
            # Attempt popup/new tab first
            context = page.context
            with context.expect_page(timeout=5000) as popup_info:
                link.click(button="left")
            new_page = popup_info.value
            new_page.wait_for_load_state("domcontentloaded")
            try:
                with new_page.expect_download(timeout=DEFAULT_TIMEOUT_MS) as dlinfo:
                    # Some pages trigger download automatically; if not, try clicking visible primary buttons
                    pass
            except PlaywrightTimeoutError:
                # Try clicking a visible button that likely triggers download
                try:
                    primary_btn = new_page.locator("a[href*='download'], a[download], button:has-text('Download')").first
                    with new_page.expect_download(timeout=DEFAULT_TIMEOUT_MS) as dlinfo:
                        primary_btn.click()
                    download = dlinfo.value
                    suggested_name = generate_safe_filename(download.suggested_filename)
                    target_path = str(Path(download_dir) / suggested_name)
                    download.save_as(target_path)
                    print(f"Downloaded via popup: {target_path}")
                    total_downloaded += 1
                except Exception:
                    pass
            else:
                download = dlinfo.value
                suggested_name = generate_safe_filename(download.suggested_filename)
                target_path = str(Path(download_dir) / suggested_name)
                download.save_as(target_path)
                print(f"Downloaded via popup: {target_path}")
                total_downloaded += 1
            finally:
                try:
                    new_page.close()
                except Error:
                    pass
        except PlaywrightTimeoutError:
            # No popup; expect download in the same page
            try:
                with page.expect_download(timeout=DEFAULT_TIMEOUT_MS) as dlinfo:
                    link.click(button="left")
                download = dlinfo.value
                suggested_name = generate_safe_filename(download.suggested_filename)
                target_path = str(Path(download_dir) / suggested_name)
                download.save_as(target_path)
                print(f"Downloaded via inline link: {target_path}")
                total_downloaded += 1
            except PlaywrightTimeoutError:
                print("Clicked a link but no download started; skipping.")
            except Error as e:
                print(f"Error while trying link download: {e}")

    # Go back to results
    page.go_back()
    page.wait_for_load_state("domcontentloaded")
    # Ensure results still visible
    page.wait_for_selector("div[role='main'] .zA", timeout=DEFAULT_TIMEOUT_MS)

    return total_downloaded


def main() -> None:
    ensure_directory(DOWNLOAD_DIR)

    pw = sync_playwright().start()
    page = None
    context = None

    if USE_EXISTING_CHROME:
        # Attach to an already running Chrome via CDP (remote debugging)
        # Start Chrome first: chrome.exe --remote-debugging-port=9222
        last_error = None
        browser = None
        for url in CHROME_CDP_URLS:
            try:
                browser = pw.chromium.connect_over_cdp(url)
                break
            except Exception as e:  # noqa: BLE001 - surface helpful message
                last_error = e
                continue
        if browser is None:
            print("Could not connect to an existing Chrome via CDP.")
            print("Tried URLs:", ", ".join(CHROME_CDP_URLS))
            print("Error:", last_error)
            print("Falling back to launching Chrome persistently from the script...")
        else:
            context = browser.contexts[0] if browser.contexts else browser.new_context(accept_downloads=True)
            page = context.pages[0] if context.pages else context.new_page()

    if page is None:
        # Launch installed Google Chrome with a persistent user profile
        # Requires: python -m playwright install chrome
        context = pw.chromium.launch_persistent_context(
            USER_DATA_DIR,
            channel="chrome",
            headless=False,
            accept_downloads=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.new_page()
    page.set_default_timeout(DEFAULT_TIMEOUT_MS)

    try:
        print("Opening Gmail...")
        page.goto("https://mail.google.com/mail/u/0/#inbox")
        page.wait_for_load_state("domcontentloaded")

        print("Please complete Gmail login in the opened browser window. Waiting for inbox...")
        wait_for_gmail_inbox(page)
        print("Inbox detected.")

        print(f"Running search: {SEARCH_QUERY}")
        search_emails(page, SEARCH_QUERY)

        threads = list(iter_search_result_threads(page))
        if not threads:
            print("No threads found for the given search query.")
            return

        if MAX_THREADS is not None:
            threads = threads[:MAX_THREADS]

        total_downloads = 0
        for idx, thread in enumerate(threads, start=1):
            try:
                print(f"Opening thread {idx}/{len(threads)}...")
                total_downloads += open_thread_and_download_attachments(page, thread, DOWNLOAD_DIR)
                # Small delay between threads to be gentle on Gmail
                time.sleep(1.0)
            except Error as e:
                print(f"Error processing thread {idx}: {e}")
                continue

        print(f"Completed. Total attachments downloaded: {total_downloads}")
    finally:
        if not USE_EXISTING_CHROME:
            print("Closing browser context...")
            context.close()
        else:
            print("Leaving your existing Chrome open.")
        print("Stopping Playwright service...")
        pw.stop()


if __name__ == "__main__":
    main()
