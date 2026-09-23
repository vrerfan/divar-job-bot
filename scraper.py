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
# تمیز کردن متن
# ==========================================

def clean_text(text):

    lines = []

    for line in text.splitlines():

        line = line.strip()

        if not line:
            continue

        # حذف خطوط تکراری
        if line in lines:
            continue

        # موارد اضافی رابط کاربری دیوار
        ignored_exact = [
            "دیوار",
            "سایت دیوار",
            "صفحه اصلی",
            "ورود",
            "ثبت نام",
            "ثبت آگهی",
            "گزارش آگهی",
            "آگهی‌های مشابه",
            "مشاهده آگهی‌های مشابه",
            "خانه",
            "دسته‌بندی‌ها",
        ]

        if line in ignored_exact:
            continue

        lines.append(line)

    return lines


# ==========================================
# دریافت جزئیات آگهی
# ==========================================

def get_ad_details(link):

    try:

        response = requests.get(
            link,
            headers=HEADERS,
            timeout=30
        )

        print(
            f"جزئیات آگهی: {response.status_code}"
        )

        if response.status_code != 200:
            return ""

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        # حذف تگ‌های غیرضروری
        for tag in soup([
            "script",
            "style",
            "noscript",
            "svg"
        ]):
            tag.decompose()

        # تلاش برای پیدا کردن محتوای اصلی آگهی
        candidates = []

        # متا description
        meta = soup.find(
            "meta",
            attrs={"name": "description"}
        )

        if meta and meta.get("content"):
            candidates.append(
                meta.get("content")
            )

        # تمام پاراگراف‌ها
        for tag in soup.find_all(
            ["p", "div"]
        ):

            text = tag.get_text(
                " ",
                strip=True
            )

            if not text:
                continue

            if len(text) < 10:
                continue

            if len(text) > 5000:
                continue

            candidates.append(text)

        # متن کلی صفحه
        page_text = soup.get_text(
            "\n",
            strip=True
        )

        lines = clean_text(page_text)

        # پیدا کردن بخش‌هایی که احتمالاً متن آگهی هستند
        useful_lines = []

        for line in lines:

            # موارد واضح رابط کاربری
            if line in [
                "دیوار",
                "سایت دیوار",
                "ثبت آگهی",
                "گزارش آگهی",
                "آگهی‌های مشابه",
                "ورود",
                "ثبت نام",
            ]:
                continue

            # متن‌های خیلی کوتاه معمولاً UI هستند
            if len(line) <= 2:
                continue

            useful_lines.append(line)

        # حذف خطوط ابتدایی تکراری
        final_lines = []

        for line in useful_lines:

            if line in final_lines:
                continue

            final_lines.append(line)

        return "\n".join(final_lines)

    except Exception as e:

        print(
            f"⚠️ خطا در دریافت جزئیات: {e}"
        )

        return ""


# ==========================================
# پیدا کردن مقدار فیلد
# ==========================================

def find_value(text, patterns):

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:

            value = match.group(1).strip()

            if value:
                return value

    return None


# ==========================================
# استخراج اطلاعات شغلی
# ==========================================

def extract_job_info(title, description):

    full_text = (
        f"{title}\n{description}"
    )

    info = {}

    info["gender"] = find_value(
        full_text,
        [
            r"جنسیت\s*[:：]?\s*(خانم|آقا|مرد|زن|آقا و خانم)",
            r"(خانم|آقا|مرد|زن)\s*(?:مورد نیاز|نیازمند)"
        ]
    )

    info["age"] = find_value(
        full_text,
        [
            r"(?:محدوده سنی|سن)\s*[:：]?\s*([^\n]+)"
        ]
    )

    info["experience"] = find_value(
        full_text,
        [
            r"(?:سابقه کار|سابقه)\s*[:：]?\s*([^\n]+)"
        ]
    )

    info["cooperation"] = find_value(
        full_text,
        [
            r"(?:نوع همکاری)\s*[:：]?\s*([^\n]+)",
            r"(تمام[‌ ]?وقت|پاره[‌ ]?وقت|دورکاری)"
        ]
    )

    info["hours"] = find_value(
        full_text,
        [
            r"(?:ساعت کاری|ساعات کاری)\s*[:：]?\s*([^\n]+)"
        ]
    )

    info["salary"] = find_value(
        full_text,
        [
            r"(?:حقوق|دستمزد|درآمد)\s*[:：]?\s*([^\n]+)",
            r"((?:حداقل|حداکثر)?\s*\d+(?:\s*تا\s*\d+)?\s*میلیون\s*تومان)"
        ]
    )

    info["payment"] = find_value(
        full_text,
        [
            r"(?:پرداخت|نحوه پرداخت)\s*[:：]?\s*([^\n]+)",
            r"(ماهانه|هفتگی|روزانه)"
        ]
    )

    info["employment"] = find_value(
        full_text,
        [
            r"(?:نوع استخدام)\s*[:：]?\s*([^\n]+)",
            r"(رسمی|قراردادی|آزمایشی)"
        ]
    )

    return info


# ==========================================
# استخراج متن مفید آگهی
# ==========================================

def extract_description(title, raw_text):

    if not raw_text:
        return ""

    lines = clean_text(raw_text)

    result = []

    for line in lines:

        # عنوان را دوباره داخل توضیحات نیاور
        if line == title:
            continue

        # موارد UI
        if line in [
            "دیوار",
            "سایت دیوار",
            "ثبت آگهی",
            "گزارش آگهی",
            "آگهی‌های مشابه",
            "مشاهده آگهی‌های مشابه",
            "صفحه اصلی",
            "ورود",
            "ثبت نام",
        ]:
            continue

        # لینک‌ها
        if line.startswith("http://"):
            continue

        if line.startswith("https://"):
            continue

        # اگر خط شامل لینک دیوار بود حذف شود
        if "divar.ir" in line.lower():
            continue

        if line not in result:
            result.append(line)

    return "\n".join(result)


# ==========================================
# ساخت پست کانال
# ==========================================

def build_channel_post(ad):

    title = ad["title"]
    description = ad.get(
        "description",
        ""
    )

    info = extract_job_info(
        title,
        description
    )

    post = []

    # عنوان
    post.append(
        f"# 🟢 {title}"
    )

    post.append("")

    # عنوان شغلی
    post.append(
        f"🟢 عنوان شغلی: {title}"
    )

    # اطلاعات فقط در صورت وجود واقعی
    if info["gender"]:
        post.append(
            f"🟢 جنسیت: {info['gender']}"
        )

    if info["age"]:
        post.append(
            f"🟢 محدوده سنی: {info['age']}"
        )

    if info["experience"]:
        post.append(
            f"🟢 سابقه کار: {info['experience']}"
        )

    if info["cooperation"]:
        post.append(
            f"🟢 نوع همکاری: {info['cooperation']}"
        )

    if info["hours"]:
        post.append(
            f"🟢 ساعت کاری: {info['hours']}"
        )

    if info["salary"]:
        post.append(
            f"🟢 حقوق: {info['salary']}"
        )

    if info["payment"]:
        post.append(
            f"🟢 پرداخت: {info['payment']}"
        )

    if info["employment"]:
        post.append(
            f"🟢 نوع استخدام: {info['employment']}"
        )

    # توضیحات
    if description:

        post.append("")
        post.append(
            "### 🟢 توضیحات"
        )

        description_lines = (
            description.splitlines()
        )

        # حداکثر 25 خط مفید
        count = 0

        for line in description_lines:

            line = line.strip()

            if not line:
                continue

            if line == title:
                continue

            if "divar.ir" in line.lower():
                continue

            if line in [
                "دیوار",
                "سایت دیوار",
                "ثبت آگهی",
                "گزارش آگهی",
                "آگهی‌های مشابه",
                "صفحه اصلی",
                "ورود",
                "ثبت نام",
            ]:
                continue

            post.append(
                f"🟢 {line}"
            )

            count += 1

            if count >= 25:
                break

    # پایان ثابت
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
# دریافت آگهی‌ها
# ==========================================

all_ads = []

for city in CITIES:

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
                "⏳ محدودیت دیوار - "
                "30 ثانیه صبر..."
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
        f"📝 آماده‌سازی "
        f"{index}/{len(ads_to_send)}"
    )

    print(
        f"عنوان: {ad['title']}"
    )

    # دریافت متن آگهی
    raw_description = (
        get_ad_details(
            ad["link"]
        )
    )

    ad["description"] = (
        extract_description(
            ad["title"],
            raw_description
        )
    )

    # ساخت پست
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
# ذخیره
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
    f"💾 تعداد آگهی‌های ذخیره‌شده: "
    f"{len(seen_ads)}"
)
