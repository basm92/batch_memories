from google import genai
from google.genai import types
from dotenv import load_dotenv
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import date, datetime
import os

load_dotenv('environ.env')  

# --- API Key Setup ---
try:
    # Attempt to get the API key from the environment variable
    GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
    if not GOOGLE_API_KEY:
        raise ValueError("GOOGLE_API_KEY environment variable not set.")
    client = genai.Client(api_key=GOOGLE_API_KEY)
    print("API Key configured successfully.")
except ValueError as e:
    print(f"Error: {e}")
    print("Please set the GOOGLE_API_KEY environment variable.")
    print("Get your key from: https://aistudio.google.com/app/apikey")
except Exception as e:
    print(f"An unexpected error occurred during configuration: {e}")
    
    
# Create the response schema
class FinancialItem(BaseModel):
    """Represents a single asset or liability item."""
    name: str
    value: float

class OverviewSchema(BaseModel):
    """Represents the overview of assets and liabilities."""
    assets: List[FinancialItem] = Field(..., alias="Assets")
    liabilities: List[FinancialItem] = Field(..., alias="Liabilities")

class EstateDataSchema(BaseModel):
    """Pydantic schema for the estate data."""
    name: str = Field(..., alias="Name")
    date_of_death: datetime = Field(..., alias="Date of Death")
    net_assets: float = Field(..., alias="Baten (Net Assets)")
    net_liabilities: float = Field(..., alias="Schulden en Lasten (Net Liabilities)")
    net_wealth: float = Field(..., alias="Saldo (Net Wealth)")
    overview: OverviewSchema = Field(..., alias="Overview")

    class Config:
        populate_by_name = True

# Upload the images
uploaded_files = {}
images = [i for i in os.listdir('./example_memorie/example1')]# if i.startswith('NL-HlmNHA_178_2789')]
for i in images:
    uploaded_files[i] = client.files.upload(file=os.path.join('./example_memorie/example1/', i))
# Prompt text
prompt_text = """Transcribe the information present in the images to json."""

# Create the prompt with text and multiple images
# You have to allow billing using the Google Cloud Console or the Google Cloud SDK Online
response = client.models.generate_content(
    model="gemini-2.5-pro-preview-05-06",
    contents=[
        types.Content(
            role="user",
            parts=[types.Part.from_uri(
                    file_uri=uploaded_files[i].uri,
                    mime_type=uploaded_files[i].mime_type,
                ) for i in uploaded_files.keys()
            ] + [types.Part.from_text(text=prompt_text)]
        )
    ],
    config={
      "response_mime_type": "application/json",
      "response_schema": EstateDataSchema
    },
)

print(response.text, file=open('response_ex1.txt', 'w'))
