import pandas as pd

# Start with url from Utrecht kantoor
url_utrecht = "https://hetutrechtsarchief.nl/collectie/609C5BCE05EA4642E0534701000A17FD"

# Find all a mi_tree_content mi_hyperlink 

#In a loop, click each one
## Find button of class mi_button_a_style
## click it
## copy the text content of div.mi_link_box textarea
## proceed to next iteration

import time
from playwright.sync_api import sync_playwright, TimeoutError

def run_archive_interaction(url: str):
    """
    Automates interaction with Het Utrechts Archief website.

    This script navigates to the provided URL, iterates through specific links,
    opens a share dialog for each, copies the content from a textarea,
    and then closes the dialog before moving to the next link.
    """
    with sync_playwright() as p:
        # Launch the browser. Set headless=False to watch the script in action.
        browser = p.chromium.launch(headless=False, slow_mo=50)
        page = browser.new_page()

        try:
            # Navigate to the starting URL and wait for the page to be fully loaded
            print(f"Navigating to {url}...")
            page.goto(url, wait_until="networkidle", timeout=60000)
            print("Page loaded successfully.")

            # Locate all the target links on the page
            links_locator = page.locator("a.mi_tree_content.mi_hyperlink")
            link_count = links_locator.count()
            print(f"Found {link_count} items to process.")

            extracted_content = []

            # Loop through each link by its index
            # This is more reliable than iterating through a list of elements,
            # as the page might change after a click, making old element references stale.
            for i in range(link_count):
                # Re-locate the link in each iteration to ensure it's fresh
                link = links_locator.nth(i)
                
                try:
                    item_text = link.text_content(timeout=5000).strip()
                    print(f"\n[{i+1}/{link_count}] Processing: '{item_text}'")

                    # 1. Click the tree link
                    link.click()

                    # 2. Find and click the button to open the share/link dialog
                    # We wait for the button to be visible before clicking
                    share_button = page.locator("button.mi_button_a_style").first
                    print("  - Waiting for the share button...")
                    share_button.wait_for(state="visible", timeout=10000)
                    share_button.click()
                    print("  - Clicked the share button.")

                    # 3. Find the textarea and copy its content
                    # The inputValue() method is specifically for form elements
                    textarea = page.locator("div.mi_link_box textarea").first
                    textarea.wait_for(state="visible", timeout=5000)
                    text_content = textarea.input_value() # Use input_value() for textareas. [4,
                    print("hello")
                    
