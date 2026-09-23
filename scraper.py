import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
import json
import os
import time

# شهرهای استان البرز
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

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = "8531717188"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0 Safari/537.36"
}


# -----------------------------
# خواندن آگهی‌های قبلی
# -----------------------------

try:
    with open(SEEN_FILE, "r", encoding="utf-8") as f:
        seen_ads = json.load(f)

    if not isinstance(seen_ads, list):
        seen_ads = []

except Exception:
    seen_ads = []

print(f"آگهی‌های قبلی: {len(seen_ads)}")


# -----------------------------
# دریافت آگهی‌ها
# -----------------------------

all_ads = []

for city in CITIES:

    print(f"در حال بررسی: {city}")

    time.sleep(8)

    url = f"{BASE_URL}/s/{city}/jobs"

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        if response.status_code == 429:
            print("⏳ محدودیت دیوار - 30 ثانیه صبر...")
            time.sleep(30)

            response = requests.get(
                url,
                headers=HEADERS,
                timeout=30
            )

        if response.status_code != 200:
            print(f"❌ خطا در {city}: {response.status_code}")
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

            # جلوگیری از تکرار داخل همین اجرا
            if any(ad["id"] == ad_id for ad in all_ads):
                continue

            all_ads.append({
                "id": ad_id,
                "title": title,
                "link": urljoin(BASE_URL, href),
                "city": city
            })

    except Exception as e:
        print(f"❌ خطا در {city}: {e}")


# -----------------------------
# پیدا کردن آگهی‌های جدید
# -----------------------------

new_ads = [
    ad for ad in all_ads
    if ad["id"] not in seen_ads
]

ads_to_send = new_ads[:10]


print()
print("=" * 60)
print(f"کل آگهی‌ها: {len(all_ads)}")
print(f"آگهی‌های جدید: {len(new_ads)}")
print(f"انتخاب شده برای ارسال: {len(ads_to_send)}")
print("=" * 60)


# -----------------------------
# ارسال به تلگرام
# -----------------------------

def send_telegram(message):

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    data = {
        "chat_id": CHAT_ID,
        "text": message,
        "disable_web_page_preview": False
    }

    try:

        response = requests.post(
            url,
            data=data,
            timeout=30
        )

        print("Telegram:", response.status_code)

        if response.status_code != 200:
            print(response.text)

        return response.status_code == 200

    except Exception as e:

        print("❌ خطای تلگرام:", e)

        return False


# -----------------------------
# ارسال ۱۰ آگهی
# -----------------------------

for ad in ads_to_send:

    message = (
        f"🟢 آگهی استخدام\n\n"
        f"📌 {ad['title']}\n"
        f"📍 {ad['city']}\n\n"
        f"🔗 {ad['link']}"
    )

    if send_telegram(message):

        print(f"✅ ارسال شد: {ad['id']}")

        # بلافاصله بعد از ارسال موفق، ذخیره شود
        if ad["id"] not in seen_ads:
            seen_ads.append(ad["id"])

    else:

        print(f"❌ ارسال نشد: {ad['id']}")


# -----------------------------
# ذخیره وضعیت
# -----------------------------

with open(
    SEEN_FILE,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        seen_ads,
        f,
        ensure_ascii=False,
        indent=2
    )


print()
print(f"💾 تعداد آگهی‌های ذخیره‌شده: {len(seen_ads)}")
print(f"📁 فایل: {os.path.abspath(SEEN_FILE)}")
