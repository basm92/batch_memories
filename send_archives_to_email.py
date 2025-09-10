# Save this code as a Python file (e.g., run_playwright.py)
from playwright.sync_api import sync_playwright, Error
import re

# Manually start the Playwright service and launch browser
p = sync_playwright().start()
browser = p.chromium.launch(headless=False)

# Create a new page (like a new tab) and navigate to URL
page = browser.new_page()
page.goto("https://hetutrechtsarchief.nl/collectie/609C5BCE05EA4642E0534701000A17FD")
page.wait_for_load_state('domcontentloaded')

# Find all links
all_link_locators = page.locator("a.mi_hyperlink")
links_to_click = []

# Loop through the elements to find valid links
# The \b ensures we match whole words, preventing a match in "12345".
year_pattern = re.compile(r'\b(\d{4})\b')

for i in range(all_link_locators.count()):  
    current_link_locator = all_link_locators.nth(i)  
    text = current_link_locator.text_content()
    # Find all 4-digit numbers within the link's text
    matches = year_pattern.findall(text)
    for year_str in matches:
        try:
            year = int(year_str)
            # Check if the found year is 1877 or later
            if year >= 1877:
                links_to_click.append(current_link_locator)
        except ValueError:
            # This case is unlikely with the regex, but it's safe to include
            continue


def download_given_link(link_locator):
    """
    This needs an active playwright page object. 
    Use this to for loop over the link locators in the list links_to_click.
    This will click the link, find the thumbnail, click it, 
    fill in the email, send the email, close the iframe and close the link.
    """
    link_locator.click()
    parent_div_locator = link_locator.locator('xpath=./ancestor::div[contains(@class, "mi_tree_content")][1]')
    thumbnail_link_locator = parent_div_locator.locator('a.mi_stripthumb').first
    thumbnail_link_locator.click()
    page.wait_for_load_state('domcontentloaded')
    # Find the download button
    iframe_locator = page.frame_locator('iframe[allowtransparency = "true"]')
    download_button_in_frame = iframe_locator.locator('#download')
    download_button_in_frame.click()
    # Step 3: Find box for and insert Email
    iframe_locator.locator("input[type='email']").fill("memoriesretrieval@gmail.com")
    # Step 4: Send Email
    iframe_locator.locator("button[type='submit']").click()
    # Step 5: Close the iframe and go back to main page
    close_button = iframe_locator.get_by_role("button", name=" Sluiten ")
    close_button.click()
    # Step 6: Also close the link
    link_locator.click()


# Loop through the collected links and download each
for link in links_to_click:
    try:
        download_given_link(link)
    except Error as e:
        print(f"An error occurred while processing a link: {e}")
        continue

# Close the browser window
print("Closing the browser.")
browser.close()

# This block will always execute, ensuring Playwright is stopped cleanly.
print("Stopping the Playwright service.")
p.stop()

