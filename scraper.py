import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
import json
import os
import time


# ==========================================
# تنظیمات
# ==========================================

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
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    )
}


# ==========================================
# خواندن آگهی‌های قبلی
# ==========================================

try:
    with open(SEEN_FILE, "r", encoding="utf-8") as f:
        seen_ads = json.load(f)

    if not isinstance(seen_ads, list):
        seen_ads = []

except Exception:
    seen_ads = []

print(f"آگهی‌های قبلی: {len(seen_ads)}")


# ==========================================
# دریافت صفحه آگهی
# ==========================================

def get_ad_page(link):

    try:

        response = requests.get(
            link,
            headers=HEADERS,
            timeout=30
        )

        print(
            f"دریافت آگهی: {response.status_code}"
        )

        if response.status_code != 200:
            return None

        return BeautifulSoup(
            response.text,
            "html.parser"
        )

    except Exception as e:

        print(
            f"⚠️ خطا در دریافت آگهی: {e}"
        )

        return None


# ==========================================
# استخراج اطلاعات ساختاریافته Divar
# ==========================================

def extract_divar_fields(soup):

    fields = {}

    if not soup:
        return fields

    rows = soup.select(
        'div[data-testid="unexpandable-info-row"]'
    )

    print(
        f"تعداد فیلدهای پیدا شده: {len(rows)}"
    )

    for row in rows:

        title_element = row.select_one(
            ".kt-unexpandable-row__title"
        )

        value_element = row.select_one(
            ".kt-unexpandable-row__value"
        )

        if not title_element or not value_element:
            continue

        field_name = title_element.get_text(
            " ",
            strip=True
        )

        field_value = value_element.get_text(
            " ",
            strip=True
        )

        if not field_name or not field_value:
            continue

        fields[field_name] = field_value

        print(
            f"فیلد: {field_name} = {field_value}"
        )

    return fields


# ==========================================
# استخراج توضیحات واقعی آگهی
# ==========================================

def extract_real_description(soup, title):

    if not soup:
        return ""

    # کلاس‌های رایج توضیحات آگهی
    possible_selectors = [
        '[data-testid="description"]',
        '.kt-description-row__text',
        '.kt-description-row',
    ]

    for selector in possible_selectors:

        element = soup.select_one(
            selector
        )

        if element:

            text = element.get_text(
                "\n",
                strip=True
            )

            if text:

                lines = []

                for line in text.splitlines():

                    line = line.strip()

                    if not line:
                        continue

                    if line == title:
                        continue

                    if "divar.ir" in line.lower():
                        continue

                    if line not in lines:
                        lines.append(line)

                return "\n".join(lines)

    return ""


# ==========================================
# دریافت اطلاعات کامل آگهی
# ==========================================

def get_ad_details(link, title):

    soup = get_ad_page(link)

    if not soup:
        return {
            "fields": {},
            "description": ""
        }

    fields = extract_divar_fields(
        soup
    )

    description = extract_real_description(
        soup,
        title
    )

    return {
        "fields": fields,
        "description": description
    }


# ==========================================
# ساخت متن آگهی
# ==========================================

def build_channel_post(ad):

    title = ad["title"]

    fields = ad.get(
        "fields",
        {}
    )

    description = ad.get(
        "description",
        ""
    )

    post = []

    # ======================================
    # عنوان
    # ======================================

    post.append(
        f"# 🟢 {title}"
    )

    post.append("")

    # ======================================
    # عنوان شغلی
    # ======================================

    post.append(
        f"🟢 عنوان شغلی: {title}"
    )

    # ======================================
    # تبدیل نام فیلدهای Divar
    # ======================================

    field_map = {
        "جنسیت": "جنسیت",
        "محدوده سنی": "محدوده سنی",
        "سن": "محدوده سنی",
        "سابقه کاری": "سابقه کار",
        "سابقه کار": "سابقه کار",
        "نوع همکاری": "نوع همکاری",
        "ساعت کاری": "ساعت کاری",
        "حقوق": "حقوق",
        "دستمزد": "حقوق",
        "شیوهٔ پرداخت": "پرداخت",
        "شیوه پرداخت": "پرداخت",
        "نحوه پرداخت": "پرداخت",
        "نوع استخدام": "نوع استخدام",
    }

    added_fields = set()

    for divar_name, channel_name in field_map.items():

        if divar_name not in fields:
            continue

        value = fields[
            divar_name
        ].strip()

        if not value:
            continue

        if channel_name in added_fields:
            continue

        post.append(
            f"🟢 {channel_name}: {value}"
        )

        added_fields.add(
            channel_name
        )

    # ======================================
    # توضیحات
    # ======================================

    if description:

        post.append("")
        post.append(
            "### 🟢 توضیحات"
        )

        lines = description.splitlines()

        count = 0

        for line in lines:

            line = line.strip()

            if not line:
                continue

            if line == title:
                continue

            if "divar.ir" in line.lower():
                continue

            post.append(
                f"🟢 {line}"
            )

            count += 1

            if count >= 25:
                break

    # ======================================
    # پایان ثابت
    # ======================================

    post.append("")

    post.append(
        "کانال تلگرام"
    )

    post.append(
        "@karyabi_alborzi"
    )

    post.append("")

    post.append(
        "جهت ثبت آگهی"
    )

    post.append(
        "@Karyabi_karaji"
    )

    return "\n".join(post)


# ==========================================
# دریافت آگهی‌های شهرها
# ==========================================

all_ads = []

for city in CITIES:

    print()
    print(
        f"در حال بررسی: {city}"
    )

    time.sleep(8)

    url = (
        f"{BASE_URL}/s/"
        f"{city}/jobs"
    )

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        if response.status_code == 429:

            print(
                "⏳ محدودیت دیوار..."
            )

            time.sleep(30)

            response = requests.get(
                url,
                headers=HEADERS,
                timeout=30
            )

        if response.status_code != 200:

            print(
                f"❌ خطا در {city}: "
                f"{response.status_code}"
            )

            continue

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        for a in soup.find_all(
            "a",
            href=True
        ):

            href = a["href"]

            if not href.startswith("/v/"):
                continue

            title = a.get_text(
                " ",
                strip=True
            )

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
                ad["id"] == ad_id
                for ad in all_ads
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

        print(
            f"❌ خطا در {city}: {e}"
        )


# ==========================================
# انتخاب 10 آگهی جدید
# ==========================================

new_ads = [
    ad
    for ad in all_ads
    if ad["id"] not in seen_ads
]

ads_to_send = new_ads[:10]


print()
print("=" * 60)
print(
    f"کل آگهی‌ها: {len(all_ads)}"
)
print(
    f"آگهی‌های جدید: {len(new_ads)}"
)
print(
    f"انتخاب شده: {len(ads_to_send)}"
)
print("=" * 60)


# ==========================================
# ارسال تلگرام
# ==========================================

def send_telegram(message):

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

    data = {
        "chat_id": CHAT_ID,
        "text": message,
        "disable_web_page_preview": True
    }

    try:

        response = requests.post(
            url,
            data=data,
            timeout=30
        )

        print(
            "Telegram:",
            response.status_code
        )

        if response.status_code != 200:
            print(response.text)

        return (
            response.status_code == 200
        )

    except Exception as e:

        print(
            f"❌ خطای تلگرام: {e}"
        )

        return False


# ==========================================
# پردازش آگهی‌ها
# ==========================================

for index, ad in enumerate(
    ads_to_send,
    1
):

    print()
    print(
        f"📝 آگهی "
        f"{index}/{len(ads_to_send)}"
    )

    print(
        f"عنوان: {ad['title']}"
    )

    # دریافت اطلاعات واقعی Divar
    details = get_ad_details(
        ad["link"],
        ad["title"]
    )

    ad["fields"] = details[
        "fields"
    ]

    ad["description"] = details[
        "description"
    ]

    # ساخت متن نهایی
    channel_post = (
        build_channel_post(ad)
    )

    print()
    print("----- متن آماده -----")
    print(channel_post)
    print("---------------------")

    # ارسال
    if send_telegram(
        channel_post
    ):

        print(
            f"✅ ارسال شد: "
            f"{ad['id']}"
        )

        if ad["id"] not in seen_ads:

            seen_ads.append(
                ad["id"]
            )

    else:

        print(
            f"❌ ارسال نشد: "
            f"{ad['id']}"
        )


# ==========================================
# ذخیره آگهی‌های ارسال شده
# ==========================================

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
print(
    f"💾 تعداد ذخیره‌شده: "
    f"{len(seen_ads)}"
)
