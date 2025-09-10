import os
from dotenv import load_dotenv
from pydantic import BaseModel, EmailStr
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout, Error as PWError

load_dotenv()
os.environ['DISPLAY'] = ':1'  # or try ':1' if :0 doesn't work

def scrape_and_send(url, email_to):
    """
    Scrape the given URL and send the result to the specified email address.
    """
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=False)