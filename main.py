import io
import os
import re
import sys
from datetime import datetime
import pytz
import requests
import pdfplumber

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
PDF_URL = "https://mausam.imd.gov.in/thiruvananthapuram/mcdata/district_rainfall_forecast.pdf"
CACHE_FILE = "last_forecast.txt"

def get_severity_details(intensity):
    """Maps IMD intensity codes to visual progress bars, hex colors, and severity levels."""
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

def generate_commute_advisory(max_score):
    """Generates commuting/riding tips based on overall severity."""
    if max_score >= 4:
        return "🚨 **Commute Alert:** Severe downpours expected! Expect traffic slowdowns, potential waterlogging in low-lying areas, and poor visibility."
    elif max_score == 3:
        return "🛵 **Road Advisory:** Heavy rain patches likely. Keep rain gear handy and watch for slick road surfaces."
    else:
        return "🟢 **Commute Advisory:** Weather looks manageable. Good conditions for standard daily travel!"

def generate_weather_presenter_commentary(forecasts):
    """Generates dynamic AI Weather Presenter persona commentary."""
    heavy_days = [f['date'] for f in forecasts if get_severity_details(f['intensity'])[2] >= 3]
    calm_days = [f['date'] for f in forecasts if get_severity_details(f['intensity'])[2] <= 2]
    
    if len(heavy_days) >= 3:
        days_str = ", ".join(heavy_days[:-1]) + f" and {heavy_days[-1]}"
        return f"🚨 *'Grab your heavy-duty umbrellas, Ernakulam! ☔ IMD is predicting solid downpours on {days_str}.'* "
    elif len(heavy_days) == 2:
        return f"🌧️ *'Keep your rain gear on standby, Ernakulam! Heavy rain is likely hitting us on {heavy_days[0]} and {heavy_days[1]}.'* "
    elif len(heavy_days) == 1:
        comment = f"⚠️ *'Watch out on {heavy_days[0]}! Rain is picking up heavy for a bit, but the rest of the week stays manageable.'*"
        if calm_days:
            comment += f" *({calm_days[0]} looks safe to leave the heavy raincoat home!)*"
        return comment
    else:
        return "☀️ *'Good news, Ernakulam! No crazy downpours on the radar—just light to moderate showers scattered through the week.'*"

def get_ernakulam_data():
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(PDF_URL, headers=headers, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"Error downloading PDF: {e}")
        return None, None

    try:
        with pdfplumber.open(io.BytesIO(response.content)) as pdf:
            first_page = pdf.pages[0]
            raw_text = first_page.extract_text() or ""
            
            # --- Extract Issue Date & Time from PDF Text ---
            issue_time_match = re.search(r"Time of Issue:\s*([^\n]+)", raw_text, re.IGNORECASE)
            issue_time = issue_time_match.group(1).strip() if issue_time_match else "N/A"
            
            # Look for date pattern like "03 August 2026"
            date_match = re.search(r"\b(\d{1,2}\s+[A-Za-z]+\s+\d{4})\b", raw_text)
            issue_date = date_match.group(1).strip() if date_match else ""
            
            full_issue_stamp = f"{issue_date} @ {issue_time}".strip(" @")

            # --- Parse Forecast Tables ---
            tables = first_page.extract_tables()
            for table in tables:
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
                        return daily_forecasts, full_issue_stamp
    except Exception as e:
        print(f"Error parsing PDF: {e}")
        return None, None
        
    return None, None

def has_forecast_changed(forecasts, issue_stamp):
    current_text = f"{issue_stamp} | " + " | ".join([f"{f['date']}:{f['intensity']}:{f['probability']}" for f in forecasts])
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            if f.read().strip() == current_text:
                return False
    with open(CACHE_FILE, "w") as f:
        f.write(current_text)
    return True

def send_discord_notification(forecasts, issue_stamp):
    if not DISCORD_WEBHOOK_URL:
        print("ERROR: DISCORD_WEBHOOK_URL environment variable is not set!")
        sys.exit(1)

    embed_fields = []
    max_severity_score = 0
    embed_color = 0x3498DB

    for f in forecasts:
        bar_text, color_code, score = get_severity_details(f['intensity'])
        if score > max_severity_score:
            max_severity_score = score
            embed_color = color_code

        embed_fields.append({
            "name": f"📅 {f['date']}",
            "value": f"**Severity:** {bar_text}\n**Intensity:** `{f['intensity']}`\n**Probability:** `{f['probability']}`",
            "inline": True
        })

    persona_commentary = generate_weather_presenter_commentary(forecasts)
    advisory = generate_commute_advisory(max_severity_score)

    # Current IST check timestamp
    ist = pytz.timezone('Asia/Kolkata')
    checked_time_str = datetime.now(ist).strftime("%I:%M %p IST")

    description_text = (
        f"📌 **IMD Issue Bulletin:** `{issue_stamp}`\n\n"
        f"{persona_commentary}\n\n"
        f"{advisory}\n\n"
        f"📄 [View Official IMD PDF]({PDF_URL})"
    )

    payload = {
        "username": "Ernakulam Weather Radar",
        "avatar_url": "https://upload.wikimedia.org/wikipedia/commons/9/91/India_Meteorological_Department_logo.png",
        "embeds": [{
            "title": "🎙️ Ernakulam District Rainfall Dispatch",
            "description": description_text,
            "color": embed_color,
            "fields": embed_fields,
            "footer": {"text": f"Checked at {checked_time_str} • IMD Tracker • Ernakulam"}
        }]
    }
    
    res = requests.post(DISCORD_WEBHOOK_URL, json=payload)
    if res.status_code in [200, 204]:
        print("Successfully sent full feature update to Discord!")
    else:
        print(f"Failed to send: {res.status_code}, {res.text}")

if __name__ == "__main__":
    forecasts, issue_stamp = get_ernakulam_data()
    if forecasts:
        if has_forecast_changed(forecasts, issue_stamp):
            print("New update detected! Sending to Discord...")
            send_discord_notification(forecasts, issue_stamp)
        else:
            print("No change in forecast since last check.")
    else:
        print("Could not retrieve forecast data.")
