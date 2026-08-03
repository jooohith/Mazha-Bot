import io
import os
import requests
import pdfplumber

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
PDF_URL = "https://mausam.imd.gov.in/thiruvananthapuram/mcdata/district_rainfall_forecast.pdf"
CACHE_FILE = "last_forecast.txt"

def get_ernakulam_data():
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(PDF_URL, headers=headers, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"Error downloading PDF: {e}")
        return None

    try:
        with pdfplumber.open(io.BytesIO(response.content)) as pdf:
            first_page = pdf.pages[0]
            tables = first_page.extract_tables()
            
            for table in tables:
                for idx, row in enumerate(table):
                    # Find Ernakulam in the table row
                    if row and len(row) > 0 and row[0] and "Ernakulam" in str(row[0]):
                        # Intensity values start from index 2 onwards in Row 1
                        intensity_vals = " | ".join([str(c).replace('\n', ' ') for c in row[2:] if c])
                        
                        # Grab Probability values from the very next row below it
                        prob_row = table[idx + 1] if idx + 1 < len(table) else []
                        prob_vals = " | ".join([str(c).replace('\n', ' ') for c in prob_row[2:] if c])
                        
                        return {
                            "district": "Ernakulam",
                            "intensity": intensity_vals if intensity_vals else "N/A",
                            "probability": prob_vals if prob_vals else "N/A"
                        }
    except Exception as e:
        print(f"Error parsing PDF: {e}")
        return None

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
