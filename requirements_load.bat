@echo off
chcp 65001 > nul
echo Creating conda environment 'memories_project' with Python 3.9...
conda create -n memories_project python=3.9 -y

echo Activating environment...
call conda activate memories_project

echo Installing packages from requirements.txt...
pip install playwright==1.47.0 python-dotenv==1.0.1 pydantic==2.8.2 pydantic[email] email-validator==2.1.1 pydantic-email-validator==0.1.0

echo Installing Chromium browser for Playwright...
playwright install chromium

echo.
echo Environment setup complete!
echo To activate the environment manually, run:
echo conda activate memories_project
echo.
echo To test the installation, run:
echo python -c "from playwright.sync_api import sync_playwright; print('✓ Playwright imported successfully')"
pause