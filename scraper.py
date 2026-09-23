```python
import os
import re
import json
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

JOB_URL = "https://divar.ir/s/alborz-province/jobs"

SEEN_FILE = "seen_ads.json"

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = "8531717188"

MAX_ADS_PER_RUN = 10


# =========================================================
# ابزارهای کمکی
# =========================================================

def normalize_text(text):
    if not text:
        return ""

    text = text.replace("\u200c", " ")
    text = text.replace("\u200f", "")
    text = text.replace("\u200e", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def to_persian_digits(text):
    if not text:
        return text

    table = str.maketrans(
        "0123456789",
        "۰۱۲۳۴۵۶۷۸۹"
    )

    return text.translate(table)


def get_ad_id(url):
    if not url:
        return ""

    match = re.search(r"/v/[^/]+/([A-Za-z0-9_-]+)", url)

    if match:
        return match.group(1)

    return ""


def clean_value(value):
    if not value:
        return ""

    value = normalize_text(value)

    # حذف نقطه و فاصله‌های اضافی ابتدا و انتها
    value = value.strip(" -:؛،")

    return value


# =========================================================
# seen ads
# =========================================================

def load_seen_ads():

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


def save_seen_ads(seen):

    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(
            seen,
            f,
            ensure_ascii=False,
            indent=2
        )


# =========================================================
# دریافت لینک آگهی‌های صفحه استخدام
# =========================================================

def get_listing_urls(page):

    print("🌐 دریافت لیست آگهی‌ها...")

    try:

        response = requests.get(
            JOB_URL,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                "Accept": (
                    "text/html,application/xhtml+xml,"
                    "application/xml;q=0.9,*/*;q=0.8"
                ),
                "Accept-Language": (
                    "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7"
                ),
                "Referer": "https://divar.ir/"
            },
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

    # -----------------------------------------
    # روش اول: BeautifulSoup
    # -----------------------------------------

    try:

        soup = BeautifulSoup(html, "html.parser")

        for a in soup.find_all("a", href=True):

            href = a.get("href", "")

            if "/v/" not in href:
                continue

            if href.startswith("/"):
                href = "https://divar.ir" + href

            href = href.split("?")[0]
            href = href.split("#")[0]

            match = re.search(
                r"https://divar\.ir/v/[^/]+/([A-Za-z0-9_-]+)",
                href
            )

            if not match:
                continue

            ad_id = match.group(1)

            if len(ad_id) < 5:
                continue

            if not any(get_ad_id(x) == ad_id for x in urls):
                urls.append(href)

    except Exception as e:

        print(f"⚠️ خطا در استخراج لینک‌ها با BeautifulSoup: {e}")

    # -----------------------------------------
    # روش دوم: Regex برای لینک‌های معمولی
    # -----------------------------------------

    matches = re.findall(
        r'(?:https://divar\.ir)?/v/[^"\'<>\s]+',
        html
    )

    for href in matches:

        try:

            if href.startswith("/"):
                href = "https://divar.ir" + href

            href = href.split("?")[0]
            href = href.split("#")[0]

            match = re.search(
                r"https://divar\.ir/v/[^/]+/([A-Za-z0-9_-]+)$",
                href
            )

            if not match:
                continue

            ad_id = match.group(1)

            if len(ad_id) < 5:
                continue

            if not any(get_ad_id(x) == ad_id for x in urls):
                urls.append(href)

        except Exception:
            continue

    print(f"📋 تعداد آگهی‌های صفحه: {len(urls)}")

    return urls


# =========================================================
# استخراج اطلاعات ساختاریافته
# =========================================================

def extract_structured_data(page):

    data = {}

    try:

        rows = page.locator(
            'div[data-testid="unexpandable-info-row"]'
        )

        count = rows.count()

        for i in range(count):

            try:

                row = rows.nth(i)

                title = row.locator(
                    "div.kt-unexpandable-row__title-box p"
                ).inner_text()

                value = row.locator(
                    "div.kt-unexpandable-row__value-box p"
                ).inner_text()

                title = clean_value(title)
                value = clean_value(value)

                if title and value:
                    data[title] = value

            except Exception:
                continue

    except Exception:
        pass

    return data


# =========================================================
# تشخیص اطلاعات از متن توضیحات
# =========================================================

def find_gender(text):

    if not text:
        return ""

    patterns = [
        r"جنسیت\s*[:：]?\s*(خانم|زن)",
        r"فقط\s*(خانم|زن)",
        r"(خانم|زن)\s*مورد نیاز",
        r"(خانم|زن)\s*نیازمند",
        r"(خانم|زن)\s*استخدام",
    ]

    for pattern in patterns:

        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            return "خانم"

    patterns = [
        r"جنسیت\s*[:：]?\s*(آقا|مرد)",
        r"فقط\s*(آقا|مرد)",
        r"(آقا|مرد)\s*مورد نیاز",
        r"(آقا|مرد)\s*نیازمند",
        r"(آقا|مرد)\s*استخدام",
    ]

    for pattern in patterns:

        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            return "آقا"

    if re.search(
        r"آقا\s*(و|یا)\s*خانم|خانم\s*(و|یا)\s*آقا",
        text
    ):
        return "فرقی نمی کند"

    return ""


def find_age(text):

    if not text:
        return ""

    patterns = [

        r"سن\s*(\d{1,2})\s*(?:تا|-)\s*(\d{1,2})\s*سال",

        r"سنین\s*(\d{1,2})\s*(?:تا|-)\s*(\d{1,2})",

        r"(\d{1,2})\s*(?:تا|-)\s*(\d{1,2})\s*سال",

        r"حداقل سن\s*(\d{1,2})",

        r"حداکثر سن\s*(\d{1,2})",

    ]

    for pattern in patterns:

        match = re.search(pattern, text)

        if not match:
            continue

        if len(match.groups()) == 2:

            a = match.group(1)
            b = match.group(2)

            return f"{a} تا {b} سال"

        if "حداقل" in pattern:
            return f"حداقل {match.group(1)} سال"

        if "حداکثر" in pattern:
            return f"حداکثر {match.group(1)} سال"

    return ""


def find_hours(text):

    if not text:
        return ""

    patterns = [

        r"ساعت کاری\s*[:：]?\s*([^\n]+)",

        r"ساعت\s*(\d{1,2})\s*(?:تا|-)\s*(\d{1,2})",

        r"(\d{1,2})\s*الی\s*(\d{1,2})",

        r"از\s*(\d{1,2})\s*تا\s*(\d{1,2})",

    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if not match:
            continue

        value = match.group(0)

        # جلوگیری از اشتباه گرفتن سن و حقوق با ساعت
        if "سال" in value:
            continue

        if "میلیون" in value:
            continue

        if re.search(
            r"\d+\s*(?:تا|-|الی)\s*\d+\s*(?:سال|میلیون)",
            value
        ):
            continue

        if "ساعت کاری" in value:
            value = re.sub(
                r"^ساعت کاری\s*[:：]?\s*",
                "",
                value
            )

        return clean_value(value)

    return ""


def find_salary(text):

    if not text:
        return ""

    patterns = [

        r"از\s*[\d۰-۹]+\s*تا\s*[\d۰-۹]+\s*میلیون\s*تومان",

        r"[\d۰-۹]+\s*تا\s*[\d۰-۹]+\s*میلیون\s*تومان",

        r"حداقل\s*[\d۰-۹]+\s*میلیون\s*تومان",

        r"حداکثر\s*[\d۰-۹]+\s*میلیون\s*تومان",

        r"تا\s*[\d۰-۹]+\s*میلیون\s*تومان",

        r"[\d۰-۹]+\s*میلیون\s*تومان",

        r"حقوق\s*[:：]?\s*توافقی",

        r"حقوق\s*[:：]?\s*پایه\s*وزارت\s*کار",

    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:

            value = match.group(0)

            value = re.sub(
                r"^حقوق\s*[:：]?\s*",
                "",
                value
            )

            return clean_value(value)

    return ""


def find_payment(text):

    if not text:
        return ""

    patterns = [

        r"پرداخت\s*[:：]?\s*(ماهانه|هفتگی|روزانه|پورسانتی/درصدی|پورسانتی|توافقی)",

        r"شیوه.?ی پرداخت\s*[:：]?\s*([^\n]+)",

        r"حقوق\s*.*?(ماهانه|هفتگی|روزانه)",

    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:

            value = match.group(1)

            return clean_value(value)

    return ""


def find_experience(text):

    if not text:
        return ""

    patterns = [

        r"حداقل\s*(\d+)\s*سال\s*سابقه",

        r"سابقه\s*[:：]?\s*(حداقل\s*\d+\s*سال)",

        r"(\d+)\s*سال\s*سابقه",

        r"بدون نیاز به سابقه",

        r"نیاز به سابقه نیست",

        r"سابقه کار ندارد",

    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if not match:
            continue

        if "بدون" in match.group(0) or "نیاز به سابقه نیست" in match.group(0):
            return "بدون نیاز به سابقه"

        return clean_value(match.group(0))

    return ""


# =========================================================
# استخراج شماره تماس
# =========================================================

def extract_phone_numbers(text):

    if not text:
        return []

    # شماره‌های ایرانی با 09
    patterns = [

        r"(?<!\d)09\d{9}(?!\d)",

        r"(?<!\d)۰۹\d{9}(?!\d)",

        r"(?<!\d)09\d[\s\-]\d{3}[\s\-]\d{4}",

        r"(?<!\d)۰۹\d[\s\-]\d{3}[\s\-]\d{4}",

    ]

    found = []

    for pattern in patterns:

        matches = re.findall(
            pattern,
            text
        )

        for number in matches:

            number = number.replace(" ", "")
            number = number.replace("-", "")

            number = to_persian_digits(number)

            if number not in found:
                found.append(number)

    return found


def extract_phone_from_page(page, body_text):

    phones = []

    # -----------------------------------------
    # از متن صفحه
    # -----------------------------------------

    phones.extend(
        extract_phone_numbers(body_text)
    )

    # -----------------------------------------
    # از attribute های HTML
    # -----------------------------------------

    try:

        html = page.content()

        phones.extend(
            extract_phone_numbers(html)
        )

    except Exception:
        pass

    # حذف تکراری‌ها
    result = []

    for phone in phones:

        if phone not in result:
            result.append(phone)

    return result


# =========================================================
# استخراج توضیحات واقعی
# =========================================================

UI_NOISE = {
    "زنگ خطرهای قبل از همکاری",
    "اطلاعات تماس",
    "نوع همکاری",
    "سابقه",
    "شیوهٔ پرداخت",
    "شیوه پرداخت",
    "عنوان شغلی",
    "دستمزد",
    "بیمه",
    "جنسیت",
    "وضعیت سربازی",
    "سایر ویژگی ها و امکانات",
    "توضیحات",
    "یادداشت تنها برای شما قابل دیدن است و پس از حذف آگهی، پاک خواهد شد",
    "گزارش آگهی",
    "تصویر 1 از 1",
    "تصویر 1 از 2",
    "تصویر 2 از 2",
}


def is_noise_line(line):

    line = normalize_text(line)

    if not line:
        return True

    if line in UI_NOISE:
        return True

    # متن‌های مربوط به منو و رابط دیوار
    noise_patterns = [

        r"^استخدام .* در .*$",

        r"^استخدام بازاریابی و فروش$",

        r"^استخدام صنعتی، فنی، مهندسی$",

        r"^استخدام مالی، حسابداری، حقوقی$",

        r"^استخدام خدمات فروشگاه و رستوران$",

        r"^فروشنده$",

        r"^حسابدار$",

        r"^باریستا$",

        r"^یادداشت تنها برای شما",

        r"^گزارش آگهی",

        r"^تصویر \d+ از \d+$",

    ]

    for pattern in noise_patterns:

        if re.match(pattern, line):
            return True

    return False


def extract_description(page, title):

    try:

        # اول article را امتحان می‌کنیم
        article = page.locator("article")

        if article.count() > 0:

            text = article.first.inner_text()

        else:

            text = page.locator("body").inner_text()

    except Exception:

        try:
            text = page.locator("body").inner_text()
        except Exception:
            return ""

    text = normalize_text(text)

    lines = text.splitlines()

    cleaned = []

    started = False

    for line in lines:

        line = normalize_text(line)

        if not line:
            continue

        # از زمانی که عنوان آگهی را دیدیم
        if line == title:
            started = True
            continue

        if not started:
            continue

        # خطوط رابط کاربری را حذف کن
        if is_noise_line(line):
            continue

        # زمان و محل بالای آگهی
        if re.match(
            r"^(امروز|دقایقی پیش|لحظاتی پیش|پریروز|دیروز|\d+\s*(روز|هفته|ماه|سال)\s*پیش)",
            line
        ):
            continue

        # لینک‌های احتمالی
        if "divar.ir/v/" in line:
            continue

        # آیدی‌های سیستم
        if line.startswith("@"):
            continue

        # شماره تلفن را از توضیحات حذف می‌کنیم
        if extract_phone_numbers(line):
            continue

        cleaned.append(line)

    # حذف تکراری‌های پشت سر هم
    final_lines = []

    for line in cleaned:

        if final_lines and final_lines[-1] == line:
            continue

        final_lines.append(line)

    return "\n".join(final_lines).strip()


# =========================================================
# اطلاعات کامل آگهی
# =========================================================

def scrape_ad(page, url):

    ad_id = get_ad_id(url)

    print(f"🔎 بررسی آگهی: {ad_id}")

    try:

        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=60000
        )

        page.wait_for_timeout(2500)

    except Exception as e:

        print(f"❌ خطا در باز کردن آگهی: {e}")

        return None

    # -----------------------------------------
    # عنوان
    # -----------------------------------------

    title = ""

    try:

        title = page.locator(
            'h1'
        ).first.inner_text()

    except Exception:
        pass

    if not title:

        try:

            title = page.title()

            title = re.sub(
                r"\s*\|\s*دیوار.*$",
                "",
                title
            )

        except Exception:
            title = "آگهی استخدام"

    title = clean_value(title)

    # -----------------------------------------
    # اطلاعات ساختاریافته
    # -----------------------------------------

    structured = extract_structured_data(page)

    print("📊 اطلاعات ساختاریافته:")
    print(structured)

    # -----------------------------------------
    # متن صفحه
    # -----------------------------------------

    try:

        body_text = page.locator(
            "body"
        ).inner_text()

    except Exception:

        body_text = ""

    body_text = normalize_text(body_text)

    # -----------------------------------------
    # توضیحات
    # -----------------------------------------

    description = extract_description(
        page,
        title
    )

    # -----------------------------------------
    # فیلدها
    # -----------------------------------------

    gender = structured.get(
        "جنسیت",
        ""
    )

    if not gender:
        gender = find_gender(body_text)

    age = find_age(body_text)

    experience = ""

    # تجربه فقط از متن واقعی
    # اگر structured مقدار معتبر دارد استفاده می‌کنیم
    structured_experience = structured.get(
        "سابقه",
        ""
    )

    if structured_experience:

        valid_experience = [
            "بدون نیاز به سابقه",
            "کمتر از ۱ سال",
            "کم تر از ۱ سال",
            "۱ تا ۳ سال",
            "۳ تا ۶ سال",
            "بیشتر از ۶ سال",
        ]

        if any(
            x in structured_experience
            for x in valid_experience
        ):
            experience = structured_experience

    if not experience:
        experience = find_experience(body_text)

    cooperation = ""

    structured_cooperation = structured.get(
        "نوع همکاری",
        ""
    )

    if structured_cooperation:

        valid_cooperation = [
            "تمام وقت",
            "پاره وقت",
            "کارآموزی",
            "دورکاری",
            "پروژه‌ای",
            "فریلنسری",
        ]

        if any(
            x in structured_cooperation
            for x in valid_cooperation
        ):
            cooperation = structured_cooperation

    hours = structured.get(
        "ساعت کاری",
        ""
    )

    # اگر مقدار ساختاریافته ساعت کاری نبود،
    # از متن پیدا کن
    if not hours:
        hours = find_hours(body_text)

    # جلوگیری از خطاهایی مثل:
    # "پذیرش سنین از 16 تا 30 سال"
    if hours:

        if (
            "سال" in hours
            or "میلیون" in hours
            or "سن" in hours
        ):
            hours = find_hours(description)

    salary = structured.get(
        "دستمزد",
        ""
    )

    if not salary:
        salary = find_salary(description)

    if not salary:
        salary = find_salary(body_text)

    payment = structured.get(
        "شیوهٔ پرداخت",
        ""
    )

    if not payment:
        payment = structured.get(
            "شیوه پرداخت",
            ""
        )

    if not payment:
        payment = find_payment(body_text)

    insurance = structured.get(
        "بیمه",
        ""
    )

    if not insurance:

        if re.search(
            r"بیمه\s*(دارد|✔|✅)",
            body_text
        ):
            insurance = "دارد"

        elif re.search(
            r"بیمه\s*(ندارد|❌)",
            body_text
        ):
            insurance = "ندارد"

    # -----------------------------------------
    # شماره تماس
    # -----------------------------------------

    phones = extract_phone_from_page(
        page,
        body_text
    )

    # -----------------------------------------
    # نتیجه
    # -----------------------------------------

    return {
        "id": ad_id,
        "url": url,
        "title": title,
        "gender": clean_value(gender),
        "age": clean_value(age),
        "experience": clean_value(experience),
        "cooperation": clean_value(cooperation),
        "hours": clean_value(hours),
        "salary": clean_value(salary),
        "payment": clean_value(payment),
        "insurance": clean_value(insurance),
        "phones": phones,
        "description": description,
    }


# =========================================================
# ساخت پست تلگرام
# =========================================================

def build_telegram_post(ad):

    title = ad.get(
        "title",
        "آگهی استخدام"
    ).strip()

    lines = []

    # -----------------------------------------
    # عنوان
    # -----------------------------------------

    lines.append(
        f"# 🟢 {title}"
    )

    lines.append("")

    # -----------------------------------------
    # عنوان شغلی
    # -----------------------------------------
    # اگر عنوان شغلی دقیقاً همان عنوان آگهی باشد
    # دوباره نمایش داده نمی‌شود.

    job_title = ""

    # در حال حاضر عنوان ساختاریافته جداگانه
    # در خروجی scrape_ad ذخیره نشده.
    # بنابراین فقط وقتی عنوان شغلی مستقل داشته باشیم
    # باید نمایش داده شود.

    # عمداً اینجا عنوان آگهی را دوباره تکرار نمی‌کنیم.

    # -----------------------------------------
    # جنسیت
    # -----------------------------------------

    if ad.get("gender"):
        lines.append(
            f"🟢 جنسیت: {ad['gender']}"
        )

    # -----------------------------------------
    # سن
    # -----------------------------------------

    if ad.get("age"):
        lines.append(
            f"🟢 محدوده سنی: {to_persian_digits(ad['age'])}"
        )

    # -----------------------------------------
    # سابقه
    # -----------------------------------------

    if ad.get("experience"):
        lines.append(
            f"🟢 سابقه کار: {ad['experience']}"
        )

    # -----------------------------------------
    # نوع همکاری
    # -----------------------------------------

    if ad.get("cooperation"):
        lines.append(
            f"🟢 نوع همکاری: {ad['cooperation']}"
        )

    # -----------------------------------------
    # ساعت کاری
    # -----------------------------------------

    if ad.get("hours"):
        lines.append(
            f"🟢 ساعت کاری: {ad['hours']}"
        )

    # -----------------------------------------
    # حقوق
    # -----------------------------------------

    if ad.get("salary"):
        lines.append(
            f"🟢 حقوق: {ad['salary']}"
        )

    # -----------------------------------------
    # پرداخت
    # -----------------------------------------

    if ad.get("payment"):
        lines.append(
            f"🟢 پرداخت: {ad['payment']}"
        )

    # -----------------------------------------
    # بیمه
    # -----------------------------------------

    if ad.get("insurance"):
        lines.append(
            f"🟢 بیمه: {ad['insurance']}"
        )

    # -----------------------------------------
    # توضیحات
    # -----------------------------------------

    if ad.get("description"):

        lines.append("")

        lines.append(
            "### 🟢 توضیحات"
        )

        for item in ad["description"].splitlines():

            item = normalize_text(item)

            if not item:
                continue

            # دوباره شماره تلفن را داخل توضیحات نمی‌آوریم
            if extract_phone_numbers(item):
                continue

            lines.append(
                f"🟢 {item}"
            )

    # -----------------------------------------
    # شماره تماس
    # -----------------------------------------

    if ad.get("phones"):

        lines.append("")

        for phone in ad["phones"]:

            lines.append(
                f"📞 {phone}"
            )

    # -----------------------------------------
    # کانال‌ها
    # -----------------------------------------

    lines.append("")

    lines.append(
        "کانال تلگرام"
    )

    lines.append(
        "@karyabi_alborzi"
    )

    lines.append("")

    lines.append(
        "جهت ثبت آگهی"
    )

    lines.append(
        "@Karyabi_karaji"
    )

    return "\n".join(lines)


# =========================================================
# ارسال پیام به تلگرام
# =========================================================

def send_telegram_message(text):

    url = (
        f"https://api.telegram.org/bot"
        f"{BOT_TOKEN}/sendMessage"
    )

    try:

        response = requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": text,
            },
            timeout=30
        )

        if response.status_code == 200:

            print("✅ پیام با موفقیت ارسال شد.")

            return True

        print(
            "❌ خطای تلگرام:",
            response.text
        )

    except Exception as e:

        print(
            f"❌ خطا در ارسال تلگرام: {e}"
        )

    return False


# =========================================================
# اجرای اصلی
# =========================================================

def main():

    print("🚀 شروع ربات")

    if not BOT_TOKEN:

        print(
            "❌ BOT_TOKEN پیدا نشد."
        )

        return

    seen = load_seen_ads()

    print(
        f"📦 تعداد آگهی‌های قبلی: {len(seen)}"
    )

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page(
            locale="fa-IR",
            viewport={
                "width": 1440,
                "height": 900
            },
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            )
        )

        # -----------------------------------------
        # دریافت لینک‌ها
        # -----------------------------------------

        urls = get_listing_urls(page)

        new_urls = []

        for url in urls:

            ad_id = get_ad_id(url)

            if not ad_id:
                continue

            if ad_id not in seen:

                new_urls.append(url)

        print(
            f"🆕 آگهی جدید پیدا شده: {len(new_urls)}"
        )

        # -----------------------------------------
        # فقط 10 آگهی
        # -----------------------------------------

        new_urls = new_urls[:MAX_ADS_PER_RUN]

        sent_count = 0

        # -----------------------------------------
        # پردازش
        # -----------------------------------------

        for index, url in enumerate(
            new_urls,
            start=1
        ):

            print(
                "\n=============================="
            )

            print(
                f"📌 آگهی {index}/{len(new_urls)}"
            )

            print(url)

            ad = scrape_ad(
                page,
                url
            )

            if not ad:
                continue

            print(
                f"📝 عنوان: {ad['title']}"
            )

            telegram_text = build_telegram_post(
                ad
            )

            print(
                "\n----- متن نهایی -----"
            )

            print(telegram_text)

            print(
                "---------------------"
            )

            # -----------------------------------------
            # ارسال
            # -----------------------------------------

            success = send_telegram_message(
                telegram_text
            )

            if success:

                ad_id = ad["id"]

                if ad_id not in seen:

                    seen.append(ad_id)

                sent_count += 1

        browser.close()

    # -----------------------------------------
    # ذخیره
    # -----------------------------------------

    save_seen_ads(seen)

    print(
        f"💾 {len(seen)} آگهی ذخیره شد."
    )

    print(
        f"📨 تعداد ارسال موفق: {sent_count}"
    )

    print(
        "🏁 پایان اجرای ربات"
    )


if __name__ == "__main__":
    main()
```
