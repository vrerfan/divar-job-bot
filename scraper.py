import os
import re
import json
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

JOB_URL = "https://divar.ir/s/alborz-province/jobs"
SEEN_FILE = "seen_ads.json"
CHAT_ID = "8531717188"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def fa_to_en(text):
    table = str.maketrans(
        "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
        "01234567890123456789"
    )
    return str(text or "").translate(table)


def en_to_fa(text):
    table = str.maketrans(
        "0123456789",
        "۰۱۲۳۴۵۶۷۸۹"
    )
    return str(text or "").translate(table)


def clean_line(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def normalize_text(text):
    text = fa_to_en(text or "").lower()
    text = text.replace("\u200c", "")
    text = re.sub(r"[\W_]+", "", text, flags=re.UNICODE)
    return text


def same_title(a, b):
    a = normalize_text(a)
    b = normalize_text(b)

    if not a or not b:
        return True

    if a == b:
        return True

    shorter = min(a, b, key=len)

    if len(shorter) >= 5 and (a in b or b in a):
        return True

    return False


def get_ad_id(url):
    return url.rstrip("/").split("/")[-1].split("?")[0]


def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(
            sorted(seen),
            f,
            ensure_ascii=False,
            indent=2
        )


def get_page_text(page):
    try:
        return page.locator("body").inner_text(timeout=5000)
    except Exception:
        return ""


def extract_structured(page):
    data = {}

    rows = page.locator(
        'div[data-testid="unexpandable-info-row"]'
    )

    for i in range(rows.count()):
        try:
            row = rows.nth(i)
            ps = row.locator("p")

            if ps.count() >= 2:
                key = clean_line(
                    ps.nth(0).inner_text()
                )

                value = clean_line(
                    ps.nth(1).inner_text()
                )

                if key and value:
                    data[key] = value

        except Exception:
            pass

    return data


def extract_body_metadata(page):
    return {}


def get_real_description(page):
    """
    فقط متن واقعی صاحب آگهی را استخراج می‌کند.
    از بعد «توضیحات» شروع می‌شود و قبل از
    دسته‌بندی/اطلاعات پایین آگهی متوقف می‌شود.
    """

    text = get_page_text(page)

    if not text:
        return []

    lines = [
        clean_line(x)
        for x in text.splitlines()
        if clean_line(x)
    ]

    start = None

    for i, line in enumerate(lines):
        if line == "توضیحات":
            start = i + 1
            break

    if start is None:
        return []

    result = []

    stop_exact = {
        "دربارهٔ دیوار",
        "درباره دیوار",
        "دریافت برنامه",
        "اتاق خبر",
        "دیواری شو",
        "پشتیبانی و قوانین",
        "گزارش آگهی",
        "گزارش تخلف",
        "ثبت آگهی",
    }

    for line in lines[start:]:

        # پایان قطعی صفحه
        if line in stop_exact:
            break

        # دسته‌بندی دیوار
        if line.startswith("استخدام "):
            break

        # تصویر
        if re.fullmatch(
            r"تصویر\s+\d+\s+از\s+\d+",
            line
        ):
            break

        # یادداشت دیوار
        if line.startswith("یادداشت تنها برای شما"):
            break

        # بعضی عناصر رابط کاربری
        if line in {
            "چت",
            "تماس",
            "چت و تماس",
            "پشتیبانی",
            "دیوار من",
            "دسته‌ها",
            "انتخاب شهر",
            "برو به اطلاعات تماس",
        }:
            continue

        result.append(line)

    # حذف موارد رابط کاربری احتمالی انتهای متن
    bad_lines = {
        "یادداشت تنها برای شما قابل دیدن است و پس از حذف آگهی، پاک خواهد شد.",
        "اشتراک‌گذاری آگهی",
    }

    result = [
        x for x in result
        if x not in bad_lines
    ]

    # حذف تکراری‌های پشت سر هم
    clean = []

    for line in result:
        if not clean or clean[-1] != line:
            clean.append(line)

    return clean


def extract_phones(page):
    phones = []

    # شماره‌های تستی/نمونه‌ای که نباید منتشر شوند
    invalid_phones = {
        "09121234567",
        "09120000000",
        "09000000000",
        "09999999999",
    }

    def add_phone(number):
        number = fa_to_en(number)
        number = re.sub(r"[^\d]", "", number)

        if not re.fullmatch(r"09\d{9}", number):
            return

        if number in invalid_phones:
            return

        if number not in phones:
            phones.append(number)

    # 1. لینک tel
    try:
        links = page.locator('a[href^="tel:"]')

        for i in range(links.count()):
            href = (
                links.nth(i)
                .get_attribute("href")
                or ""
            )

            for number in re.findall(
                r"09[\d\s\-]{9,15}",
                fa_to_en(href)
            ):
                add_phone(number)

    except Exception:
        pass

    # 2. متن صفحه
    try:
        body = fa_to_en(
            get_page_text(page)
        )

        for number in re.findall(
            r"(?<!\d)09[\d\s\-]{9,15}(?!\d)",
            body
        ):
            add_phone(number)

    except Exception:
        pass

    # 3. HTML
    try:
        html = fa_to_en(
            page.content()
        )

        for number in re.findall(
            r"(?<!\d)09[\d\s\-]{9,15}(?!\d)",
            html
        ):
            add_phone(number)

    except Exception:
        pass

    # 4. دکمه نمایش شماره
    if not phones:

        try:
            buttons = page.locator("button")

            for i in range(buttons.count()):

                try:
                    button = buttons.nth(i)

                    button_text = clean_line(
                        button.inner_text(
                            timeout=1000
                        )
                    )

                    aria = (
                        button.get_attribute(
                            "aria-label"
                        )
                        or ""
                    )

                    combined = (
                        f"{button_text} {aria}"
                    )

                    if not any(
                        word in combined
                        for word in [
                            "شماره",
                            "تماس",
                            "تلفن",
                            "اطلاعات تماس"
                        ]
                    ):
                        continue

                    button.click(
                        timeout=3000
                    )

                    page.wait_for_timeout(
                        1200
                    )

                    body = fa_to_en(
                        get_page_text(page)
                    )

                    for number in re.findall(
                        r"(?<!\d)09[\d\s\-]{9,15}(?!\d)",
                        body
                    ):
                        add_phone(number)

                    if phones:
                        break

                except Exception:
                    continue

        except Exception:
            pass

    return [
        en_to_fa(x)
        for x in phones
    ]


def extract_fields(
    structured,
    body_metadata,
    description_lines
):
    fields = {}

    # فقط اطلاعات واقعی ساختاریافته دیوار
    for key, target in {
        "جنسیت": "جنسیت",
        "دستمزد": "حقوق",
        "شیوهٔ پرداخت": "پرداخت",
        "بیمه": "بیمه",
        "ساعت کاری": "ساعت کاری",
    }.items():

        value = structured.get(key)

        if value:
            fields[target] = value

    text = "\n".join(
        description_lines
    )

    # نوع همکاری فقط از متن واقعی توضیحات
    if "نوع همکاری" not in fields:

        for value in [
            "تمام وقت",
            "تمام‌وقت",
            "پاره وقت",
            "پاره‌وقت",
            "کارآموزی",
            "دورکاری",
            "پروژه‌ای",
            "پروژه ای",
            "ساعتی"
        ]:

            if value in text:
                fields["نوع همکاری"] = value
                break

    # سابقه فقط از متن واقعی توضیحات
    if "سابقه کار" not in fields:

        patterns = [
            r"بدون نیاز به سابقه",
            r"حداقل\s*[\d۰-۹]+\s*سال سابقه",
            r"[\d۰-۹]+\s*سال سابقه"
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                text
            )

            if match:
                fields["سابقه کار"] = (
                    match.group(0)
                )
                break

    # سن
    english_text = fa_to_en(text)

    match = re.search(
        r"(?:سن(?:ین)?|محدوده سنی|شرایط سنی)"
        r"[^.\n]{0,30}"
        r"(\d{1,2})\s*"
        r"(?:تا|الی|-)\s*"
        r"(\d{1,2})\s*سال",
        english_text
    )

    if match:
        fields["محدوده سنی"] = en_to_fa(
            f"{match.group(1)} تا "
            f"{match.group(2)} سال"
        )

    # اگر دیوار حقوق نداشت، از توضیحات استخراج کن
    if "حقوق" not in fields:

        for line in description_lines:

            if not re.search(
                r"حقوق|دستمزد|درآمد|دریافتی",
                line
            ):
                continue

            if re.search(
                r"\d.*(?:میلیون|تومان)|توافقی",
                fa_to_en(line)
            ):
                fields["حقوق"] = line
                break

    # اگر دیوار ساعت کاری نداشت
    if "ساعت کاری" not in fields:

        for line in description_lines:

            english_line = fa_to_en(line)

            pattern = (
                r"\b\d{1,2}"
                r"(?::\d{2})?"
                r"\s*(?:صبح|ظهر|عصر|بعدازظهر)?"
                r"\s*(?:تا|الی|-)"
                r"\s*\d{1,2}"
                r"(?::\d{2})?"
            )

            if re.search(
                pattern,
                english_line
            ):
                if any(
                    x in line
                    for x in [
                        "ساعت",
                        "صبح",
                        "ظهر",
                        "عصر",
                        "الی",
                        "تا"
                    ]
                ):
                    fields["ساعت کاری"] = line
                    break

    return fields


def build_post(
    title,
    fields,
    description_lines,
    phones
):
    output = []

    output.append(
        f"# 🟢 {title}"
    )

    # عنوان شغلی فقط اگر با عنوان اصلی فرق داشته باشد
    job_title = None

    # عمداً از عنوان شغلی ساختاریافته استفاده نمی‌کنیم
    # تا عنوان تکراری یا اضافی وارد آگهی نشود.

    order = [
        "جنسیت",
        "محدوده سنی",
        "سابقه کار",
        "نوع همکاری",
        "ساعت کاری",
        "حقوق",
        "پرداخت",
        "بیمه"
    ]

    for key in order:

        value = fields.get(key)

        if value:
            output.append(
                f"🟢 {key}: {value}"
            )

    if description_lines:

        output.append("")
        output.append(
            "### 🟢 توضیحات"
        )

        for line in description_lines:
            output.append(
                f"🟢 {line}"
            )

    if phones:

        output.append("")

        for phone in phones:
            output.append(
                f"📞 {phone}"
            )

    output.extend([
        "",
        "کانال تلگرام",
        "@karyabi_alborzi",
        "",
        "جهت ثبت آگهی",
        "@Karyabi_karaji"
    ])

    return "\n".join(output)


def send_telegram(text):
    token = os.getenv("BOT_TOKEN")

    if not token:
        raise RuntimeError(
            "BOT_TOKEN تنظیم نشده است."
        )

    url = (
        "https://api.telegram.org/"
        f"bot{token}/sendMessage"
    )

    response = requests.post(
        url,
        json={
            "chat_id": CHAT_ID,
            "text": text
        },
        timeout=30
    )

    if not response.ok:
        raise RuntimeError(
            response.text
        )


def get_listing_urls():
    print(
        "🌐 دریافت لیست آگهی‌ها..."
    )

    headers = {
        "User-Agent": UA,
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,*/*;q=0.8"
        ),
        "Accept-Language":
            "fa-IR,fa;q=0.9,en-US;q=0.8",
        "Referer":
            "https://divar.ir/"
    }

    try:

        response = requests.get(
            JOB_URL,
            headers=headers,
            timeout=30
        )

        print(
            f"🌐 Jobs page: HTTP "
            f"{response.status_code}"
        )

        if response.status_code != 200:
            return []

        html = response.text

    except Exception as e:

        print(
            f"❌ خطا در دریافت لیست: {e}"
        )

        return []

    urls = []

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    candidates = []

    for a in soup.find_all(
        "a",
        href=True
    ):
        candidates.append(
            a["href"]
        )

    candidates += re.findall(
        r'(?:https://divar\.ir)?'
        r'/v/[^"\'<>\s]+',
        html
    )

    escaped = re.findall(
        r'(?:https?:)?'
        r'\\/\\/divar\.ir'
        r'\\/v\\/[^"\'<>\s]+',
        html
    )

    candidates += [
        x.replace("\\/", "/")
        for x in escaped
    ]

    for href in candidates:

        href = href.replace(
            "\\/",
            "/"
        )

        if href.startswith("/"):
            href = (
                "https://divar.ir"
                + href
            )

        if not href.startswith(
            "https://divar.ir/v/"
        ):
            continue

        href = href.split("?")[0]
        href = href.split("#")[0]

        ad_id = get_ad_id(href)

        if len(ad_id) < 5:
            continue

        if not any(
            get_ad_id(old) == ad_id
            for old in urls
        ):
            urls.append(href)

    print(
        f"📋 تعداد آگهی‌های صفحه: "
        f"{len(urls)}"
    )

    return urls


def main():

    print(
        "🚀 شروع ربات\n"
    )

    seen = load_seen()

    print(
        f"📦 تعداد آگهی‌های قبلی: "
        f"{len(seen)}\n"
    )

    urls = get_listing_urls()

    new_ads = [
        url
        for url in urls
        if get_ad_id(url) not in seen
    ]

    print(
        f"🆕 آگهی جدید پیدا شده: "
        f"{len(new_ads)}"
    )

    sent_count = 0

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page(
            user_agent=UA,
            locale="fa-IR"
        )

        for index, url in enumerate(
            new_ads[:10],
            start=1
        ):

            print(
                "\n==============================\n"
            )

            ad_id = get_ad_id(url)

            print(
                f"📌 آگهی {index}/10"
            )

            print(
                f"🔎 بررسی آگهی: {ad_id}"
            )

            try:

                page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=30000
                )

                page.wait_for_timeout(
                    1500
                )

                structured = (
                    extract_structured(page)
                )

                print(
                    "📊 اطلاعات ساختاریافته:"
                )

                print(structured)

                title = ""

                try:

                    h1 = page.locator("h1")

                    if h1.count():

                        title = clean_line(
                            h1.first.inner_text(
                                timeout=5000
                            )
                        )

                except Exception:
                    pass

                if not title:

                    title = clean_line(
                        page.title()
                    ).replace(
                        " | دیوار",
                        ""
                    )

                description = (
                    get_real_description(page)
                )

                phones = extract_phones(
                    page
                )

                if phones:

                    print(
                        f"📞 شماره پیدا شد: "
                        f"{phones}"
                    )

                else:

                    print(
                        "📞 شماره تماس پیدا نشد."
                    )

                fields = extract_fields(
                    structured,
                    {},
                    description
                )

                post = build_post(
                    title,
                    fields,
                    description,
                    phones
                )

                print(
                    "\n----- متن نهایی -----\n"
                )

                print(post)

                send_telegram(post)

                seen.add(ad_id)

                sent_count += 1

                print(
                    "\n---------------------\n"
                )

                print(
                    "✅ پیام با موفقیت ارسال شد."
                )

            except Exception as e:

                print(
                    f"❌ خطا در آگهی "
                    f"{ad_id}: {e}"
                )

        browser.close()

    save_seen(seen)

    print(
        f"\n📨 تعداد آگهی ارسال‌شده: "
        f"{sent_count}"
    )

    print(
        f"💾 {len(seen)} آگهی ذخیره شد."
    )

    print(
        "🏁 پایان اجرای ربات"
    )


if __name__ == "__main__":
    main()
