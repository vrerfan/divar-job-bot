import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
import json
import os
import time

CITIES = [
    "karaj",
    "fardis",
    "nazarabad",
    "hashtgerd",
    "taleghan",
    "eshtehard",
]

BASE_URL = "https://divar.ir"
SEEN_FILE = "seen_ads.json"

headers = {
    "User-Agent": "Mozilla/5.0"
}

if os.path.exists(SEEN_FILE):
    with open(SEEN_FILE, "r", encoding="utf-8") as f:
        seen_ads = json.load(f)
else:
    seen_ads = []

print(f"آگهی‌های قبلی: {len(seen_ads)}")

all_ads = []

for city in CITIES:

    time.sleep(10)

    url = f"{BASE_URL}/s/{city}/jobs"

    print(f"در حال بررسی: {city}")

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=20
        )

        if response.status_code == 429:
            print("⏳ محدودیت دیوار - 30 ثانیه صبر...")
            time.sleep(30)

            response = requests.get(
                url,
                headers=headers,
                timeout=20
            )

        if response.status_code != 200:
            print(f"خطا: {response.status_code}")
            continue

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        for a in soup.find_all("a", href=True):

            href = a["href"]

            if not href.startswith("/v/"):
                continue

            title = a.get_text(" ", strip=True)

            if not title:
                continue

            match = re.search(
                r"/([A-Za-z0-9_-]+)$",
                href
            )

            if not match:
                continue

            ad_id = match.group(1)

            if any(
                x["id"] == ad_id
                for x in all_ads
            ):
                continue

            all_ads.append({
                "id": ad_id,
                "title": title,
                "link": urljoin(
                    BASE_URL,
                    href
                ),
                "city": city
            })

    except Exception as e:
        print(f"خطا در {city}: {e}")


new_ads = [
    ad for ad in all_ads
    if ad["id"] not in seen_ads
]

ads_to_send = new_ads[:10]

print()
print("=" * 60)
print(f"کل آگهی‌ها: {len(all_ads)}")
print(f"آگهی‌های جدید: {len(new_ads)}")
print(f"انتخاب شده: {len(ads_to_send)}")
print("=" * 60)

for i, ad in enumerate(ads_to_send, 1):
    print(f"{i}. {ad['city']} | {ad['id']}")
    print(ad["title"])
    print(ad["link"])
    print()
BOT_TOKEN = 
CHAT_ID = "8531717188"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    data = {
        "chat_id": CHAT_ID,
        "text": message,
        "disable_web_page_preview": False
    }

    response = requests.post(url, data=data, timeout=20)

    print("Telegram:", response.status_code)

    return response.status_code == 200


for ad in ads_to_send:
    message = (
        f"🟢 آگهی استخدام\n\n"
        f"📌 {ad['title']}\n"
        f"📍 {ad['city']}\n\n"
        f"🔗 {ad['link']}"
    )

    if send_telegram(message):
        print(f"✅ ارسال شد: {ad['id']}")
    else:
        print(f"❌ ارسال نشد: {ad['id']}")
# ذخیره آگهی‌های ارسال‌شده
for ad in ads_to_send:
    if ad["id"] not in seen_ads:
        seen_ads.append(ad["id"])

with open(SEEN_FILE, "w", encoding="utf-8") as f:
    json.dump(seen_ads, f, ensure_ascii=False, indent=2)

print(f"💾 تعداد آگهی‌های ذخیره‌شده: {len(seen_ads)}")
