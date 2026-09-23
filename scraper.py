import os
import json
import re
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


# =========================
# تنظیمات
# =========================

JOB_URL = "https://divar.ir/s/alborz-province/jobs"

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = "8531717188"

SEEN_FILE = "seen_ads.json"

CHANNEL_ID = "@karyabi_alborzi"
REGISTER_ID = "@Karyabi_karaji"


# =========================
# ابزارها
# =========================

def clean_text(text):
    if not text:
        return ""

    text = text.replace("\u200c", " ")
    text = text.replace("\u200f", "")
    text = text.replace("\u200e", "")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_digits(text):
    if not text:
        return text

    table = str.maketrans(
        "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
        "01234567890123456789"
    )

    return text.translate(table)


def load_seen():
    if not os.path.exists(SEEN_FILE):
        return []

    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            return data

    except Exception:
        pass

    return []


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)


# =========================
# دریافت لینک آگهی‌ها
# =========================

def get_listing_urls():

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
        )
    }

    response = requests.get(
        JOB_URL,
        headers=headers,
        timeout=30
    )

    print(f"🌐 Jobs page: HTTP {response.status_code}")

    if response.status_code != 200:
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    urls = []
    ids = set()

    for a in soup.find_all("a", href=True):

        href = a.get("href", "").strip()

        if not href.startswith("/v/"):
            continue

        full_url = "https://divar.ir" + href

        match = re.search(r"/([a-zA-Z0-9_-]+)$", href)

        if not match:
            continue

        ad_id = match.group(1)

        if ad_id in ids:
            continue

        ids.add(ad_id)
        urls.append((ad_id, full_url))

    print(f"📋 تعداد آگهی‌های صفحه: {len(urls)}")

    return urls


# =========================
# استخراج فیلدهای واقعی دیوار
# =========================

def extract_structured_fields(page):

    fields = {}

    rows = page.locator(
        'div[data-testid="unexpandable-info-row"]'
    )

    count = rows.count()

    for i in range(count):

        try:
            row = rows.nth(i)

            title = clean_text(
                row.locator(
                    ".kt-unexpandable-row__title"
                ).inner_text()
            )

            value = clean_text(
                row.locator(
                    ".kt-unexpandable-row__value"
                ).inner_text()
            )

            if title and value:
                fields[title] = value

        except Exception:
            continue

    return fields


# =========================
# استخراج متن اصلی آگهی
# =========================

def get_clean_body_lines(page):

    try:
        body = page.locator("body").inner_text()

    except Exception:
        return []

    lines = []

    for raw in body.splitlines():

        line = clean_text(raw)

        if not line:
            continue

        lines.append(line)

    return lines


# =========================
# حذف بخش‌های اضافی دیوار
# =========================

def clean_description_lines(lines):

    result = []

    ignored_exact = {
        "گزارش آگهی",
        "دربارهٔ دیوار",
        "درباره دیوار",
        "دریافت برنامه",
        "اتاق خبر",
        "دیواری شو",
        "یادداشت تنها برای شما قابل دیدن است و پس از حذف آگهی، پاک خواهد شد.",
        "تصویر",
    }

    ignored_contains = [
        "تصویر ",
        "از ",
        "یادداشت تنها برای شما قابل دیدن است",
        "گزارش آگهی",
        "دربارهٔ دیوار",
        "دریافت برنامه",
        "اتاق خبر",
        "دیواری شو",
    ]

    for line in lines:

        if line in ignored_exact:
            continue

        skip = False

        for word in ignored_contains:

            if word in line:
                skip = True
                break

        if skip:
            continue

        result.append(line)

    return result


# =========================
# تشخیص اطلاعات از متن
# =========================

def extract_from_lines(lines):

    data = {}

    normalized = [normalize_digits(x) for x in lines]

    # -------------------------
    # جنسیت
    # -------------------------

    for i, line in enumerate(normalized):

        if line in ["خانم", "آقا", "فرقی نمی‌کند", "فرقی ندارد"]:
            data["جنسیت"] = line
            break

        if line.lower() in ["خانم", "آقا"]:
            data["جنسیت"] = line
            break

    # -------------------------
    # سابقه کار
    # -------------------------

    experience_patterns = [
        r"بدون نیاز به سابقه",
        r"کم‌تر از \d+ سال",
        r"کمتر از \d+ سال",
        r"حداقل \d+ سال",
        r"حداکثر \d+ سال",
        r"\d+ سال سابقه",
    ]

    for line in normalized:

        for pattern in experience_patterns:

            if re.search(pattern, line):

                data["سابقه کار"] = line
                break

        if "سابقه کار" in data:
            break

    # -------------------------
    # نوع همکاری
    # -------------------------

    cooperation_values = [
        "تمام وقت",
        "پاره وقت",
        "دورکاری",
        "کارآموزی",
        "پروژه‌ای",
        "پروژه ای",
    ]

    for line in normalized:

        if line in cooperation_values:
            data["نوع همکاری"] = line
            break

    # -------------------------
    # پرداخت
    # -------------------------

    payment_values = [
        "ماهانه",
        "هفتگی",
        "روزانه",
        "ساعتی",
        "پورسانتی/درصدی",
        "توافقی",
    ]

    for line in normalized:

        if line in payment_values:
            data["پرداخت"] = line
            break

    # -------------------------
    # حقوق
    # -------------------------

    salary_patterns = [
        r"از .* تا .* میلیون تومان",
        r"حداقل .* میلیون تومان",
        r"حداکثر .* میلیون تومان",
        r"پایه وزارت کار",
        r"توافقی",
    ]

    for line in normalized:

        if "میلیون تومان" in line or "وزارت کار" in line:

            data["حقوق"] = line
            break

        for pattern in salary_patterns:

            if re.search(pattern, line):
                data["حقوق"] = line
                break

        if "حقوق" in data:
            break

    # -------------------------
    # ساعت کاری
    # -------------------------

    time_patterns = [
        r"از \d{1,2} تا \d{1,2}",
        r"از \d{1,2}:\d{2} تا \d{1,2}:\d{2}",
        r"\d{1,2} صبح تا \d{1,2} شب",
        r"\d{1,2} صبح تا \d{1,2} عصر",
    ]

    for line in normalized:

        for pattern in time_patterns:

            if re.search(pattern, line):

                data["ساعت کاری"] = line
                break

        if "ساعت کاری" in data:
            break

    # -------------------------
    # بیمه
    # -------------------------

    for line in normalized:

        if line in ["دارد", "ندارد"]:

            # فقط اگر نزدیک به کلمه بیمه باشد
            idx = normalized.index(line)

            nearby = normalized[max(0, idx - 2):idx + 1]

            if any("بیمه" in x for x in nearby):
                data["بیمه"] = line
                break

    # -------------------------
    # دورکاری
    # -------------------------

    for i, line in enumerate(normalized):

        if "امکان دورکاری" in line:

            if i + 1 < len(normalized):

                value = normalized[i + 1]

                if value in ["دارد", "ندارد"]:
                    data["دورکاری"] = value

            break

    return data


# =========================
# استخراج اطلاعات آگهی
# =========================

def get_ad_details(page, url):

    print(f"🔎 باز کردن آگهی: {url}")

    try:

        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=45000
        )

        page.wait_for_timeout(2500)

        structured = extract_structured_fields(page)

        lines = get_clean_body_lines(page)

        body_data = extract_from_lines(lines)

        # اطلاعات ساختاریافته همیشه اولویت دارد
        data = {}

        for key, value in body_data.items():
            data[key] = value

        for key, value in structured.items():

            if key == "شیوهٔ پرداخت":
                data["پرداخت"] = value

            elif key == "عنوان شغلی":
                data["عنوان شغلی"] = value

            elif key == "دستمزد":
                data["حقوق"] = value

            elif key == "جنسیت":
                data["جنسیت"] = value

            elif key == "ساعت کاری":
                data["ساعت کاری"] = value

            elif key == "بیمه":
                data["بیمه"] = value

            elif key == "سابقه کار":
                data["سابقه کار"] = value

            elif key == "نوع همکاری":
                data["نوع همکاری"] = value

        # عنوان واقعی آگهی
        title = ""

        try:
            title = clean_text(
                page.locator("h1").first.inner_text()
            )
        except Exception:
            pass

        if not title:

            for line in lines:

                if len(line) > 2:
                    title = line
                    break

        data["عنوان"] = title

        print(f"📊 تعداد فیلدهای ساختاریافته: {len(structured)}")
        print(f"📌 عنوان: {title}")
        print(f"📋 فیلدهای ساختاریافته: {structured}")

        return {
            "title": title,
            "data": data,
            "lines": lines
        }

    except Exception as e:

        print(f"❌ خطا در باز کردن آگهی: {e}")

        return None


# =========================
# ساخت توضیحات تمیز
# =========================

def build_description(details):

    lines = details.get("lines", [])

    lines = clean_description_lines(lines)

    description = []

    # مواردی که قبلاً به عنوان اطلاعات استخراج شده‌اند
    extracted_values = set()

    for value in details["data"].values():

        if value:
            extracted_values.add(
                clean_text(value)
            )

    # مواردی که صرفاً اطلاعات رابط کاربری هستند
    ui_lines = {
        "عنوان شغلی",
        "شیوهٔ پرداخت",
        "دستمزد",
        "جنسیت",
        "بیمه",
        "ساعت کاری",
        "سابقه",
        "وضعیت سربازی",
        "عنوان شغلی",
        "نوع همکاری",
        "پرداخت",
        "توضیحات",
    }

    for line in lines:

        if line in ui_lines:
            continue

        if line in extracted_values:
            continue

        # مقادیر خیلی کوتاه و بی‌ارزش
        if line in ["۱", "۲", "۳", "۴", "۵"]:
            continue

        if re.fullmatch(r"\d+", normalize_digits(line)):
            continue

        # زمان/محل ابتدایی دیوار
        if "در کرج،" in line or "در هشتگرد،" in line:
            continue

        # متن‌های واضحاً مربوط به UI
        if "هفته پیش در" in line:
            continue

        if "پریروز در" in line:
            continue

        if "دیروز در" in line:
            continue

        if "امروز در" in line:
            continue

        # اگر متن واقعی آگهی باشد
        if len(line) >= 8:
            description.append(line)

    # حذف موارد تکراری
    final = []

    for line in description:

        if line not in final:
            final.append(line)

    # حداکثر 10 خط توضیح
    return final[:10]


# =========================
# ساخت پست تلگرام
# =========================

def make_post(details):

    title = details["title"]
    data = details["data"]

    salary = data.get("حقوق", "")

    # عنوان
    heading = title

    if salary:
        heading += f" | حقوق {salary}"

    post = []

    post.append(f"# 🟢 {heading}")
    post.append("")

    # -------------------------
    # فیلدهای اصلی
    # -------------------------

    field_order = [
        ("عنوان شغلی", "عنوان شغلی"),
        ("جنسیت", "جنسیت"),
        ("سابقه کار", "سابقه کار"),
        ("نوع همکاری", "نوع همکاری"),
        ("ساعت کاری", "ساعت کاری"),
        ("حقوق", "حقوق"),
        ("پرداخت", "پرداخت"),
        ("بیمه", "بیمه"),
        ("دورکاری", "امکان دورکاری"),
    ]

    for key, label in field_order:

        value = data.get(key)

        if not value:
            continue

        # حقوق فقط یک بار نمایش داده شود
        post.append(f"🟢 {label}: {value}")

    # -------------------------
    # توضیحات واقعی
    # -------------------------

    description = build_description(details)

    if description:

        post.append("")
        post.append("### 🟢 توضیحات")
        post.append("")

        for line in description:

            # اگر خود متن با ایموجی شروع نشده
            if line.startswith("🟢"):
                post.append(line)
            else:
                post.append(f"🟢 {line}")

    # -------------------------
    # آیدی‌های ثابت
    # -------------------------

    post.append("")
    post.append("کانال تلگرام")
    post.append(CHANNEL_ID)
    post.append("")
    post.append("جهت ثبت آگهی")
    post.append(REGISTER_ID)

    return "\n".join(post)


# =========================
# ارسال به تلگرام
# =========================

def send_telegram(text):

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": text
    }

    try:

        response = requests.post(
            url,
            json=payload,
            timeout=30
        )

        if response.status_code == 200:

            result = response.json()

            if result.get("ok"):
                print("📨 پیام با موفقیت به تلگرام ارسال شد.")
                return True

        print(
            f"❌ خطای تلگرام: "
            f"{response.status_code} - {response.text}"
        )

    except Exception as e:

        print(f"❌ خطا در ارسال تلگرام: {e}")

    return False


# =========================
# اجرای اصلی
# =========================

def main():

    print("🚀 شروع ربات\n")

    if not BOT_TOKEN:

        print("❌ BOT_TOKEN پیدا نشد.")
        return

    seen = load_seen()

    print(f"📦 تعداد آگهی‌های قبلی: {len(seen)}")

    listings = get_listing_urls()

    if not listings:

        print("❌ هیچ آگهی‌ای پیدا نشد.")
        return

    new_listings = []

    for ad_id, url in listings:

        if ad_id not in seen:

            new_listings.append(
                (ad_id, url)
            )

        if len(new_listings) >= 10:
            break

    print(
        f"🆕 آگهی جدید پیدا شده: "
        f"{len(new_listings)}"
    )

    if not new_listings:

        print("ℹ️ آگهی جدیدی برای ارسال وجود ندارد.")
        return

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page(
            viewport={
                "width": 1280,
                "height": 900
            },
            locale="fa-IR"
        )

        for ad_id, url in new_listings:

            details = get_ad_details(
                page,
                url
            )

            if not details:
                continue

            post = make_post(details)

            print("\n")
            print("=" * 50)
            print(post)
            print("=" * 50)
            print("\n")

            success = send_telegram(post)

            if success:

                if ad_id not in seen:
                    seen.append(ad_id)

                save_seen(seen)

                print(
                    f"✅ ارسال شد: "
                    f"{details['title']}"
                )

            else:

                print(
                    f"⚠️ ارسال نشد و در seen ثبت نشد: "
                    f"{details['title']}"
                )

        browser.close()

    print("\n🏁 پایان اجرای ربات")


if __name__ == "__main__":
    main()
