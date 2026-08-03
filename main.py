import io
import os
import sys
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
                # 1. Grab dates from the top header row (skipping labels in index 0 & 1)
                header_row = table[0]
                dates = [str(cell).replace('\n', '').strip() for cell in header_row[1:] if cell]
                
                # 2. Search for Ernakulam
                for idx, row in enumerate(table):
                    if row and len(row) > 0 and row[0] and "Ernakulam" in str(row[0]):
                        
                        # Intensity values (Row 1)
                        intensity_vals = [str(c).replace('\n', ' ').strip() for c in row[2:] if c]
                        
                        # Probability values (Next row down)
                        prob_row = table[idx + 1] if idx + 1 < len(table) else []
                        prob_vals = [str(c).replace('\n', ' ').strip() for c in prob_row[2:] if c]
                        
                        # Build a list of per-day dictionary items
                        daily_forecasts = []
                        for i in range(min(len(dates), len(intensity_vals), len(prob_vals))):
                            daily_forecasts.append({
                                "date": dates[i],
                                "intensity": intensity_vals[i],
                                "probability": prob_vals[i]
                            })
                            
                        return daily_forecasts
    except Exception as e:
        print(f"Error parsing PDF: {e}")
        return None

    return None

def has_forecast_changed(forecasts):
    # Create a string footprint to compare against last saved forecast
    current_text = " | ".join([f"{f['date']}:{f['intensity']}:{f['probability']}" for f in forecasts])
    
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            if f.read().strip() == current_text:
                return False  # No change
    
    with open(CACHE_FILE, "w") as f:
        f.write(current_text)
    return True

def send_discord_notification(forecasts):
    if not DISCORD_WEBHOOK_URL:
        print("ERROR: DISCORD_WEBHOOK_URL environment variable is not set!")
        sys.exit(1)

    # Format fields per day for Discord
    embed_fields = []
    for f in forecasts:
        embed_fields.append({
            "name": f"📅 {f['date']}",
            "value": f"**Intensity:** `{f['intensity']}`\n**Probability:** `{f['probability']}`",
            "inline": True  # Shows dates side-by-side on desktop
        })

    payload = {
        "username": "Kerala Weather Alert",
        "avatar_url": "https://upload.wikimedia.org/wikipedia/commons/9/91/India_Meteorological_Department_logo.png",
        "embeds": [{
            "title": "🌧️ IMD District Rainfall Forecast: Ernakulam",
            "description": "5-Day Forecast breakdown parsed from IMD Thiruvananthapuram.",
            "url": PDF_URL,
            "color": 3447003,
            "fields": embed_fields,
            "footer": {"text": "Automated GitHub Action Tracker"}
        }]
    }
    
    res = requests.post(DISCORD_WEBHOOK_URL, json=payload)
    if res.status_code in [200, 204]:
        print("Successfully sent update to Discord!")
    else:
        print(f"Failed to send to Discord: {res.status_code}, {res.text}")

if __name__ == "__main__":
    forecasts = get_ernakulam_data()
    if forecasts:
        if has_forecast_changed(forecasts):
            print("New update detected! Sending to Discord...")
            send_discord_notification(forecasts)
        else:
            print("No change in forecast since last check.")
    else:
        print("Could not retrieve forecast data.")
