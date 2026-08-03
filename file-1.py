import io
import os
import requests
import pdfplumber

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
PDF_URL = "https://mausam.imd.gov.in/thiruvananthapuram/mcdata/district_rainfall_forecast.pdf"
CACHE_FILE = "last_forecast.txt"

def get_ernakulam_data():
    response = requests.get(PDF_URL)
    if response.status_code != 200:
        return None

    with pdfplumber.open(io.BytesIO(response.content)) as pdf:
        first_page = pdf.pages[0]
        tables = first_page.extract_tables()
        
        for table in tables:
            for row in table:
                if row[0] and "Ernakulam" in row[0]:
                    intensity = row[1].replace('\n', ' ') if len(row) > 1 else "N/A"
                    probability = row[2].replace('\n', ' ') if len(row) > 2 else "N/A"
                    return {
                        "district": "Ernakulam",
                        "intensity": intensity,
                        "probability": probability
                    }
    return None

def has_forecast_changed(current_data):
    current_text = f"{current_data['intensity']} | {current_data['probability']}"
    
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            if f.read().strip() == current_text:
                return False  # No change
    
    with open(CACHE_FILE, "w") as f:
        f.write(current_text)
    return True

def send_discord_notification(data):
    payload = {
        "username": "Kerala Weather Alert",
        "avatar_url": "https://upload.wikimedia.org/wikipedia/commons/9/91/India_Meteorological_Department_logo.png",
        "embeds": [{
            "title": "🌧️ IMD District Rainfall Forecast: Ernakulam",
            "description": "New update detected from IMD Thiruvananthapuram.",
            "url": PDF_URL,
            "color": 3447003,
            "fields": [
                {"name": "📊 Rain Intensity", "value": f"`{data['intensity']}`", "inline": False},
                {"name": "🎲 Probability", "value": f"`{data['probability']}`", "inline": False}
            ],
            "footer": {"text": "Automated GitHub Action Tracker"}
        }]
    }
    requests.post(DISCORD_WEBHOOK_URL, json=payload)

if __name__ == "__main__":
    data = get_ernakulam_data()
    if data and has_forecast_changed(data):
        print("New update detected! Sending to Discord...")
        send_discord_notification(data)
    else:
        print("No change in forecast or failed to fetch.")