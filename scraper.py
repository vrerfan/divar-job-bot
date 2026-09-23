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


def get_ad_id(url):
    try:
        path = urlparse(url).path.rstrip("/")
        parts = path.split("/")

        if len(parts) >= 3 and parts[-2] == "v":
            return parts[-1]

    except Exception:
        pass

    return None


# =========================
# پیدا کردن لینک آگهی‌ها
# =========================

def get_listing_urls(page):

    print("🌐 باز کردن صفحه استخدام...")

    page.goto(
        JOB_URL,
        wait_until="domcontentloaded",
        timeout=60000
    )

    # صبر برای لود کامل محتوای داینامیک دیوار
    page.wait_for_timeout(8000)

    urls = []

    # ---------------------------------
    # روش اول: لینک‌های واقعی DOM
    # ---------------------------------

    try:
        hrefs = page.locator("a").evaluate_all(
            """
            elements => elements
                .map(e => e.href)
                .filter(Boolean)
            """
        )

        for href in hrefs:

            href = href.split("?")[0].split("#")[0]

            match = re.search(
                r"https?://(?:www\.)?divar\.ir/v/[^/]+/([A-Za-z0-9_-]+)$",
                href
            )

            if match:
                if href not in urls:
                    urls.append(href)

    except Exception as e:
        print(f"⚠️ روش اول خطا داد: {e}")

    # ---------------------------------
    # روش دوم: گرفتن HTML صفحه
    # ---------------------------------

    if len(urls) == 0:

        print("🔄 روش دوم برای پیدا کردن آگهی‌ها...")

        try:

            html = page.content()

            matches = re.findall(
                r'(?:https://divar\.ir)?/v/[^"\'>\s]+',
                html
            )

            for href in matches:

                if href.startswith("/"):
                    href = "https://divar.ir" + href

                href = href.split("?")[0].split("#")[0]

                match = re.search(
                    r"https?://(?:www\.)?divar\.ir/v/[^/]+/([A-Za-z0-9_-]+)$",
                    href
                )

                if match and href not in urls:
                    urls.append(href)

        except Exception as e:
            print(f"⚠️ روش دوم خطا داد: {e}")

    # ---------------------------------
    # حذف موارد خراب
    # ---------------------------------

    final_urls = []

    for url in urls:

        ad_id = get_ad_id(url)

        if not ad_id:
            continue

        if ad_id not in [
            get_ad_id(x) for x in final_urls
        ]:
            final_urls.append(url)

    print(f"📋 تعداد آگهی‌های صفحه: {len(final_urls)}")

    return final_urls


# =========================
# فیلدهای ساختاریافته
# =========================

def extract_structured_fields(page):

    data = {}

    try:

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

                if title and value:
                    data[title] = value

            except Exception:
                continue

    except Exception:
        pass

    return data


# =========================
# استخراج اطلاعات از متن
# =========================

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

        line = clean_text(line)

        if line in cooperation_values:
            data["نوع همکاری"] = line
            break

    # -------------------------
    # سابقه
    # -------------------------

    experience_values = [
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
    ]

    for line in lines:

        line = clean_text(line)

        if line in experience_values:
            data["سابقه کار"] = line
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

        line = clean_text(line)

        if line in gender_values:
            data["جنسیت"] = line
            break

    # -------------------------
    # پرداخت
    # -------------------------

    payment_values = [
        "ماهانه",
        "روزانه",
        "هفتگی",
        "ساعتی",
        "پورسانتی",
        "پورسانتی/درصدی",
        "توافقی"
    ]

    for line in lines:

        line = clean_text(line)

        if line in payment_values:
            data["پرداخت"] = line
            break

    # -------------------------
    # حقوق
    # -------------------------

    for line in lines:

        line = clean_text(line)

        if "تومان" not in line:
            continue

        if (
            "میلیون" in line
            or "میلیارد" in line
            or "توافقی" in line
        ):
            data["حقوق"] = line
            break

    # -------------------------
    # ساعت کاری
    # -------------------------

    for line in lines:

        line = clean_text(line)

        # حقوق و سن را ساعت کاری حساب نکن
        if "تومان" in line:
            continue

        if "سال" in line:
            continue

        if "سن" in line:
            continue

        if re.search(
            r"از\s*[۰-۹0-9]{1,2}\s*تا\s*[۰-۹0-9]{1,2}",
            line
        ):
            data["ساعت کاری"] = line
            break

    # -------------------------
    # بیمه
    # -------------------------

    for i, line in enumerate(lines):

        line = clean_text(line)

        if line == "بیمه":

            if i + 1 < len(lines):

                value = clean_text(lines[i + 1])

                if value in ["دارد", "ندارد"]:
                    data["بیمه"] = value

    return data


# =========================
# توضیحات واقعی
# =========================

def extract_description(page):

    bad_words = [
        "برو به اطلاعات تماس",
        "انتخاب شهر",
        "دیوار من",
        "چت و تماس",
        "پشتیبانی",
        "ثبت آگهی",
        "گزارش آگهی",
        "دربارهٔ دیوار",
        "درباره دیوار",
        "تصویر 1 از",
        "تصویر 2 از",
        "تصویر 3 از",
        "تصویر 4 از",
        "تصویر 5 از",
        "اطلاعات تماس",
        "سایر ویژگی ها و امکانات",
        "سایر ویژگی‌ها و امکانات"
    ]

    selectors = [
        '[data-testid="description"]',
        '[data-testid*="description"]',
        '[class*="description"]'
    ]

    for selector in selectors:

        try:

            elements = page.locator(selector).all()

            for element in elements:

                try:

                    text = element.inner_text()
                    text = clean_text(text)

                    if len(text) < 15:
                        continue

                    if any(
                        bad.lower() in text.lower()
                        for bad in bad_words
                    ):
                        continue

                    return text

                except Exception:
                    continue

        except Exception:
            continue

    return ""


# =========================
# دریافت اطلاعات آگهی
# =========================

def get_ad_details(page, url):

    print(f"🔎 باز کردن آگهی: {url}")

    page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=60000
    )

    page.wait_for_timeout(3000)

    # -------------------------
    # عنوان
    # -------------------------

    title = ""

    for selector in [
        "h1",
        '[data-testid="title"]'
    ]:

        try:

            value = page.locator(selector).first.inner_text()

            if value:
                title = clean_text(value)
                break

        except Exception:
            continue

    if not title:
        title = "آگهی استخدام"

    # -------------------------
    # فیلدهای ساختاریافته
    # -------------------------

    structured = extract_structured_fields(page)

    print(f"📊 تعداد فیلدهای ساختاریافته: {len(structured)}")
    print(f"📌 عنوان: {title}")
    print(f"📋 فیلدهای ساختاریافته: {structured}")

    # -------------------------
    # متن صفحه
    # -------------------------

    try:
        body = page.locator("body").inner_text()
    except Exception:
        body = ""

    lines = [
        clean_text(x)
        for x in body.splitlines()
        if clean_text(x)
    ]

    fallback = extract_fallback_fields(lines)

    data = {}

    # -------------------------
    # عنوان شغلی
    # -------------------------

    if structured.get("عنوان شغلی"):
        data["عنوان شغلی"] = structured["عنوان شغلی"]

    # -------------------------
    # جنسیت
    # -------------------------

    if structured.get("جنسیت"):
        data["جنسیت"] = structured["جنسیت"]

    elif fallback.get("جنسیت"):
        data["جنسیت"] = fallback["جنسیت"]

    # -------------------------
    # سابقه
    # -------------------------

    valid_experience = [
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
    ]

    structured_experience = structured.get("سابقه کار")

    if structured_experience in valid_experience:
        data["سابقه کار"] = structured_experience

    elif fallback.get("سابقه کار"):
        data["سابقه کار"] = fallback["سابقه کار"]

    # -------------------------
    # نوع همکاری
    # -------------------------

    valid_cooperation = [
        "تمام وقت",
        "پاره وقت",
        "دورکاری",
        "کارآموزی",
        "پروژه‌ای",
        "پروژه ای"
    ]

    structured_cooperation = structured.get("نوع همکاری")

    if structured_cooperation in valid_cooperation:
        data["نوع همکاری"] = structured_cooperation

    elif fallback.get("نوع همکاری"):
        data["نوع همکاری"] = fallback["نوع همکاری"]

    # -------------------------
    # ساعت کاری
    # -------------------------

    structured_time = structured.get("ساعت کاری")

    if structured_time and re.search(
        r"\d+\s*تا\s*\d+|[۰-۹]+\s*تا\s*[۰-۹]+",
        structured_time
    ):

        if "تومان" not in structured_time:
            data["ساعت کاری"] = structured_time

    elif fallback.get("ساعت کاری"):

        data["ساعت کاری"] = fallback["ساعت کاری"]

    # -------------------------
    # حقوق
    # -------------------------

    if structured.get("دستمزد"):
        data["حقوق"] = structured["دستمزد"]

    elif fallback.get("حقوق"):
        data["حقوق"] = fallback["حقوق"]

    # -------------------------
    # پرداخت
    # -------------------------

    if structured.get("شیوهٔ پرداخت"):
        data["پرداخت"] = structured["شیوهٔ پرداخت"]

    elif fallback.get("پرداخت"):
        data["پرداخت"] = fallback["پرداخت"]

    # -------------------------
    # بیمه
    # -------------------------

    if structured.get("بیمه"):
        data["بیمه"] = structured["بیمه"]

    elif fallback.get("بیمه"):
        data["بیمه"] = fallback["بیمه"]

    # -------------------------
    # دورکاری
    # -------------------------

    if structured.get("امکان دورکاری"):
        data["امکان دورکاری"] = structured["امکان دورکاری"]

    # -------------------------
    # توضیحات
    # -------------------------

    description = extract_description(page)

    return {
        "title": title,
        "fields": data,
        "description": description
    }


# =========================
# ساخت پست
# =========================

def make_post(ad):

    title = ad["title"]
    data = ad["fields"]
    description = ad["description"]

    # عنوان
    heading = title

    if data.get("حقوق"):
        heading += f" | حقوق {data['حقوق']}"

    lines = [
        f"# 🟢 {heading}",
        ""
    ]

    # ترتیب نمایش
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

        lines.append(
            f"🟢 {label}: {value}"
        )

    # توضیحات
    if description:

        lines.append("")
        lines.append("### 🟢 توضیحات")

        description_lines = [
            clean_text(x)
            for x in description.splitlines()
            if clean_text(x)
        ]

        for line in description_lines:

            if any(
                bad.lower() in line.lower()
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

            lines.append(
                f"🟢 {line}"
            )

    # آیدی‌های ثابت
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
# ارسال تلگرام
# =========================

def send_telegram(message):

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "disable_web_page_preview": True
    }

    try:

        response = requests.post(
            url,
            json=payload,
            timeout=30
        )

        if response.status_code == 200:
            print("📨 پیام با موفقیت به تلگرام ارسال شد.")
            return True

        print("❌ خطا در ارسال تلگرام:")
        print(response.text)

        return False

    except Exception as e:

        print(f"❌ خطای ارتباط با تلگرام: {e}")

        return False


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

        # گرفتن آگهی‌ها
        urls = get_listing_urls(page)

        new_ads = []

        for url in urls:

            ad_id = get_ad_id(url)

            if not ad_id:
                continue

            if ad_id in seen:
                continue

            new_ads.append(
                (ad_id, url)
            )

            if len(new_ads) >= MAX_ADS:
                break

        print(
            f"🆕 آگهی جدید پیدا شده: "
            f"{len(new_ads)}\n"
        )

        # پردازش
        for ad_id, url in new_ads:

            try:

                ad = get_ad_details(
                    page,
                    url
                )

                post = make_post(ad)

                print("\n" + "=" * 50)
                print(post)
                print("=" * 50 + "\n")

                sent = send_telegram(post)

                if sent:

                    if ad_id not in seen:
                        seen.append(ad_id)

                    save_seen(seen)

                    print(
                        f"✅ ارسال شد: "
                        f"{ad['title']}\n"
                    )

                else:

                    print(
                        f"⚠️ ارسال نشد و ذخیره نشد: "
                        f"{ad['title']}\n"
                    )

            except Exception as e:

                print(
                    f"❌ خطا در پردازش آگهی: {e}"
                )

        browser.close()

    print("🏁 پایان اجرای ربات")


if __name__ == "__main__":
    main()
