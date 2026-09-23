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


def normalize_text(text):
    text = fa_to_en(text or "").lower()
    text = re.sub(r"[\u200c\u200d]", "", text)
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


def clean_line(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


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


def clean_description(text):
    lines = []

    ignored = {
        "زنگ خطرهای قبل از همکاری",
        "اطلاعات تماس",
        "گزارش آگهی",
        "یادداشت تنها برای شما قابل دیدن است و پس از حذف آگهی، پاک خواهد شد."
    }

    for raw in (text or "").splitlines():
        line = clean_line(raw)

        if not line:
            continue

        if line in ignored:
            continue

        if re.fullmatch(r"تصویر \d+ از \d+", line):
            continue

        lines.append(line)

    cut_markers = {
        "استخدام بازاریابی و فروش",
        "استخدام مالی، حسابداری، حقوقی",
        "استخدام صنعتی، فنی، مهندسی",
        "استخدام خدمات فروشگاه و رستوران",
        "استخدام اداری و مدیریت"
    }

    for i, line in enumerate(lines):
        if line in cut_markers:
            lines = lines[:i]
            break

    return lines


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
                key = clean_line(ps.nth(0).inner_text())
                value = clean_line(ps.nth(1).inner_text())

                if key and value:
                    data[key] = value

        except Exception:
            pass

    return data


def get_ad_text(page):
    try:
        article = page.locator("article")

        if article.count():
            text = article.first.inner_text(timeout=5000)

            if len(text.strip()) > 50:
                return text

    except Exception:
        pass

    try:
        return page.locator("body").inner_text(timeout=5000)
    except Exception:
        return ""


def extract_phones(page, body_text):
    phones = []

    def add_phone(number):
        number = fa_to_en(number)
        number = re.sub(r"[^\d]", "", number)

        if re.fullmatch(r"09\d{9}", number):
            if number not in phones:
                phones.append(number)

    # 1. شماره‌های داخل لینک tel
    try:
        links = page.locator('a[href^="tel:"]')

        for i in range(links.count()):
            href = links.nth(i).get_attribute("href") or ""

            for number in re.findall(
                r"09[\d\s\-]{9,15}",
                fa_to_en(href)
            ):
                add_phone(number)

    except Exception:
        pass

    # 2. شماره داخل متن قابل مشاهده
    text = fa_to_en(body_text)

    for number in re.findall(
        r"(?<!\d)09[\d\s\-]{9,15}(?!\d)",
        text
    ):
        add_phone(number)

    # 3. شماره احتمالی داخل HTML / JSON صفحه
    if not phones:
        try:
            html = fa_to_en(page.content())

            for number in re.findall(
                r"(?<!\d)09[\d\s\-]{9,15}(?!\d)",
                html
            ):
                add_phone(number)

        except Exception:
            pass

    # 4. اگر شماره هنوز پیدا نشد، دکمه‌های تماس را امتحان کن
    if not phones:
        buttons = [
            "شماره تلفن",
            "نمایش شماره",
            "نمایش تلفن",
            "اطلاعات تماس",
            "تماس"
        ]

        for button_text in buttons:
            try:
                locator = page.get_by_text(
                    button_text,
                    exact=False
                )

                if locator.count():
                    locator.first.click(timeout=1500)
                    page.wait_for_timeout(1000)

                    new_text = page.locator(
                        "body"
                    ).inner_text(timeout=5000)

                    for number in re.findall(
                        r"09[\d\s\-]{9,15}",
                        fa_to_en(new_text)
                    ):
                        add_phone(number)

                    if phones:
                        break

            except Exception:
                pass

    return [en_to_fa(phone) for phone in phones]


def extract_fields(structured, description_lines):
    fields = {}

    # اطلاعات ساختاریافته خود دیوار
    if structured.get("جنسیت"):
        fields["جنسیت"] = structured["جنسیت"]

    if structured.get("شیوهٔ پرداخت"):
        fields["پرداخت"] = structured["شیوهٔ پرداخت"]

    if structured.get("دستمزد"):
        fields["حقوق"] = structured["دستمزد"]

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

    text = "\n".join(description_lines)

    # نوع همکاری
    if "نوع همکاری" not in fields:
        cooperation_patterns = [
            "تمام وقت",
            "تمام‌وقت",
            "پاره وقت",
            "پاره‌وقت",
            "کارآموزی",
            "پروژه‌ای",
            "پروژه ای",
            "دورکاری",
            "ساعتی"
        ]

        for value in cooperation_patterns:
            if value in text:
                fields["نوع همکاری"] = value
                break

    # سابقه کار
    if "سابقه کار" not in fields:
        patterns = [
            r"بدون نیاز به سابقه",
            r"حداقل\s*[\d۰-۹]+\s*سال سابقه",
            r"[\d۰-۹]+\s*سال سابقه",
            r"کمتر از\s*[\d۰-۹]+\s*سال سابقه"
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)

            if match:
                fields["سابقه کار"] = match.group(0)
                break

    # سن
    if "محدوده سنی" not in fields:
        english_text = fa_to_en(text)

        match = re.search(
            r"(?:سن(?:ین)?|محدوده سنی|رده سنی)"
            r"[^.\n]{0,30}"
            r"(\d{1,2})\s*(?:تا|الی|-)\s*(\d{1,2})\s*سال",
            english_text,
            re.IGNORECASE
        )

        if match:
            fields["محدوده سنی"] = en_to_fa(
                f"{match.group(1)} تا {match.group(2)} سال"
            )

        else:
            match = re.search(
                r"(?:حداکثر سن|حداکثر)\s*(\d{1,2})\s*سال",
                english_text,
                re.IGNORECASE
            )

            if match:
                fields["محدوده سنی"] = en_to_fa(
                    f"حداکثر {match.group(1)} سال"
                )

    # جنسیت از متن
    if "جنسیت" not in fields:
        if re.search(r"فقط\s*(?:آقا|اقا|مرد)", text):
            fields["جنسیت"] = "آقا"

        elif re.search(r"فقط\s*(?:خانم|زن)", text):
            fields["جنسیت"] = "خانم"

    # حقوق از متن
    if "حقوق" not in fields:
        for line in description_lines:
            if re.search(
                r"حقوق|دستمزد|درآمد|دریافتی|میانگین دریافتی",
                line
            ):
                if re.search(
                    r"\d.*(?:میلیون|تومان)|توافقی",
                    fa_to_en(line),
                    re.IGNORECASE
                ):
                    fields["حقوق"] = line
                    break

    # ساعت کاری
    if "ساعت کاری" not in fields:
        for line in description_lines:
            english_line = fa_to_en(line)

            # جلوگیری از اشتباه گرفتن حقوق و سن با ساعت
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

            time_pattern = (
                r"\b\d{1,2}(?::\d{2})?"
                r"\s*(?:صبح|ظهر|بعدازظهر|عصر)?"
                r"\s*(?:تا|الی|-)"
                r"\s*"
                r"\d{1,2}(?::\d{2})?"
            )

            if re.search(time_pattern, english_line):
                if (
                    "ساعت" in line
                    or "صبح" in line
                    or "عصر" in line
                    or "الی" in line
                    or ":" in line
                ):
                    fields["ساعت کاری"] = line
                    break

    return fields


def build_post(title, fields, description_lines, phones):
    output = []

    # عنوان اصلی
    output.append(f"# 🟢 {title}")

    # جلوگیری از تکرار عنوان
    job_title = fields.get("عنوان شغلی")

    if job_title and not same_title(title, job_title):
        output.append(
            f"🟢 عنوان شغلی: {job_title}"
        )

    # ترتیب نمایش اطلاعات
    field_order = [
        "جنسیت",
        "محدوده سنی",
        "سابقه کار",
        "نوع همکاری",
        "ساعت کاری",
        "حقوق",
        "پرداخت",
        "بیمه"
    ]

    for key in field_order:
        value = fields.get(key)

        if value:
            output.append(
                f"🟢 {key}: {value}"
            )

    # توضیحات
    if description_lines:
        output.append("")
        output.append("### 🟢 توضیحات")

        for line in description_lines:
            output.append(f"🟢 {line}")

    # شماره تماس
    if phones:
        output.append("")

        for phone in phones:
            output.append(f"📞 {phone}")

    # آیدی‌های ثابت کانال
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

    url = f"https://api.telegram.org/bot{token}/sendMessage"

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
    print("🌐 دریافت لیست آگهی‌ها...")

    headers = {
        "User-Agent": UA,
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,*/*;q=0.8"
        ),
        "Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://divar.ir/"
    }

    try:
        response = requests.get(
            JOB_URL,
            headers=headers,
            timeout=30
        )

        print(
            f"🌐 Jobs page: HTTP {response.status_code}"
        )

        if response.status_code != 200:
            return []

        html = response.text

    except Exception as e:
        print(f"❌ خطا در دریافت لیست: {e}")
        return []

    urls = []

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    candidates = []

    # لینک‌های معمولی
    for a in soup.find_all(
        "a",
        href=True
    ):
        candidates.append(a["href"])

    # لینک‌های داخل HTML
    candidates += re.findall(
        r'(?:https://divar\.ir)?/v/[^"\'<>\s]+',
        html
    )

    # نسخه escaped شده
    escaped = re.findall(
        r'(?:https?:)?\\/\\/divar\.ir\\/v\\/[^"\'<>\s]+',
        html
    )

    candidates += [
        item.replace("\\/", "/")
        for item in escaped
    ]

    for href in candidates:
        href = href.replace("\\/", "/")

        if href.startswith("/"):
            href = "https://divar.ir" + href

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
            get_ad_id(existing) == ad_id
            for existing in urls
        ):
            urls.append(href)

    print(
        f"📋 تعداد آگهی‌های صفحه: {len(urls)}"
    )

    return urls


def main():
    print("🚀 شروع ربات\n")

    seen = load_seen()

    print(
        f"📦 تعداد آگهی‌های قبلی: {len(seen)}\n"
    )

    listing_urls = get_listing_urls()

    new_ads = [
        url
        for url in listing_urls
        if get_ad_id(url) not in seen
    ]

    print(
        f"🆕 آگهی جدید پیدا شده: {len(new_ads)}"
    )

    sent_count = 0

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
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

                page.wait_for_timeout(1200)

                # اطلاعات ساختاریافته
                structured = extract_structured(page)

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

                # متن آگهی
                raw_text = get_ad_text(page)

                description = clean_description(
                    raw_text
                )

                # حذف عنوان تکراری از توضیحات
                description = [
                    line
                    for line in description
                    if line != title
                ]

                # استخراج شماره
                phones = extract_phones(
                    page,
                    raw_text
                )

                if phones:
                    print(
                        f"📞 شماره پیدا شد: {phones}"
                    )
                else:
                    print(
                        "📞 شماره تماس پیدا نشد."
                    )

                # استخراج فیلدها
                fields = extract_fields(
                    structured,
                    description
                )

                # ساخت متن نهایی
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

                # ارسال تلگرام
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
                    f"❌ خطا در آگهی {ad_id}: {e}"
                )

        browser.close()

    save_seen(seen)

    print(
        f"\n📨 تعداد آگهی ارسال‌شده: {sent_count}"
    )

    print(
        f"💾 {len(seen)} آگهی ذخیره شد."
    )

    print(
        "🏁 پایان اجرای ربات"
    )


if __name__ == "__main__":
    main()
