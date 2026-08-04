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
RADAR_PORTAL_URL = "https://mausam.imd.gov.in/thiruvananthapuram/index_radar.php?id=Kochi"
RADAR_IMAGE_URL = "https://mausam.imd.gov.in/thiruvananthapuram/Radar/Kochi_MAX.gif"
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
    """Fetches news strictly regarding official Ernakulam holiday declarations."""
    try:
        feed = feedparser.parse(GOOGLE_NEWS_RSS)
        
        declaration_phrases = [
            "declared holiday", "declares holiday", "holiday declared", 
            "holiday for schools", "holiday for educational",
            "അവധി പ്രഖ്യാപിച്ചു", "സ്‌കൂളുകൾക്ക് അവധി"
        ]
        
        # Exclude meta/editorial/commentary articles
        ignore_words = ["demands", "demand", "storm", "pressure", "trolls", "social media", "criticism"]
        
        ist = pytz.timezone('Asia/Kolkata')
        now_ist = datetime.now(ist)

        for entry in feed.entries[:10]:
            title = entry.get("title", "").strip()
            summary = entry.get("summary", "")
            raw_link = entry.get("link", "")
            combined_text = (title + " " + summary).lower()

            if any(iw in combined_text for iw in ignore_words):
                continue

            if any(dp in combined_text for dp in declaration_phrases):
                published_parsed = entry.get("published_parsed")
                if published_parsed:
                    pub_time_epoch = time.mktime(published_parsed)
                    pub_dt = datetime.fromtimestamp(pub_time_epoch, tz=pytz.utc).astimezone(ist)
                    
                    if pub_dt.date() < now_ist.date() and (now_ist - pub_dt) > timedelta(hours=4):
                        continue

                clean_link = resolve_clean_url(raw_link)
                source = entry.get("source", {}).get("title", "News Outlet")
                return f"🚨 **DISTRICT HOLIDAY ANNOUNCEMENT ({source}):**\n[{title}]({clean_link})"
    except Exception as e:
        print(f"Error checking Google News RSS: {e}")

    return None

def parse_rgb_to_alert(rgb_tuple):
    """Converts a pdfplumber non_stroking_color tuple into alert details."""
    if not rgb_tuple or not isinstance(rgb_tuple, (tuple, list)):
        return None

    # Scale float RGB tuples (0.0 - 1.0) to (0 - 255)
    if all(isinstance(c, float) and c <= 1.0 for c in rgb_tuple):
        r, g, b = [int(c * 255) for c in rgb_tuple[:3]]
    else:
        r, g, b = [int(c) for c in rgb_tuple[:3]]

    # Precise IMD Warning Categories RGB Matching
    if r > 200 and g < 90:
        return "🟥🟥🟥🟥🟥 (Extremely Heavy / Red Alert)", 0xFF0000, 5
    elif r > 210 and 90 <= g <= 170:
        return "🟧🟧🟧🟧⬜ (Very Heavy / Orange Alert)", 0xE67E22, 4
    elif r > 200 and g > 170 and b < 120:
        return "🟨🟨⬜⬜⬜ (Heavy / Yellow Alert)", 0xF1C40F, 3
    elif g > 140 and r < 120:
        return "🟩⬜⬜⬜⬜ (Light to Moderate / Green Alert)", 0x2ECC71, 1
    
    return None

def get_severity_details(intensity, rgb_tuple=None):
    """Primary RGB spatial matcher with comprehensive string fallbacks."""
    # 1. Direct RGB vector fill matching from PDF
    rgb_result = parse_rgb_to_alert(rgb_tuple)
    if rgb_result:
        return rgb_result

    # 2. String fallback (handles text variants like 'ISOL H to VH*')
    intensity_upper = str(intensity).upper()
    if "H TO VH" in intensity_upper or "VH*" in intensity_upper or "EXTREMELY" in intensity_upper:
        return "🟥🟥🟥🟥🟥 (Extremely Heavy / Red Alert)", 0xFF0000, 5
    elif "VH" in intensity_upper or "VERY HEAVY" in intensity_upper:
        return "🟧🟧🟧🟧⬜ (Very Heavy / Orange Alert)", 0xE67E22, 4
    elif "ISOL. H" in intensity_upper or "ISOL . H" in intensity_upper or "ISOL H" in intensity_upper:
        return "🟨🟨⬜⬜⬜ (Heavy / Yellow Alert)", 0xF1C40F, 3
    elif "H" in intensity_upper or "HEAVY" in intensity_upper:
        return "🟧🟧🟧⬜⬜ (Heavy)", 0xE67E22, 3
    elif "M" in intensity_upper or "L TO M" in intensity_upper:
        return "🟦🟦⬜⬜⬜ (Light to Moderate)", 0x3498DB, 2
    else:
        return "🟩⬜⬜⬜⬜ (Light/None)", 0x2ECC71, 1

def generate_commute_advisory(max_score):
    if max_score >= 5:
        return "🚨 **Red Alert Commute Warning:** Extremely severe downpours probable! High likelihood of waterlogging, low visibility, and disrupted travel."
    elif max_score == 4:
        return "🟧 **Orange Alert Advisory:** Heavy to very heavy rainfall expected. Leave early, exercise extreme caution, and check for local traffic updates."
    elif max_score == 3:
        return "🛵 **Road Advisory:** Heavy rain patches likely. Keep rain gear handy and watch for slick road surfaces."
    else:
        return "🟢 **Commute Advisory:** Weather looks manageable. Normal conditions for standard daily travel!"

def generate_weather_presenter_commentary(forecasts):
    heavy_days = [f['date'] for f in forecasts if get_severity_details(f['intensity'], f.get('color'))[2] >= 3]
    calm_days = [f['date'] for f in forecasts if get_severity_details(f['intensity'], f.get('color'))[2] <= 2]
    
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

            # Extract fill rects with valid background colors
            colored_rects = [
                r for r in first_page.rects 
                if r.get("non_stroking_color") and r.get("non_stroking_color") not in [(0,), (1,), (0,0,0), (1,1,1)]
            ]

            tables_with_positions = first_page.find_tables()

            for tbl in tables_with_positions:
                extracted_table = tbl.extract()
                
                for row_idx, row in enumerate(extracted_table):
                    if row and len(row) > 0 and row[0] and "Ernakulam" in str(row[0]):
                        header_row = extracted_table[0]
                        dates = [str(cell).replace('\n', '').strip() for cell in header_row[1:] if cell]

                        next_row = extracted_table[row_idx + 1] if row_idx + 1 < len(extracted_table) else []
                        
                        row_1_label = str(row[1]).lower() if len(row) > 1 and row[1] else ""
                        
                        if "intensity" in row_1_label:
                            raw_intensity = row[2:]
                            raw_prob = next_row[2:] if next_row else []
                            target_row_idx = row_idx
                        else:
                            raw_prob = row[2:]
                            raw_intensity = next_row[2:] if next_row else []
                            target_row_idx = row_idx + 1

                        intensity_vals = [str(c).replace('\n', ' ').strip() for c in raw_intensity if c]
                        prob_vals = [str(c).replace('\n', ' ').strip() for c in raw_prob if c]

                        daily_forecasts = []
                        for i in range(min(len(dates), len(intensity_vals), len(prob_vals))):
                            col_cell_idx = i + 2
                            cell_bbox = tbl.rows[target_row_idx].cells[col_cell_idx]
                            
                            matched_color = None
                            if cell_bbox:
                                cx0, ctop, cx1, cbottom = cell_bbox
                                for r in colored_rects:
                                    rx0, rtop, rx1, rbottom = r['x0'], r['top'], r['x1'], r['bottom']
                                    if abs(rx0 - cx0) < 15 and abs(rtop - ctop) < 15:
                                        matched_color = r.get("non_stroking_color")
                                        break

                            daily_forecasts.append({
                                "date": dates[i],
                                "intensity": intensity_vals[i],
                                "probability": prob_vals[i],
                                "color": matched_color
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
        bar_text, color_code, score = get_severity_details(f['intensity'], f.get('color'))
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
    description_parts.append(f"📡 [View Live Kochi Interactive Radar Portal]({RADAR_PORTAL_URL})")

    description_text = "\n".join(description_parts)

    payload = {
        "username": "Ernakulam Weather Radar",
        "avatar_url": "https://upload.wikimedia.org/wikipedia/commons/9/91/India_Meteorological_Department_logo.png",
        "embeds": [{
            "title": "🎙️ Ernakulam District Rainfall & Radar Dispatch",
            "description": description_text,
            "color": embed_color if is_changed else 0x7F8C8D,
            "fields": embed_fields,
            "image": {
                "url": RADAR_IMAGE_URL
            },
            "footer": {"text": f"Checked at {checked_time_str} • IMD Radar Tracker • Ernakulam"}
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
