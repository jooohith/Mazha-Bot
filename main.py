import io
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime, timedelta
import pytz
import requests
import pdfplumber
import feedparser

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
PDF_URL = "https://mausam.imd.gov.in/thiruvananthapuram/mcdata/district_rainfall_forecast.pdf"
CACHE_FILE = "last_forecast.txt"

NEWS_QUERY = "Ernakulam (holiday OR അവധി OR collector) when:1d"
ENCODED_QUERY = urllib.parse.quote(NEWS_QUERY)
GOOGLE_NEWS_RSS = f"https://news.google.com/rss/search?q={ENCODED_QUERY}&hl=en-IN&gl=IN&ceid=IN:en"

def resolve_clean_url(url):
    """Resolves Google News RSS redirect links to clean direct URLs."""
    try:
        res = requests.head(url, allow_redirects=True, timeout=5)
        return res.url
    except Exception:
        return url

def check_district_holiday():
    """Fetches a single news headline strictly regarding Ernakulam holidays for today or tomorrow."""
    try:
        feed = feedparser.parse(GOOGLE_NEWS_RSS)
        holiday_keywords = ["അവധി", "holiday", "collector", "കലക്ടർ"]
        
        ist = pytz.timezone('Asia/Kolkata')
        now_ist = datetime.now(ist)
        
        yesterday_ist = now_ist - timedelta(days=1)
        yesterday_num = yesterday_ist.strftime("%d").lstrip("0")
        
        yesterday_patterns = [
            f"august {yesterday_num}", f"aug {yesterday_num}",
            f"{yesterday_num} august", f"{yesterday_num} aug",
            f"അഗസ്റ്റ് {yesterday_num}", f"{yesterday_num} അഗസ്റ്റ്"
        ]

        for entry in feed.entries[:10]:
            title = entry.get("title", "").strip()
            summary = entry.get("summary", "")
            raw_link = entry.get("link", "")
            combined_text = (title + " " + summary).lower()

            if any(hk in combined_text for hk in holiday_keywords):
                published_parsed = entry.get("published_parsed")
                if published_parsed:
                    pub_time_epoch = time.mktime(published_parsed)
                    pub_dt = datetime.fromtimestamp(pub_time_epoch, tz=pytz.utc).astimezone(ist)
                    
                    if pub_dt.date() < now_ist.date() and (now_ist - pub_dt) > timedelta(hours=4):
                        continue

                if any(yp in combined_text for yp in yesterday_patterns):
                    continue

                clean_link = resolve_clean_url(raw_link)
                source = entry.get("source", {}).get("title", "News Outlet")
                return f"🚨 **DISTRICT HOLIDAY COVERAGE FOUND ({source}):**\n[{title}]({clean_link})"
    except Exception as e:
        print(f"Error checking Google News RSS: {e}")

    return None

def get_severity_details(intensity):
    """Maps IMD intensity codes to visual progress bars, hex colors, and severity levels."""
    intensity_upper = str(intensity).upper()
    
    if "XH" in intensity_upper or "EXTREMELY HEAVY" in intensity_upper:
        return "🟥🟥🟥🟥🟥 (Extremely Heavy)", 0xFF0000, 5
    elif "VH" in intensity_upper or "VERY HEAVY" in intensity_upper:
        return "🟧🟧🟧🟧⬜ (Very Heavy)", 0xE74C3C, 4
    elif "ISOL. H" in intensity_upper or "ISOL . H" in intensity_upper:
        # 🟡 Yellow Alert (Isolated Heavy)
        return "🟨🟨⬜⬜⬜ (Heavy)", 0xF1C40F, 3
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

            issue_time_match = re.search(r"Time of Issue:\s*([^\n]+)", raw_text, re.IGNORECASE)
            issue_time = issue_time_match.group(1).strip() if issue_time_match else "N/A"

            date_match = re.search(r"\b(\d{1,2}\s+[A-Za-z]+\s+\d{4})\b", raw_text)
            issue_date = date_match.group(1).strip() if date_match else ""

            full_issue_stamp = f"{issue_date} @ {issue_time}".strip(" @")

            tables = first_page.extract_tables()
            for table in tables:
                header_row = table[0]
                dates = [str(cell).replace('\n', '').strip() for cell in header_row[1:] if cell]

                for idx, row in enumerate(table):
                    if row and len(row) > 0 and row[0] and "Ernakulam" in str(row[0]):
                        next_row = table[idx + 1] if idx + 1 < len(table) else []
                        
                        row_1_label = str(row[1]).lower() if len(row) > 1 and row[1] else ""
                        
                        if "intensity" in row_1_label:
                            raw_intensity = row[2:]
                            raw_prob = next_row[2:] if next_row else []
                        else:
                            raw_prob = row[2:]
                            raw_intensity = next_row[2:] if next_row else []

                        intensity_vals = [str(c).replace('\n', ' ').strip() for c in raw_intensity if c]
                        prob_vals = [str(c).replace('\n', ' ').strip() for c in raw_prob if c]

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

def has_forecast_changed(forecasts, issue_stamp, holiday_alert):
    current_text = f"{issue_stamp} | {holiday_alert} | " + " | ".join([f"{f['date']}:{f['intensity']}:{f['probability']}" for f in forecasts])
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            if f.read().strip() == current_text:
                return False
    with open(CACHE_FILE, "w") as f:
        f.write(current_text)
    return True

def send_discord_notification(forecasts, issue_stamp, holiday_alert, is_changed=True):
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

    ist = pytz.timezone('Asia/Kolkata')
    checked_time_str = datetime.now(ist).strftime("%I:%M %p IST")

    description_parts = []

    # Status header depending on whether data changed
    if is_changed:
        description_parts.append("🚨 **NEW UPDATE / FORECAST CHANGED**\n")
    else:
        description_parts.append("ℹ️ **REGULAR STATUS CHECK: No new forecast updates or holiday changes.**\n")

    if holiday_alert:
        description_parts.append(f"{holiday_alert}\n")

    description_parts.append(f"📌 **IMD Issue Bulletin:** `{issue_stamp}`\n")
    description_parts.append(f"{persona_commentary}\n")
    description_parts.append(f"{advisory}\n")
    description_parts.append(f"📄 [View Official IMD PDF]({PDF_URL})")

    description_text = "\n".join(description_parts)

    payload = {
        "username": "Ernakulam Weather Radar",
        "avatar_url": "https://upload.wikimedia.org/wikipedia/commons/9/91/India_Meteorological_Department_logo.png",
        "embeds": [{
            "title": "🎙️ Ernakulam District Rainfall Dispatch",
            "description": description_text,
            "color": embed_color if is_changed else 0x7F8C8D,  # Grey header if no change
            "fields": embed_fields,
            "footer": {"text": f"Checked at {checked_time_str} • IMD Tracker • Ernakulam"}
        }]
    }

    res = requests.post(DISCORD_WEBHOOK_URL, json=payload)
    if res.status_code in [200, 204]:
        print("Successfully sent update to Discord!")
    else:
        print(f"Failed to send: {res.status_code}, {res.text}")

if __name__ == "__main__":
    forecasts, issue_stamp = get_ernakulam_data()
    holiday_alert = check_district_holiday()

    if forecasts:
        changed = has_forecast_changed(forecasts, issue_stamp, holiday_alert)
        if changed:
            print("New update detected! Sending alert to Discord...")
            send_discord_notification(forecasts, issue_stamp, holiday_alert, is_changed=True)
        else:
            print("No change detected, sending status update to Discord...")
            send_discord_notification(forecasts, issue_stamp, holiday_alert, is_changed=False)
    else:
        print("Could not retrieve forecast data.")
