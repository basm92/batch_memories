from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    page.goto("https://hetutrechtsarchief.nl/collectie/609C5BCE05EA4642E0534701000A17FD")

    # This will pause the script and open the Playwright Inspector
    print("Script is paused in the browser. Press the 'Resume' button in the Inspector to continue.")
    page.pause()

    # The script will continue from here after you resume it from the inspector
    print("Script has resumed.")
    print(page.title())

    browser.close()