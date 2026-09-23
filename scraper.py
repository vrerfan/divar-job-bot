import os
import json
import re
import requests
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright


# =========================
# تنظیمات
# =========================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = "8531717188"

JOB_URL = "https://divar.ir/s/alborz-province/jobs"
SEEN_FILE = "seen_ads.json"

MAX_ADS = 10


# =========================
# ابزارهای کمکی
# =========================

def clean_text(text):
    if not text:
        return ""

    text = text.replace("\u200c", " ")
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n+", "\n", text)

    return text.strip()


def normalize_digits(text):
    if not text:
        return ""

    trans = str.maketrans(
        "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
        "01234567890123456789"
    )

    return text.translate(trans)


def is_valid_ad_url(url):
    try:
        path = urlparse(url).path.rstrip("/")
        parts = path.split("/")

        return (
            len(parts) >= 3
            and parts[-2] == "v"
            and len(parts[-1]) >= 5
        )
    except Exception:
        return False


def get_ad_id(url):
    path = urlparse(url).path.rstrip("/")
    return path.split("/")[-1]


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
# استخراج آگهی‌های صفحه اصلی
# =========================

def get_listing_urls(page):

    print("🌐 باز کردن صفحه استخدام...")

    page.goto(
        JOB_URL,
        wait_until="domcontentloaded",
        timeout=60000
    )

    page.wait_for_timeout(5000)

    links = page.locator('a[href*="/v/"]').all()

    urls = []

    for link in links:
        try:
            href = link.get_attribute("href")

            if not href:
                continue

            if href.startswith("/"):
                href = "https://divar.ir" + href

            href = href.split("?")[0].split("#")[0]

            if not is_valid_ad_url(href):
                continue

            if href not in urls:
                urls.append(href)

        except Exception:
            continue

    print(f"📋 تعداد آگهی‌های صفحه: {len(urls)}")

    return urls


# =========================
# فیلدهای ساختاریافته
# =========================

def extract_structured_fields(page):

    data = {}

    rows = page.locator(
        'div[data-testid="unexpandable-info-row"]'
    ).all()

    for row in rows:

        try:
            title = row.locator(
                ".kt-unexpandable-row__title"
            ).inner_text()

            value = row.locator(
                ".kt-unexpandable-row__value"
            ).inner_text()

            title = clean_text(title)
            value = clean_text(value)

            if not title or not value:
                continue

            data[title] = value

        except Exception:
            continue

    return data


# =========================
# تشخیص اطلاعات از متن
# =========================

def extract_value(lines, patterns):

    for line in lines:

        line = clean_text(line)

        for pattern in patterns:

            match = re.search(pattern, line, re.I)

            if match:
                value = match.group(1).strip()

                if value:
                    return value

    return None


def extract_fallback_fields(lines):

    data = {}

    # -------------------------
    # نوع همکاری
    # -------------------------

    cooperation_values = [
        "تمام وقت",
        "پاره وقت",
        "دورکاری",
        "کارآموزی",
        "پروژه‌ای",
        "پروژه ای"
    ]

    for line in lines:

        clean = clean_text(line)

        if clean in cooperation_values:
            data["نوع همکاری"] = clean
            break

    # -------------------------
    # سابقه کار
    # -------------------------

    experience_patterns = [
        r"بدون نیاز به سابقه",
        r"کمتر از ۱ سال",
        r"کم‌تر از ۱ سال",
        r"کمتر از 1 سال",
        r"کم‌تر از 1 سال",
        r"حداقل ۱ سال",
        r"حداقل 1 سال",
        r"حداقل ۲ سال",
        r"حداقل 2 سال",
        r"حداقل ۳ سال",
        r"حداقل 3 سال",
        r"حداقل ۴ سال",
        r"حداقل 4 سال",
        r"حداقل ۵ سال",
        r"حداقل 5 سال"
    ]

    for line in lines:

        clean = clean_text(line)

        for pattern in experience_patterns:

            if re.fullmatch(pattern, clean, re.I):
                data["سابقه کار"] = clean
                break

        if "سابقه کار" in data:
            break

    # -------------------------
    # جنسیت
    # -------------------------

    gender_values = [
        "آقا",
        "خانم",
        "فرقی ندارد",
        "فرقی نمی‌کند",
        "فرقی نمی کند"
    ]

    for line in lines:

        clean = clean_text(line)

        if clean in gender_values:
            data["جنسیت"] = clean
            break

    # -------------------------
    # پرداخت
    # -------------------------

    payment_values = [
        "ماهانه",
        "روزانه",
        "هفتگی",
        "ساعتی",
        "پورسانتی/درصدی",
        "پورسانتی",
        "توافقی"
    ]

    for line in lines:

        clean = clean_text(line)

        if clean in payment_values:
            data["شیوهٔ پرداخت"] = clean
            break

    # -------------------------
    # حقوق
    # -------------------------

    salary_patterns = [
        r"(از\s*[\d۰-۹]+(?:[.,]\d+)?\s*(?:تا|-)\s*[\d۰-۹]+(?:[.,]\d+)?\s*(?:میلیون|میلیارد)\s*تومان)",
        r"(حداقل\s*[\d۰-۹]+(?:[.,]\d+)?\s*(?:میلیون|میلیارد)\s*تومان)",
        r"(حداکثر\s*[\d۰-۹]+(?:[.,]\d+)?\s*(?:میلیون|میلیارد)\s*تومان)",
        r"(تا\s*[\d۰-۹]+(?:[.,]\d+)?\s*(?:میلیون|میلیارد)\s*تومان)",
        r"(توافقی)"
    ]

    salary = extract_value(lines, salary_patterns)

    if salary:
        data["حقوق"] = salary

    # -------------------------
    # ساعت کاری
    # فقط الگوی واقعی ساعت
    # -------------------------

    time_patterns = [
        r"(?:از\s*)?([0-2]?\d\s*تا\s*[0-2]?\d)(?=\s*(?:$|[^۰-۹0-9]))",
        r"(از\s*[۰-۹0-9]{1,2}\s*تا\s*[۰-۹0-9]{1,2}(?:\s*[^،]*)?)"
    ]

    for line in lines:

        clean = clean_text(line)

        # اگر حقوق است، به هیچ وجه ساعت کاری نیست
        if "تومان" in clean or "میلیون" in clean or "میلیارد" in clean:
            continue

        # اگر سن است، ساعت کاری نیست
        if "سن" in clean or "سال" in clean:
            continue

        if re.search(
            r"از\s*[۰-۹0-9]{1,2}\s*تا\s*[۰-۹0-9]{1,2}",
            clean
        ):
            data["ساعت کاری"] = clean
            break

    # -------------------------
    # بیمه
    # -------------------------

    for line in lines:

        clean = clean_text(line)

        if clean in ["دارد", "ندارد"]:
            # فقط وقتی نزدیک به عبارت بیمه باشد
            data.setdefault("_possible_values", []).append(clean)

    return data


# =========================
# استخراج توضیحات واقعی
# =========================

def extract_description(page):

    selectors = [
        '[data-testid="description"]',
        '.kt-description-row__text',
        'div.kt-description-row',
        'div[class*="description-row"]',
        'div[class*="description"]'
    ]

    for selector in selectors:

        try:

            elements = page.locator(selector).all()

            for element in elements:

                try:
                    text = element.inner_text()
                    text = clean_text(text)

                    if not text:
                        continue

                    # حذف مواردی که واضحاً UI هستند
                    bad = [
                        "گزارش آگهی",
                        "یادداشت تنها برای شما",
                        "دربارهٔ دیوار",
                        "درباره دیوار",
                        "اطلاعات تماس",
                        "برو به اطلاعات تماس",
                        "دیوار من",
                        "پشتیبانی",
                        "ثبت آگهی",
                        "چت و تماس",
                        "انتخاب شهر",
                        "تصویر 1 از",
                        "تصویر 2 از",
                        "تصویر 3 از",
                        "تصویر 4 از",
                        "تصویر 5 از"
                    ]

                    if any(x in text for x in bad):
                        continue

                    # توضیحات واقعی معمولاً طول مناسبی دارند
                    if len(text) >= 15:
                        return text

                except Exception:
                    continue

        except Exception:
            continue

    return ""


# =========================
# استخراج اطلاعات کامل آگهی
# =========================

def get_ad_details(page, url):

    print(f"🔎 باز کردن آگهی: {url}")

    page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=60000
    )

    page.wait_for_timeout(2500)

    # عنوان
    title = ""

    title_selectors = [
        "h1",
        '[data-testid="title"]'
    ]

    for selector in title_selectors:

        try:
            value = page.locator(selector).first.inner_text()

            if value:
                title = clean_text(value)
                break

        except Exception:
            pass

    if not title:
        title = "آگهی استخدام"

    # فیلدهای ساختاریافته
    structured = extract_structured_fields(page)

    print(f"📊 تعداد فیلدهای ساختاریافته: {len(structured)}")
    print(f"📌 عنوان: {title}")
    print(f"📋 فیلدهای ساختاریافته: {structured}")

    # متن صفحه برای fallback
    try:
        body_text = page.locator("body").inner_text()
    except Exception:
        body_text = ""

    lines = [
        clean_text(x)
        for x in body_text.splitlines()
        if clean_text(x)
    ]

    fallback = extract_fallback_fields(lines)

    # -------------------------
    # ترکیب فیلدها
    # -------------------------

    data = {}

    # عنوان شغلی
    if structured.get("عنوان شغلی"):
        data["عنوان شغلی"] = structured["عنوان شغلی"]

    # جنسیت
    gender = structured.get("جنسیت")

    if gender:
        data["جنسیت"] = gender
    elif fallback.get("جنسیت"):
        data["جنسیت"] = fallback["جنسیت"]

    # سابقه
    experience = structured.get("سابقه کار")

    if experience in [
        "بدون نیاز به سابقه",
        "کمتر از ۱ سال",
        "کم‌تر از ۱ سال",
        "کمتر از 1 سال",
        "کم‌تر از 1 سال",
        "حداقل ۱ سال",
        "حداقل 1 سال",
        "حداقل ۲ سال",
        "حداقل 2 سال",
        "حداقل ۳ سال",
        "حداقل 3 سال",
        "حداقل ۴ سال",
        "حداقل 4 سال",
        "حداقل ۵ سال",
        "حداقل 5 سال"
    ]:
        data["سابقه کار"] = experience

    elif fallback.get("سابقه کار"):
        data["سابقه کار"] = fallback["سابقه کار"]

    # نوع همکاری
    cooperation = structured.get("نوع همکاری")

    if cooperation in [
        "تمام وقت",
        "پاره وقت",
        "دورکاری",
        "کارآموزی",
        "پروژه‌ای",
        "پروژه ای"
    ]:
        data["نوع همکاری"] = cooperation

    elif fallback.get("نوع همکاری"):
        data["نوع همکاری"] = fallback["نوع همکاری"]

    # ساعت کاری
    structured_time = structured.get("ساعت کاری")

    if structured_time:

        # فقط اگر واقعاً ساعت باشد
        if re.search(
            r"\d+\s*تا\s*\d+|[۰-۹]+\s*تا\s*[۰-۹]+",
            structured_time
        ):
            data["ساعت کاری"] = structured_time

    elif fallback.get("ساعت کاری"):
        data["ساعت کاری"] = fallback["ساعت کاری"]

    # حقوق
    salary = structured.get("دستمزد")

    if salary:
        data["حقوق"] = salary

    elif fallback.get("حقوق"):
        data["حقوق"] = fallback["حقوق"]

    # پرداخت
    payment = structured.get("شیوهٔ پرداخت")

    if payment:
        data["پرداخت"] = payment

    elif fallback.get("شیوهٔ پرداخت"):
        data["پرداخت"] = fallback["شیوهٔ پرداخت"]

    # بیمه
    insurance = structured.get("بیمه")

    if insurance:
        data["بیمه"] = insurance

    # دورکاری
    remote = structured.get("امکان دورکاری")

    if remote:
        data["امکان دورکاری"] = remote

    # توضیحات واقعی
    description = extract_description(page)

    return {
        "title": title,
        "fields": data,
        "description": description
    }


# =========================
# ساخت متن آگهی
# =========================

def make_post(ad):

    title = ad["title"]
    data = ad["fields"]
    description = ad["description"]

    # -------------------------
    # عنوان
    # -------------------------

    heading = title

    if data.get("حقوق"):
        heading += f" | حقوق {data['حقوق']}"

    lines = [
        f"# 🟢 {heading}",
        ""
    ]

    # -------------------------
    # اطلاعات
    # -------------------------

    ordered_fields = [
        ("عنوان شغلی", "عنوان شغلی"),
        ("جنسیت", "جنسیت"),
        ("سابقه کار", "سابقه کار"),
        ("نوع همکاری", "نوع همکاری"),
        ("ساعت کاری", "ساعت کاری"),
        ("حقوق", "حقوق"),
        ("پرداخت", "پرداخت"),
        ("بیمه", "بیمه"),
        ("امکان دورکاری", "امکان دورکاری")
    ]

    for key, label in ordered_fields:

        value = data.get(key)

        if not value:
            continue

        lines.append(f"🟢 {label}: {value}")

    # -------------------------
    # توضیحات
    # -------------------------

    if description:

        lines.append("")
        lines.append("### 🟢 توضیحات")

        # خطوط توضیحات را تمیز می‌کنیم
        description_lines = [
            clean_text(x)
            for x in description.splitlines()
            if clean_text(x)
        ]

        for line in description_lines:

            # جلوگیری از ورود UI
            if any(
                bad in line
                for bad in [
                    "برو به اطلاعات تماس",
                    "انتخاب شهر",
                    "دیوار من",
                    "چت و تماس",
                    "پشتیبانی",
                    "ثبت آگهی",
                    "گزارش آگهی",
                    "دربارهٔ دیوار",
                    "درباره دیوار",
                    "تصویر "
                ]
            ):
                continue

            lines.append(f"🟢 {line}")

    # -------------------------
    # آیدی‌های ثابت
    # -------------------------

    lines.extend([
        "",
        "کانال تلگرام",
        "@karyabi_alborzi",
        "",
        "جهت ثبت آگهی",
        "@Karyabi_karaji"
    ])

    return "\n".join(lines)


# =========================
# ارسال به تلگرام
# =========================

def send_telegram(message):

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "disable_web_page_preview": True
    }

    response = requests.post(
        url,
        json=payload,
        timeout=30
    )

    if response.status_code != 200:

        print("❌ خطا در ارسال تلگرام:")
        print(response.text)

        return False

    print("📨 پیام با موفقیت به تلگرام ارسال شد.")

    return True


# =========================
# اجرای اصلی
# =========================

def main():

    print("\n🚀 شروع ربات\n")

    if not BOT_TOKEN:
        print("❌ BOT_TOKEN پیدا نشد.")
        return

    seen = load_seen()

    print(f"📦 تعداد آگهی‌های قبلی: {len(seen)}\n")

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

        # -------------------------
        # گرفتن لینک آگهی‌ها
        # -------------------------

        urls = get_listing_urls(page)

        new_ads = []

        for url in urls:

            ad_id = get_ad_id(url)

            if ad_id in seen:
                continue

            new_ads.append((ad_id, url))

            if len(new_ads) >= MAX_ADS:
                break

        print(f"🆕 آگهی جدید پیدا شده: {len(new_ads)}\n")

        # -------------------------
        # پردازش ۱۰ آگهی
        # -------------------------

        for ad_id, url in new_ads:

            try:

                ad = get_ad_details(page, url)

                post = make_post(ad)

                print("\n" + "=" * 50)
                print(post)
                print("=" * 50 + "\n")

                # فقط بعد از ارسال موفق، seen شود
                sent = send_telegram(post)

                if sent:

                    if ad_id not in seen:
                        seen.append(ad_id)

                    save_seen(seen)

                    print(f"✅ ارسال شد: {ad['title']}\n")

                else:

                    print(
                        f"⚠️ ارسال ناموفق بود و آگهی ذخیره نشد: "
                        f"{ad['title']}\n"
                    )

            except Exception as e:

                print(f"❌ خطا در پردازش آگهی: {e}")

        browser.close()

    print("🏁 پایان اجرای ربات")


if __name__ == "__main__":
    main()
