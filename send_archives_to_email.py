# Save this code as a Python file (e.g., run_playwright.py)
from playwright.sync_api import sync_playwright, Error

print("Starting the Playwright script...")

# Manually start the Playwright service
p = sync_playwright().start()

# Launch the browser in 'headed' mode (so you can see it)
browser = p.chromium.launch(headless=False)

# Create a new page (like a new tab)
page = browser.new_page()

# Navigate to the specified URL
print("Navigating to the URL...")
page.goto("https://hetutrechtsarchief.nl/collectie/609C5BCE05EA4642E0534701000A17FD")

# Close the browser window
print("Closing the browser.")
browser.close()

# This block will always execute, ensuring Playwright is stopped cleanly.
print("Stopping the Playwright service.")
p.stop()

