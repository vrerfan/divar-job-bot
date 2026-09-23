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


def get_page_text(page):
    try:
        return page.locator(
            "body"
        ).inner_text(timeout=5000)
    except Exception:
        return ""


def get_real_description(page, title):
    """
    فقط متن واقعی توضیحات آگهی را استخراج می‌کند
    و اطلاعات رابط کاربری دیوار را حذف می‌کند.
    """

    text = get_page_text(page)

    if not text:
        return []

    lines = []

    # خطوطی که نباید وارد توضیحات شوند
    ignored_exact = {
        "چت",
        "اطلاعات تماس",
        "گزارش آگهی",
        "یادداشت",
        "سابقه",
        "نوع همکاری",
        "شیوهٔ پرداخت",
        "عنوان شغلی",
        "دستمزد",
        "بیمه",
        "جنسیت",
        "وضعیت تاهل",
        "وضعیت سربازی",
        "سایر ویژگی‌ها و امکانات",
        "توضیحات",
        "۱"
    }

    ignored_contains = [
        "زنگ خطرهای قبل از همکاری",
        "یادداشت تنها برای شما",
        "این آگهی را به دوستانتان",
        "گزارش تخلف",
        "اشتراک‌گذاری آگهی"
    ]

    # این خطوط مشخصاً متادیتای بالای صفحه هستند
    metadata_patterns = [
        r"^\d+\s*(دقیقه|دقیقه‌ای|ساعت|ساعت پیش|روز|روز پیش|هفته|ماه)\s*پیش",
        r"^پریروز در ",
        r"^دیروز در ",
        r"^امروز در ",
        r"^دقایقی پیش در ",
        r"^لحظاتی پیش در ",
        r"^در .+، .+$"
    ]

    raw_lines = text.splitlines()

    # تشخیص شروع توضیحات واقعی
    description_started = False

    for raw in raw_lines:
        line = clean_line(raw)

        if not line:
            continue

        # حذف عنوان تکراری
        if line == title:
            continue

        # حذف موارد کاملاً مشخص
        if line in ignored_exact:
            continue

        # حذف UI
        if any(
            item in line
            for item in ignored_contains
        ):
            continue

        # حذف تصویر
        if re.fullmatch(
            r"تصویر\s+\d+\s+از\s+\d+",
            line
        ):
            continue

        # حذف متادیتای زمان/مکان
        is_metadata = False

        for pattern in metadata_patterns:
            if re.search(
                pattern,
                line,
                re.IGNORECASE
            ):
                is_metadata = True
                break

        if is_metadata:
            continue

        # اگر خط «توضیحات» بود، از بعد آن متن واقعی شروع می‌شود
        if line == "توضیحات":
            description_started = True
            continue

        # حذف عنوان‌های دسته‌بندی دیوار
        if line.startswith("استخدام ") and (
            "در " in line
            or line in {
                "استخدام رایانه و فناوری اطلاعات",
                "استخدام مالی، حسابداری، حقوقی",
                "استخدام اداری و مدیریت",
                "استخدام صنعتی، فنی، مهندسی",
                "استخدام خدمات فروشگاه و رستوران",
                "استخدام بازاریابی و فروش"
            }
        ):
            continue

        lines.append(line)

    # حذف متادیتای باقی‌مانده در ابتدای متن
    while lines:
        first = lines[0]

        if first in ignored_exact:
            lines.pop(0)
            continue

        if re.search(
            r"^\d+\s*(دقیقه|ساعت|روز|هفته|ماه)",
            first
        ):
            lines.pop(0)
            continue

        break

    # حذف خطوط انتهایی مربوط به دسته‌بندی دیوار
    cut_words = {
        "استخدام سرایداری و نظافت",
        "استخدام رایانه و فناوری اطلاعات",
        "استخدام مالی، حسابداری، حقوقی",
        "استخدام اداری و مدیریت",
        "استخدام صنعتی، فنی، مهندسی",
        "استخدام خدمات فروشگاه و رستوران",
        "استخدام بازاریابی و فروش"
    }

    clean = []

    for line in lines:
        if line in cut_words:
            break

        clean.append(line)

    # حذف تکراری‌های پشت سر هم
    result = []

    for line in clean:
        if not result or result[-1] != line:
            result.append(line)

    return result


def extract_phones(page):
    phones = []

    def add_phone(number):
        number = fa_to_en(number)
        number = re.sub(r"[^\d]", "", number)

        if re.fullmatch(
            r"09\d{9}",
            number
        ):
            if number not in phones:
                phones.append(number)

    # 1. لینک tel
    try:
        links = page.locator(
            'a[href^="tel:"]'
        )

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
            page.locator("body").inner_text(
                timeout=5000
            )
        )

        for number in re.findall(
            r"(?<!\d)09[\d\s\-]{9,15}(?!\d)",
            body
        ):
            add_phone(number)

    except Exception:
        pass

    # 3. HTML / JSON
    if not phones:
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

    # 4. تلاش برای باز کردن شماره
    if not phones:
        buttons = [
            "نمایش شماره",
            "شماره تلفن",
            "نمایش تلفن",
            "اطلاعات تماس"
        ]

        for button_text in buttons:
            try:
                locator = page.get_by_text(
                    button_text,
                    exact=False
                )

                if locator.count():
                    locator.first.click(
                        timeout=2000
                    )

                    page.wait_for_timeout(
                        1000
                    )

                    body = fa_to_en(
                        page.locator(
                            "body"
                        ).inner_text(
                            timeout=5000
                        )
                    )

                    for number in re.findall(
                        r"(?<!\d)09[\d\s\-]{9,15}(?!\d)",
                        body
                    ):
                        add_phone(number)

                    if phones:
                        break

            except Exception:
                pass

    return [
        en_to_fa(phone)
        for phone in phones
    ]


def extract_fields(
    structured,
    description_lines
):
    fields = {}

    # اطلاعات مستقیم دیوار
    if structured.get("جنسیت"):
        fields["جنسیت"] = structured["جنسیت"]

    if structured.get("دستمزد"):
        fields["حقوق"] = structured["دستمزد"]

    if structured.get("شیوهٔ پرداخت"):
        fields["پرداخت"] = structured["شیوهٔ پرداخت"]

    if structured.get("بیمه"):
        fields["بیمه"] = structured["بیمه"]

    if structured.get("عنوان شغلی"):
        fields["عنوان شغلی"] = structured["عنوان شغلی"]

    if structured.get("ساعت کاری"):
        fields["ساعت کاری"] = structured["ساعت کاری"]

    if structured.get("نوع همکاری"):
        fields["نوع همکاری"] = structured["نوع همکاری"]

    if structured.get("سابقه کار"):
        fields["سابقه کار"] = structured["سابقه کار"]

    text = "\n".join(
        description_lines
    )

    # نوع همکاری
    if "نوع همکاری" not in fields:
        cooperation = [
            "تمام وقت",
            "تمام‌وقت",
            "پاره وقت",
            "پاره‌وقت",
            "کارآموزی",
            "دورکاری",
            "پروژه‌ای",
            "پروژه ای",
            "ساعتی"
        ]

        for value in cooperation:
            if value in text:
                fields["نوع همکاری"] = value
                break

    # سابقه
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
    if "محدوده سنی" not in fields:
        english_text = fa_to_en(text)

        match = re.search(
            r"(?:سن(?:ین)?|محدوده سنی|شرایط سنی)"
            r"[^.\n]{0,30}"
            r"(\d{1,2})\s*"
            r"(?:تا|الی|-)\s*"
            r"(\d{1,2})\s*سال",
            english_text,
            re.IGNORECASE
        )

        if match:
            fields["محدوده سنی"] = en_to_fa(
                f"{match.group(1)} تا "
                f"{match.group(2)} سال"
            )

    # حقوق
    if "حقوق" not in fields:
        for line in description_lines:
            if re.search(
                r"حقوق|دستمزد|درآمد|دریافتی",
                line
            ):
                if re.search(
                    r"\d.*(?:میلیون|تومان)|توافقی",
                    fa_to_en(line)
                ):
                    fields["حقوق"] = line
                    break

    # ساعت کاری
    if "ساعت کاری" not in fields:
        for line in description_lines:
            english_line = fa_to_en(line)

            if any(
                word in english_line
                for word in [
                    "میلیون",
                    "سال",
                    "سن",
                    "درآمد",
                    "حقوق",
                    "دستمزد"
                ]
            ):
                continue

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
                if (
                    "ساعت" in line
                    or "صبح" in line
                    or "عصر" in line
                    or "الی" in line
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

    # عنوان
    output.append(
        f"# 🟢 {title}"
    )

    # عنوان شغلی فقط اگر تکراری نباشد
    job_title = fields.get(
        "عنوان شغلی"
    )

    if (
        job_title
        and not same_title(
            title,
            job_title
        )
    ):
        output.append(
            f"🟢 عنوان شغلی: {job_title}"
        )

    # اطلاعات
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

    # توضیحات واقعی
    if description_lines:
        output.append("")
        output.append(
            "### 🟢 توضیحات"
        )

        for line in description_lines:
            output.append(
                f"🟢 {line}"
            )

    # شماره تماس
    if phones:
        output.append("")

        for phone in phones:
            output.append(
                f"📞 {phone}"
            )

    # آیدی‌های ثابت
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
    token = os.getenv(
        "BOT_TOKEN"
    )

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

            print(
                f"📌 آگهی {index}/10"
            )

            print(url)

            ad_id = get_ad_id(url)

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

                # اطلاعات ساختاریافته
                structured = (
                    extract_structured(page)
                )

                print(
                    "📊 اطلاعات ساختاریافته:"
                )

                print(structured)

                # عنوان
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

                # توضیحات واقعی
                description = (
                    get_real_description(
                        page,
                        title
                    )
                )

                # شماره
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

                # فیلدها
                fields = extract_fields(
                    structured,
                    description
                )

                # ساخت پست
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

                # ارسال
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
