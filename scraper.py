import os
import re
import json
import time
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


# =========================
# تنظیمات
# =========================

BOT_TOKEN = os.environ.get("BOT_TOKEN")

CHAT_ID = "8531717188"

JOB_URL = "https://divar.ir/s/alborz-province/jobs"

SEEN_FILE = "seen_ads.json"

DIVAR_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://divar.ir/",
}


# =========================
# خواندن آگهی‌های دیده شده
# =========================

def load_seen():

    if not os.path.exists(SEEN_FILE):
        return set()

    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            return set(data)

    except Exception as e:
        print(f"⚠️ خطا در خواندن seen_ads.json: {e}")

    return set()


# =========================
# ذخیره آگهی‌های دیده شده
# =========================

def save_seen(seen):

    try:
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(
                sorted(list(seen)),
                f,
                ensure_ascii=False,
                indent=2
            )

        print(f"💾 {len(seen)} آگهی ذخیره شد.")

    except Exception as e:
        print(f"❌ خطا در ذخیره seen_ads.json: {e}")


# =========================
# استخراج ID آگهی
# =========================

def get_ad_id(url):

    if not url:
        return None

    match = re.search(
        r"/v/[^/]+/([A-Za-z0-9_-]+)",
        url
    )

    if match:
        return match.group(1)

    return None


# =========================
# دریافت لیست آگهی‌ها
# =========================

def get_listing_urls():

    print("🌐 دریافت لیست آگهی‌ها...")

    try:

        response = requests.get(
            JOB_URL,
            headers=DIVAR_HEADERS,
            timeout=30
        )

        print(f"🌐 Jobs page: HTTP {response.status_code}")

        if response.status_code != 200:
            print("❌ دریافت صفحه استخدام ناموفق بود.")
            return []

        html = response.text

    except Exception as e:

        print(f"❌ خطا در دریافت صفحه استخدام: {e}")

        return []

    urls = []
    ids = set()

    # -------------------------
    # روش اول: BeautifulSoup
    # -------------------------

    try:

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        for a in soup.find_all("a", href=True):

            href = a.get("href")

            if not href:
                continue

            if "/v/" not in href:
                continue

            if href.startswith("/"):
                href = "https://divar.ir" + href

            elif href.startswith("//"):
                href = "https:" + href

            href = href.split("?")[0]
            href = href.split("#")[0]

            ad_id = get_ad_id(href)

            if not ad_id:
                continue

            if len(ad_id) < 5:
                continue

            if ad_id not in ids:

                ids.add(ad_id)
                urls.append(href)

    except Exception as e:

        print(f"⚠️ خطا در استخراج لینک‌ها با BeautifulSoup: {e}")

    # -------------------------
    # روش دوم: Regex
    # -------------------------

    if len(urls) == 0:

        print("🔄 تلاش با Regex...")

        patterns = [

            r'https://divar\.ir/v/[^"\'<>\s]+',

            r'/v/[^"\'<>\s]+',

            r'https:\\/\\/divar\.ir\\/v\\/[^"\'<>\s]+',

            r'\\/v\\/[^"\'<>\s]+',

        ]

        for pattern in patterns:

            try:

                matches = re.findall(
                    pattern,
                    html
                )

                for href in matches:

                    href = href.replace(
                        "\\/",
                        "/"
                    )

                    if href.startswith("/"):
                        href = "https://divar.ir" + href

                    href = href.split("?")[0]
                    href = href.split("#")[0]

                    ad_id = get_ad_id(href)

                    if not ad_id:
                        continue

                    if len(ad_id) < 5:
                        continue

                    if ad_id not in ids:

                        ids.add(ad_id)
                        urls.append(href)

            except Exception:
                pass

    print(f"📋 تعداد آگهی‌های صفحه: {len(urls)}")

    return urls


# =========================
# تمیز کردن متن
# =========================

def clean_text(text):

    if not text:
        return ""

    text = text.replace("\u200c", " ")
    text = text.replace("\xa0", " ")

    text = re.sub(
        r"[ \t]+",
        " ",
        text
    )

    text = re.sub(
        r"\n+",
        "\n",
        text
    )

    return text.strip()


# =========================
# استخراج اطلاعات ساختاریافته
# =========================

def get_structured_info(page):

    info = {}

    try:

        rows = page.locator(
            'div[data-testid="unexpandable-info-row"]'
        )

        count = rows.count()

        for i in range(count):

            try:

                row = rows.nth(i)

                title = row.locator(
                    ".kt-unexpandable-row__title"
                ).inner_text()

                value = row.locator(
                    ".kt-unexpandable-row__value"
                ).inner_text()

                title = clean_text(title)
                value = clean_text(value)

                if title and value:

                    info[title] = value

            except Exception:
                continue

    except Exception as e:

        print(
            f"⚠️ خطا در اطلاعات ساختاریافته: {e}"
        )

    return info


# =========================
# اعتبارسنجی نوع همکاری
# =========================

def valid_cooperation(value):

    if not value:
        return False

    value = value.strip()

    valid = [

        "تمام وقت",
        "تمام‌وقت",

        "پاره وقت",
        "پاره‌وقت",

        "کارآموزی",

        "پروژه‌ای",
        "پروژه ای",

        "دورکاری",

        "ساعتی",

        "نیمه وقت",
        "نیمه‌وقت",

    ]

    return any(
        x in value
        for x in valid
    )


# =========================
# اعتبارسنجی سابقه کار
# =========================

def valid_experience(value):

    if not value:
        return False

    value = value.strip()

    keywords = [

        "بدون نیاز",
        "بدون سابقه",
        "کمتر از",
        "حداقل",
        "بیش از",
        "سال سابقه",
        "ماه سابقه",

    ]

    return any(
        x in value
        for x in keywords
    )


# =========================
# اعتبارسنجی ساعت کاری
# =========================

def valid_work_hours(value):

    if not value:
        return False

    value = value.strip()

    # باید چیزی شبیه ساعت باشد
    patterns = [

        r"\b\d{1,2}\s*(?:تا|-)\s*\d{1,2}\b",

        r"\b\d{1,2}:\d{2}\s*(?:تا|-)\s*\d{1,2}:\d{2}\b",

        r"\bاز\s+\d{1,2}",

        r"\bساعت\s+\d{1,2}",

    ]

    return any(
        re.search(
            pattern,
            value
        )
        for pattern in patterns
    )


# =========================
# استخراج سن
# =========================

def extract_age(text):

    if not text:
        return None

    patterns = [

        r"(?:سن|سنین)\s*(?:از)?\s*(\d{1,2})\s*(?:تا|-)\s*(\d{1,2})\s*سال",

        r"(\d{1,2})\s*(?:تا|-)\s*(\d{1,2})\s*سال",

    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text
        )

        if match:

            return (
                f"{match.group(1)} تا "
                f"{match.group(2)} سال"
            )

    return None


# =========================
# استخراج حقوق
# =========================

def extract_salary(text):

    if not text:
        return None

    text = clean_text(text)

    patterns = [

        r"از\s+[\d۰-۹,.]+\s+تا\s+[\d۰-۹,.]+\s+میلیون\s+تومان",

        r"[\d۰-۹,.]+\s+تا\s+[\d۰-۹,.]+\s+میلیون\s+تومان",

        r"حداقل\s+[\d۰-۹,.]+\s+میلیون\s+تومان",

        r"حداکثر\s+[\d۰-۹,.]+\s+میلیون\s+تومان",

        r"تا\s+[\d۰-۹,.]+\s+میلیون\s+تومان",

        r"از\s+[\d۰-۹,.]+\s+میلیون\s+تومان",

        r"[\d۰-۹,.]+\s+میلیون\s+تومان",

        r"توافقی",

    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text
        )

        if match:

            result = match.group(0)

            # اگر متن بعد از حقوق دارد،
            # فقط خود بخش حقوق را برگردان
            result = result.strip()

            return result

    return None


# =========================
# استخراج اطلاعات آگهی
# =========================

def extract_ad(page, url):

    ad_id = get_ad_id(url)

    print(f"\n🔎 بررسی آگهی: {ad_id}")

    try:

        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=30000
        )

        page.wait_for_timeout(2500)

    except Exception as e:

        print(
            f"❌ خطا در باز کردن آگهی: {e}"
        )

        return None

    # -------------------------
    # عنوان
    # -------------------------

    title = ""

    selectors = [

        "h1",

        '[data-testid="ad-title"]',

        '[data-testid="title"]',

    ]

    for selector in selectors:

        try:

            loc = page.locator(selector)

            if loc.count() > 0:

                value = clean_text(
                    loc.first.inner_text()
                )

                if value:

                    title = value
                    break

        except Exception:
            pass

    # -------------------------
    # اطلاعات ساختاریافته
    # -------------------------

    info = get_structured_info(page)

    print("📊 اطلاعات ساختاریافته:")

    print(info)

    # -------------------------
    # متن صفحه
    # -------------------------

    body_text = ""

    try:

        article = page.locator("article")

        if article.count() > 0:

            body_text = article.first.inner_text()

        else:

            body_text = page.locator(
                "body"
            ).inner_text()

    except Exception:

        try:

            body_text = page.locator(
                "body"
            ).inner_text()

        except Exception:

            body_text = ""

    body_text = clean_text(body_text)

    # -------------------------
    # اگر عنوان پیدا نشد
    # -------------------------

    if not title:

        lines = [
            clean_text(x)
            for x in body_text.split("\n")
            if clean_text(x)
        ]

        for line in lines:

            if len(line) >= 4:

                if line not in [
                    "استخدام و کاریابی",
                    "استخدام",
                    "کاریابی",
                ]:

                    title = line
                    break

    # -------------------------
    # جنسیت
    # -------------------------

    gender = info.get("جنسیت")

    if gender:

        gender = gender.strip()

    # -------------------------
    # سابقه کار
    # -------------------------

    experience = None

    for key, value in info.items():

        if "سابقه" in key:

            if valid_experience(value):

                experience = value

            break

    # -------------------------
    # نوع همکاری
    # -------------------------

    cooperation = None

    for key, value in info.items():

        if "نوع همکاری" in key:

            if valid_cooperation(value):

                cooperation = value

            break

    # -------------------------
    # ساعت کاری
    # -------------------------

    work_hours = None

    for key, value in info.items():

        if "ساعت کاری" in key:

            if valid_work_hours(value):

                work_hours = value

            break

    # -------------------------
    # حقوق
    # -------------------------

    salary = None

    for key, value in info.items():

        if "دستمزد" in key or "حقوق" in key:

            salary = extract_salary(value)

            if salary:
                break

    # اگر از اطلاعات ساختاریافته پیدا نشد
    if not salary:

        salary = extract_salary(
            body_text
        )

    # -------------------------
    # پرداخت
    # -------------------------

    payment = None

    for key, value in info.items():

        if "پرداخت" in key:

            payment = value.strip()

            break

    # -------------------------
    # بیمه
    # -------------------------

    insurance = None

    for key, value in info.items():

        if "بیمه" in key:

            insurance = value.strip()

            break

    # -------------------------
    # سن
    # -------------------------

    age = extract_age(
        body_text
    )

    # -------------------------
    # دورکاری
    # -------------------------

    remote = None

    remote_keywords = [
        "دورکاری",
        "امکان دورکاری",
        "کار در منزل",
        "کاردرمنزل",
    ]

    for keyword in remote_keywords:

        if keyword in body_text:

            remote = "دارد"
            break

    # -------------------------
    # ساخت دیکشنری
    # -------------------------

    ad = {

        "id": ad_id,

        "url": url,

        "title": title,

        "gender": gender,

        "age": age,

        "experience": experience,

        "cooperation": cooperation,

        "work_hours": work_hours,

        "salary": salary,

        "payment": payment,

        "insurance": insurance,

        "remote": remote,

        "description": body_text,

    }

    return ad


# =========================
# حذف خطوط مزاحم از توضیحات
# =========================

def clean_description(text, title):

    if not text:
        return ""

    lines = [
        clean_text(x)
        for x in text.split("\n")
        if clean_text(x)
    ]

    blacklist = [

        "دیوار",
        "ورود",
        "ثبت آگهی",
        "دسته‌بندی",
        "استخدام و کاریابی",
        "مشاهده همه",
        "اشتراک‌گذاری",
        "ذخیره",
        "گزارش",
        "ارتباط با آگهی‌دهنده",
        "تماس",
        "چت",
        "آگهی‌های مشابه",
        "آگهی‌های مرتبط",
        "خانه",
        "استان البرز",
        "کرج",

    ]

    result = []

    for line in lines:

        if line == title:
            continue

        if len(line) < 2:
            continue

        # حذف خطوط رابط کاربری
        if any(
            item == line
            for item in blacklist
        ):
            continue

        result.append(line)

    return "\n".join(result)


# =========================
# ساخت پست تلگرام
# =========================

def make_post(ad):

    title = ad.get("title") or "استخدام نیرو"

    # -------------------------
    # تیتر
    # -------------------------

    post = []

    post.append(
        f"# 🟢 {title}"
    )

    post.append("")

    # -------------------------
    # اطلاعات
    # -------------------------

    if ad.get("title"):

        post.append(
            f"🟢 عنوان شغلی: {ad['title']}"
        )

    if ad.get("gender"):

        post.append(
            f"🟢 جنسیت: {ad['gender']}"
        )

    if ad.get("age"):

        post.append(
            f"🟢 محدوده سنی: {ad['age']}"
        )

    if ad.get("experience"):

        post.append(
            f"🟢 سابقه کار: {ad['experience']}"
        )

    if ad.get("cooperation"):

        post.append(
            f"🟢 نوع همکاری: {ad['cooperation']}"
        )

    if ad.get("work_hours"):

        post.append(
            f"🟢 ساعت کاری: {ad['work_hours']}"
        )

    if ad.get("salary"):

        post.append(
            f"🟢 حقوق: {ad['salary']}"
        )

    if ad.get("payment"):

        post.append(
            f"🟢 پرداخت: {ad['payment']}"
        )

    if ad.get("insurance"):

        post.append(
            f"🟢 بیمه: {ad['insurance']}"
        )

    if ad.get("remote"):

        post.append(
            f"🟢 امکان دورکاری: {ad['remote']}"
        )

    # -------------------------
    # توضیحات
    # -------------------------

    description = clean_description(
        ad.get("description", ""),
        title
    )

    if description:

        # حذف خطوطی که قبلاً
        # به صورت فیلد استفاده شده‌اند

        used_values = set()

        for value in [
            ad.get("gender"),
            ad.get("age"),
            ad.get("experience"),
            ad.get("cooperation"),
            ad.get("work_hours"),
            ad.get("salary"),
            ad.get("payment"),
            ad.get("insurance"),
        ]:

            if value:
                used_values.add(
                    clean_text(value)
                )

        description_lines = []

        for line in description.split("\n"):

            line = clean_text(line)

            if not line:
                continue

            if line in used_values:
                continue

            # حذف بعضی متن‌های تکراری UI
            if line.startswith("دقایقی پیش"):
                continue

            if line.startswith("ساعتی پیش"):
                continue

            if line.startswith("امروز"):
                continue

            description_lines.append(line)

        if description_lines:

            post.append("")

            post.append(
                "### 🟢 توضیحات"
            )

            post.append("")

            for line in description_lines:

                post.append(
                    f"🟢 {line}"
                )

    # -------------------------
    # آیدی‌های ثابت
    # -------------------------

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


# =========================
# ارسال به تلگرام
# =========================

def send_telegram(text):

    if not BOT_TOKEN:

        print(
            "❌ BOT_TOKEN پیدا نشد."
        )

        return False

    url = (
        f"https://api.telegram.org/bot"
        f"{BOT_TOKEN}/sendMessage"
    )

    data = {

        "chat_id": CHAT_ID,

        "text": text,

        "disable_web_page_preview": True,

    }

    try:

        response = requests.post(
            url,
            data=data,
            timeout=30
        )

        if response.status_code == 200:

            result = response.json()

            if result.get("ok"):

                print(
                    "✅ پیام با موفقیت ارسال شد."
                )

                return True

        print(
            "❌ خطا در ارسال تلگرام:",
            response.text
        )

    except Exception as e:

        print(
            f"❌ خطای Telegram API: {e}"
        )

    return False


# =========================
# اجرای اصلی
# =========================

def main():

    print("🚀 شروع ربات")

    if not BOT_TOKEN:

        print(
            "❌ BOT_TOKEN تنظیم نشده!"
        )

        return

    seen = load_seen()

    print(
        f"📦 تعداد آگهی‌های قبلی: {len(seen)}"
    )

    # -------------------------
    # دریافت لیست
    # -------------------------

    urls = get_listing_urls()

    if not urls:

        print(
            "❌ هیچ آگهی‌ای پیدا نشد."
        )

        return

    # -------------------------
    # حذف آگهی‌های قبلی
    # -------------------------

    new_urls = []

    for url in urls:

        ad_id = get_ad_id(url)

        if not ad_id:
            continue

        if ad_id in seen:
            continue

        new_urls.append(url)

    print(
        f"🆕 آگهی جدید پیدا شده: "
        f"{len(new_urls)}"
    )

    # فقط ۱۰ آگهی
    new_urls = new_urls[:10]

    if not new_urls:

        print(
            "ℹ️ آگهی جدیدی برای ارسال وجود ندارد."
        )

        return

    # -------------------------
    # Playwright
    # -------------------------

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        context = browser.new_context(
            user_agent=DIVAR_HEADERS[
                "User-Agent"
            ],
            locale="fa-IR",
            viewport={
                "width": 1366,
                "height": 900
            }
        )

        page = context.new_page()

        # -------------------------
        # پردازش ۱۰ آگهی
        # -------------------------

        for index, url in enumerate(
            new_urls,
            start=1
        ):

            print(
                f"\n=============================="
            )

            print(
                f"📌 آگهی {index}/{len(new_urls)}"
            )

            print(url)

            try:

                ad = extract_ad(
                    page,
                    url
                )

                if not ad:

                    print(
                        "❌ استخراج آگهی ناموفق بود."
                    )

                    continue

                print(
                    f"📝 عنوان: {ad['title']}"
                )

                post = make_post(ad)

                print(
                    "\n----- متن نهایی -----\n"
                )

                print(post)

                print(
                    "\n---------------------\n"
                )

                # -------------------------
                # ارسال
                # -------------------------

                success = send_telegram(
                    post
                )

                if success:

                    ad_id = ad["id"]

                    if ad_id:

                        seen.add(ad_id)

                    # کمی فاصله بین ارسال‌ها
                    time.sleep(2)

                else:

                    print(
                        "⚠️ پیام ارسال نشد؛ "
                        "این آگهی seen نمی‌شود."
                    )

            except Exception as e:

                print(
                    f"❌ خطا در پردازش آگهی: {e}"
                )

        browser.close()

    # -------------------------
    # ذخیره
    # -------------------------

    save_seen(seen)

    print(
        "\n🏁 پایان اجرای ربات"
    )


# =========================
# Start
# =========================

if __name__ == "__main__":
    main()
