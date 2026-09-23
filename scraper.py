import os
import re
import json
import time
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


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


# =========================================================
# ابزارهای عمومی
# =========================================================

def clean_text(text):

    if not text:
        return ""

    text = text.replace("\u200c", " ")
    text = text.replace("\xa0", " ")

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n+", "\n", text)

    return text.strip()


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


# =========================================================
# Seen Ads
# =========================================================

def load_seen():

    if not os.path.exists(SEEN_FILE):
        return set()

    try:

        with open(
            SEEN_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

        if isinstance(data, list):
            return set(data)

    except Exception as e:

        print(
            f"⚠️ خطا در خواندن seen_ads.json: {e}"
        )

    return set()


def save_seen(seen):

    try:

        with open(
            SEEN_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                sorted(list(seen)),
                f,
                ensure_ascii=False,
                indent=2
            )

        print(
            f"💾 {len(seen)} آگهی ذخیره شد."
        )

    except Exception as e:

        print(
            f"❌ خطا در ذخیره seen_ads.json: {e}"
        )


# =========================================================
# دریافت لیست آگهی‌ها
# =========================================================

def get_listing_urls():

    print(
        "🌐 دریافت لیست آگهی‌ها..."
    )

    try:

        response = requests.get(
            JOB_URL,
            headers=DIVAR_HEADERS,
            timeout=30
        )

        print(
            f"🌐 Jobs page: HTTP {response.status_code}"
        )

        if response.status_code != 200:

            print(
                "❌ دریافت صفحه استخدام ناموفق بود."
            )

            return []

        html = response.text

    except Exception as e:

        print(
            f"❌ خطا در دریافت صفحه استخدام: {e}"
        )

        return []

    urls = []
    ids = set()

    try:

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        for a in soup.find_all(
            "a",
            href=True
        ):

            href = a.get("href")

            if not href:
                continue

            if "/v/" not in href:
                continue

            if href.startswith("/"):

                href = (
                    "https://divar.ir"
                    + href
                )

            elif href.startswith("//"):

                href = (
                    "https:"
                    + href
                )

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

        print(
            f"⚠️ خطا در استخراج لینک‌ها: {e}"
        )

    # fallback
    if not urls:

        print(
            "🔄 تلاش با Regex..."
        )

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

                        href = (
                            "https://divar.ir"
                            + href
                        )

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

    print(
        f"📋 تعداد آگهی‌های صفحه: {len(urls)}"
    )

    return urls


# =========================================================
# اطلاعات ساختاریافته
# =========================================================

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


# =========================================================
# اعتبارسنجی
# =========================================================

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


def valid_experience(value):

    if not value:
        return False

    value = value.strip()

    keywords = [

        "بدون نیاز",
        "بدون سابقه",
        "کمتر از",
        "کم تر از",
        "حداقل",
        "بیش از",
        "سال سابقه",
        "ماه سابقه",

    ]

    return any(
        x in value
        for x in keywords
    )


def valid_work_hours(value):

    if not value:
        return False

    value = value.strip()

    patterns = [

        r"از\s+\d{1,2}\s+تا\s+\d{1,2}",

        r"\d{1,2}\s*:\s*\d{2}\s+تا\s+\d{1,2}",

        r"\d{1,2}\s+تا\s+\d{1,2}",

    ]

    return any(
        re.search(
            pattern,
            value
        )
        for pattern in patterns
    )


# =========================================================
# استخراج سن
# =========================================================

def extract_age(text):

    if not text:
        return None

    patterns = [

        r"(?:سن|سنین)\s*(?:از)?\s*(\d{1,2})\s*(?:تا|-|الی)\s*(\d{1,2})\s*سال",

        r"(\d{1,2})\s*(?:تا|-|الی)\s*(\d{1,2})\s*سال",

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


# =========================================================
# استخراج حقوق
# =========================================================

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

            return clean_text(
                match.group(0)
            )

    return None


# =========================================================
# گرفتن متن واقعی توضیحات
# =========================================================

def get_real_description(page):

    """
    فقط بخش توضیحات واقعی آگهی را پیدا می‌کند.
    متن منوها و اطلاعات UI را حذف می‌کند.
    """

    try:

        # اول دنبال بخش‌هایی می‌گردیم که
        # خود Divar برای توضیحات استفاده می‌کند.

        candidates = page.locator(
            "div.kt-description"
        )

        if candidates.count() > 0:

            for i in range(
                candidates.count()
            ):

                try:

                    text = clean_text(
                        candidates.nth(i).inner_text()
                    )

                    if (
                        len(text) > 15
                        and "توضیحات" not in text[:20]
                    ):

                        return text

                except Exception:
                    pass

    except Exception:
        pass


    # -----------------------------------------------------
    # روش دوم: پیدا کردن متن «توضیحات» در DOM
    # -----------------------------------------------------

    try:

        result = page.evaluate(
            """
            () => {

                const all = Array.from(
                    document.querySelectorAll('*')
                );

                const candidates = all.filter(el => {

                    const text =
                        (el.innerText || '').trim();

                    return text === 'توضیحات';

                });

                for (const heading of candidates) {

                    let parent = heading.parentElement;

                    for (let i = 0; i < 6 && parent; i++) {

                        const text =
                            (parent.innerText || '').trim();

                        if (
                            text.length > 30 &&
                            text.length < 10000
                        ) {

                            return text;
                        }

                        parent = parent.parentElement;
                    }
                }

                return '';
            }
            """
        )

        result = clean_text(result)

        if result:

            # اگر داخل نتیجه خود عنوان توضیحات
            # وجود دارد، آن را حذف می‌کنیم.

            lines = [
                clean_text(x)
                for x in result.split("\n")
                if clean_text(x)
            ]

            cleaned = []

            started = False

            for line in lines:

                if line == "توضیحات":

                    started = True
                    continue

                if started:

                    cleaned.append(line)

            if cleaned:

                return "\n".join(
                    cleaned
                )

    except Exception:
        pass


    # -----------------------------------------------------
    # روش سوم: استخراج از متن صفحه
    # -----------------------------------------------------

    try:

        body = page.locator(
            "body"
        ).inner_text()

        body = clean_text(body)

        lines = [
            clean_text(x)
            for x in body.split("\n")
            if clean_text(x)
        ]

        # خطوطی که قطعاً UI هستند
        ui_lines = {

            "زنگ خطرهای قبل از همکاری",
            "اطلاعات تماس",
            "نوع همکاری",
            "سابقه",
            "شیوهٔ پرداخت",
            "عنوان شغلی",
            "دستمزد",
            "بیمه",
            "جنسیت",
            "وضعیت سربازی",
            "سایر ویژگی ها و امکانات",
            "توضیحات",
            "گزارش آگهی",
            "یادداشت تنها برای شما قابل دیدن است و پس از حذف آگهی، پاک خواهد شد.",
            "اشتراک‌گذاری",
            "ذخیره",
            "تماس",
            "چت",
        }

        # شروع واقعی متن را پیدا می‌کنیم
        start_index = -1

        for i, line in enumerate(lines):

            if line == "توضیحات":

                start_index = i + 1

        if start_index >= 0:

            result = []

            for line in lines[start_index:]:

                if line in ui_lines:
                    continue

                if line.startswith(
                    "استخدام ",
                ) and "در " in line:
                    continue

                if line.startswith(
                    "تصویر "
                ):
                    continue

                if line.startswith(
                    "یادداشت تنها"
                ):
                    continue

                if line == "گزارش آگهی":
                    continue

                result.append(line)

            if result:

                return "\n".join(result)

    except Exception:
        pass

    return ""


# =========================================================
# استخراج آگهی
# =========================================================

def extract_ad(page, url):

    ad_id = get_ad_id(url)

    print(
        f"\n🔎 بررسی آگهی: {ad_id}"
    )

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


    # -----------------------------------------------------
    # عنوان
    # -----------------------------------------------------

    title = ""

    selectors = [

        "h1",

        '[data-testid="ad-title"]',

        '[data-testid="title"]',

    ]

    for selector in selectors:

        try:

            loc = page.locator(
                selector
            )

            if loc.count() > 0:

                value = clean_text(
                    loc.first.inner_text()
                )

                if value:

                    title = value
                    break

        except Exception:
            pass


    # -----------------------------------------------------
    # اطلاعات ساختاریافته
    # -----------------------------------------------------

    info = get_structured_info(
        page
    )

    print(
        "📊 اطلاعات ساختاریافته:"
    )

    print(info)


    # -----------------------------------------------------
    # متن واقعی توضیحات
    # -----------------------------------------------------

    description = get_real_description(
        page
    )

    # -----------------------------------------------------
    # اطلاعات
    # -----------------------------------------------------

    gender = None

    if info.get("جنسیت"):

        gender = clean_text(
            info["جنسیت"]
        )


    # سابقه
    experience = None

    for key, value in info.items():

        if "سابقه" in key:

            if valid_experience(value):

                experience = clean_text(
                    value
                )

            break


    # نوع همکاری
    cooperation = None

    for key, value in info.items():

        if "نوع همکاری" in key:

            if valid_cooperation(value):

                cooperation = clean_text(
                    value
                )

            break


    # ساعت کاری
    work_hours = None

    for key, value in info.items():

        if "ساعت کاری" in key:

            if valid_work_hours(value):

                work_hours = clean_text(
                    value
                )

            break


    # پرداخت
    payment = None

    for key, value in info.items():

        if "پرداخت" in key:

            payment = clean_text(
                value
            )

            break


    # بیمه
    insurance = None

    for key, value in info.items():

        if "بیمه" in key:

            insurance = clean_text(
                value
            )

            break


    # حقوق
    salary = None

    for key, value in info.items():

        if (
            "دستمزد" in key
            or "حقوق" in key
        ):

            salary = extract_salary(
                value
            )

            if salary:
                break


    # اگر حقوق ساختاریافته نبود
    if not salary:

        salary = extract_salary(
            description
        )


    # سن
    age = extract_age(
        description
    )


    # اگر سن در توضیحات نبود،
    # از عنوان هم بررسی می‌کنیم.

    if not age:

        age = extract_age(
            title
        )


    # -----------------------------------------------------
    # استخراج اطلاعاتی که فقط داخل توضیحات آمده‌اند
    # -----------------------------------------------------

    if description:

        # نوع همکاری
        if not cooperation:

            cooperation_patterns = [

                r"\bتمام وقت\b",
                r"\bتمام‌وقت\b",

                r"\bپاره وقت\b",
                r"\bپاره‌وقت\b",

                r"\bکارآموزی\b",

                r"\bدورکاری\b",

                r"\bساعتی\b",

            ]

            for pattern in cooperation_patterns:

                match = re.search(
                    pattern,
                    description
                )

                if match:

                    cooperation = match.group(0)
                    break


        # سابقه
        if not experience:

            experience_patterns = [

                r"بدون نیاز به سابقه",

                r"بدون سابقه",

                r"کمتر از ۱ سال",

                r"کم تر از ۱ سال",

                r"کمتر از 1 سال",

                r"حداقل\s+\d+\s+سال",

                r"حداقل\s+[۰-۹]+\s+سال",

                r"\d+\s+سال سابقه",

                r"[۰-۹]+\s+سال سابقه",

            ]

            for pattern in experience_patterns:

                match = re.search(
                    pattern,
                    description
                )

                if match:

                    experience = clean_text(
                        match.group(0)
                    )

                    break


        # ساعت کاری
        if not work_hours:

            for line in description.split("\n"):

                line = clean_text(line)

                if not line:
                    continue

                if (
                    "ساعت کاری" in line
                    or "ساعت" in line
                ):

                    if valid_work_hours(line):

                        work_hours = line
                        break


    # -----------------------------------------------------
    # دورکاری
    # -----------------------------------------------------

    remote = None

    if description:

        remote_keywords = [

            "امکان دورکاری",
            "دورکاری",
            "کار در منزل",
            "کاردرمنزل",

        ]

        for keyword in remote_keywords:

            if keyword in description:

                remote = "دارد"
                break


    # -----------------------------------------------------
    # اگر عنوان پیدا نشد
    # -----------------------------------------------------

    if not title:

        title = "استخدام نیرو"


    # -----------------------------------------------------
    # خروجی
    # -----------------------------------------------------

    return {

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

        "description": description,

    }


# =========================================================
# پاکسازی نهایی توضیحات
# =========================================================

def clean_description(
    description,
    ad
):

    if not description:
        return ""

    lines = [

        clean_text(x)

        for x in description.split("\n")

        if clean_text(x)

    ]


    # UIهای Divar که نباید در پست باشند

    blacklist_exact = {

        "زنگ خطرهای قبل از همکاری",
        "اطلاعات تماس",
        "نوع همکاری",
        "سابقه",
        "شیوهٔ پرداخت",
        "عنوان شغلی",
        "دستمزد",
        "بیمه",
        "جنسیت",
        "وضعیت سربازی",
        "سایر ویژگی ها و امکانات",
        "توضیحات",
        "گزارش آگهی",
        "اشتراک‌گذاری",
        "ذخیره",

        "یادداشت تنها برای شما قابل دیدن است و پس از حذف آگهی، پاک خواهد شد.",

    }


    # اطلاعاتی که قبلاً به صورت فیلد آمده‌اند
    used_values = set()

    for key in [

        "gender",
        "age",
        "experience",
        "cooperation",
        "work_hours",
        "salary",
        "payment",
        "insurance",

    ]:

        value = ad.get(key)

        if value:

            used_values.add(
                clean_text(value)
            )


    result = []


    for line in lines:

        if line in blacklist_exact:
            continue


        if line in used_values:
            continue


        # خطوط زمان/لوکیشن بالای آگهی

        if re.match(
            r"^(امروز|دیروز|پریروز|دقایقی پیش|ساعتی پیش|چند روز پیش|چند هفته پیش|ماه پیش|\d+\s+(روز|هفته|ماه)\s+پیش)",
            line
        ):

            continue


        # دسته‌بندی‌های انتهای آگهی

        if line.startswith(
            "استخدام "
        ) and "در " in line:

            continue


        if line.startswith(
            "تصویر "
        ):

            continue


        if line.startswith(
            "یادداشت تنها"
        ):

            continue


        if line == "گزارش آگهی":
            continue


        # متن‌های صرفاً UI

        if line in [

            "فروشنده",
            "کارمند فروش",
            "باریستا",
            "حسابدار",

        ]:

            # فقط اگر خط به شکل تگ انتهای صفحه باشد
            continue


        result.append(line)


    return "\n".join(result)


# =========================================================
# ساخت پست
# =========================================================

def make_post(ad):

    title = (
        ad.get("title")
        or "استخدام نیرو"
    )


    post = []

    # -----------------------------------------------------
    # عنوان
    # -----------------------------------------------------

    post.append(
        f"# 🟢 {title}"
    )

    post.append("")


    # -----------------------------------------------------
    # اطلاعات
    # -----------------------------------------------------

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


    # -----------------------------------------------------
    # توضیحات
    # -----------------------------------------------------

    description = clean_description(
        ad.get("description"),
        ad
    )


    if description:

        post.append("")

        post.append(
            "### 🟢 توضیحات"
        )

        post.append("")

        for line in description.split("\n"):

            line = clean_text(line)

            if line:

                post.append(
                    f"🟢 {line}"
                )


    # -----------------------------------------------------
    # آیدی‌های کانال
    # -----------------------------------------------------

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


# =========================================================
# Telegram
# =========================================================

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


# =========================================================
# Main
# =========================================================

def main():

    print(
        "🚀 شروع ربات"
    )


    if not BOT_TOKEN:

        print(
            "❌ BOT_TOKEN تنظیم نشده!"
        )

        return


    seen = load_seen()


    print(
        f"📦 تعداد آگهی‌های قبلی: {len(seen)}"
    )


    # -----------------------------------------------------
    # لیست آگهی‌ها
    # -----------------------------------------------------

    urls = get_listing_urls()


    if not urls:

        print(
            "❌ هیچ آگهی‌ای پیدا نشد."
        )

        return


    # -----------------------------------------------------
    # فقط جدیدها
    # -----------------------------------------------------

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


    # فقط ۱۰ عدد
    new_urls = new_urls[:10]


    if not new_urls:

        print(
            "ℹ️ آگهی جدیدی برای ارسال وجود ندارد."
        )

        return


    # -----------------------------------------------------
    # Playwright
    # -----------------------------------------------------

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


        # -------------------------------------------------
        # پردازش
        # -------------------------------------------------

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

            print(
                url
            )


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


                post = make_post(
                    ad
                )


                print(
                    "\n----- متن نهایی -----\n"
                )

                print(
                    post
                )

                print(
                    "\n---------------------\n"
                )


                # ارسال
                success = send_telegram(
                    post
                )


                if success:

                    if ad["id"]:

                        seen.add(
                            ad["id"]
                        )


                    time.sleep(2)


                else:

                    print(
                        "⚠️ ارسال ناموفق بود؛ "
                        "آگهی seen نمی‌شود."
                    )


            except Exception as e:

                print(
                    f"❌ خطا در پردازش آگهی: {e}"
                )


        browser.close()


    # -----------------------------------------------------
    # ذخیره
    # -----------------------------------------------------

    save_seen(
        seen
    )


    print(
        "🏁 پایان اجرای ربات"
    )


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    main()
