import io
import os
import sys
import requests
import pdfplumber

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
PDF_URL = "https://mausam.imd.gov.in/thiruvananthapuram/mcdata/district_rainfall_forecast.pdf"
CACHE_FILE = "last_forecast.txt"

def get_severity_details(intensity):
    """Maps IMD intensity codes to visual progress bars, human text, and hex color codes."""
    intensity_upper = str(intensity).upper()
    
    if "XH" in intensity_upper or "EXTREMELY HEAVY" in intensity_upper:
        return "🟥🟥🟥🟥🟥 (Extremely Heavy)", 0xFF0000, 5
    elif "VH" in intensity_upper or "VERY HEAVY" in intensity_upper:
        return "🟥🟥🟥🟥⬜ (Very Heavy)", 0xE74C3C, 4
    elif "H" in intensity_upper or "HEAVY" in intensity_upper:
        return "🟧🟧🟧⬜⬜ (Heavy)", 0xE67E22, 3
    elif "M" in intensity_upper or "L TO M" in intensity_upper or "MODERATE" in intensity_upper:
        return "🟦🟦⬜⬜⬜ (Light to Moderate)", 0x3498DB, 2
    else:
        return "🟩⬜⬜⬜⬜ (Light/None)", 0x2ECC71, 1

def generate_tldr(forecasts):
    """Generates a quick 1-sentence summary based on the highest risk days."""
    heavy_days = [f['date'] for f in forecasts if get_severity_details(f['intensity'])[2] >= 3]
    
    if len(heavy_days) == 1:
        return f"⚠️ Expect heavy rainfall on **{heavy_days[0]}**. Keep rain gear handy!"
    elif len(heavy_days) > 1:
        days_str = ", ".join(heavy_days[:-1]) + f" and {heavy_days[-1]}"
        return f"🚨 Heavy rainfall forecasted for **{days_str}**! Take necessary precautions."
    else:
        return "🟢 Weather looks relatively calm with light-to-moderate rain across Ernakulam."

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
                # Header containing dates
                header_row = table[0]
                dates = [str(cell).replace('\n', '').strip() for cell in header_row[1:] if cell]
                
                for idx, row in enumerate(table):
                    if row and len(row) > 0 and row[0] and "Ernakulam" in str(row[0]):
                        intensity_vals = [str(c).replace('\n', ' ').strip() for c in row[2:] if c]
                        prob_row = table[idx + 1] if idx + 1 < len(table) else []
                        prob_vals = [str(c).replace('\n', ' ').strip() for c in prob_row[2:] if c]
                        
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
    current_text = " | ".join([f"{f['date']}:{f['intensity']}:{f['probability']}" for f in forecasts])
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            if f.read().strip() == current_text:
                return False
    with open(CACHE_FILE, "w") as f:
        f.write(current_text)
    return True

def send_discord_notification(forecasts):
    if not DISCORD_WEBHOOK_URL:
        print("ERROR: DISCORD_WEBHOOK_URL environment variable is not set!")
        sys.exit(1)

    embed_fields = []
    max_severity_score = 0
    embed_color = 0x3498DB  # Default Blue

    for f in forecasts:
        bar_text, color_code, score = get_severity_details(f['intensity'])
        
        # Track the highest severity score to set the overall embed card color
        if score > max_severity_score:
            max_severity_score = score
            embed_color = color_code

        embed_fields.append({
            "name": f"📅 {f['date']}",
            "value": f"**Severity:** {bar_text}\n**Raw:** `{f['intensity']}`\n**Prob:** `{f['probability']}`",
            "inline": True
        })

    tldr_text = generate_tldr(forecasts)

    payload = {
        "username": "Ernakulam Weather Radar",
        "avatar_url": "https://upload.wikimedia.org/wikipedia/commons/9/91/India_Meteorological_Department_logo.png",
        "embeds": [{
            "title": "⛈️ IMD Ernakulam 5-Day Rainfall Forecast",
            "description": f"**Summary:** {tldr_text}\n\n[Click here to open full PDF]({PDF_URL})",
            "color": embed_color,  # Color matches the highest risk level
            "fields": embed_fields,
            "footer": {"text": "Automated GitHub Action Tracker • Ernakulam District"}
        }]
    }
    
    res = requests.post(DISCORD_WEBHOOK_URL, json=payload)
    if res.status_code in [200, 204]:
        print("Successfully sent creative update to Discord!")
    else:
        print(f"Failed to send: {res.status_code}, {res.text}")

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
