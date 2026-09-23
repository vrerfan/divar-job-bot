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


def get_real_description(page):
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

        if line in stop_exact:
            break

        if re.fullmatch(
            r"تصویر\s+\d+\s+از\s+\d+",
            line
        ):
            break

        if line.startswith(
            "یادداشت تنها برای شما"
        ):
            break

        if line in {
            "چت",
            "تماس",
            "چت و تماس",
            "پشتیبانی",
            "دیوار من",
            "دسته‌ها",
            "انتخاب شهر",
            "برو به اطلاعات تماس",
            "اشتراک‌گذاری آگهی",
        }:
            continue

        result.append(line)

    bad_lines = {
        "یادداشت تنها برای شما قابل دیدن است و پس از حذف آگهی، پاک خواهد شد.",
    }

    result = [
        x for x in result
        if x not in bad_lines
    ]

    clean = []

    for line in result:
        if not clean or clean[-1] != line:
            clean.append(line)

    return clean


def extract_fields(structured, description_lines):
    fields = {}

    mapping = {
        "جنسیت": "جنسیت",
        "دستمزد": "حقوق",
        "شیوهٔ پرداخت": "پرداخت",
        "بیمه": "بیمه",
        "ساعت کاری": "ساعت کاری",
    }

    for key, target in mapping.items():

        value = structured.get(key)

        if value:
            fields[target] = value

    text = "\n".join(description_lines)

    if "نوع همکاری" not in fields:

        cooperation_patterns = [
            ("تمام‌وقت", r"تمام\s*وقت"),
            ("پاره‌وقت", r"پاره\s*وقت"),
            ("کارآموزی", r"کارآموزی"),
            ("دورکاری", r"دورکاری"),
            ("پروژه‌ای", r"پروژه\s*ای"),
            ("ساعتی", r"ساعتی"),
        ]

        for value, pattern in cooperation_patterns:

            if re.search(pattern, text):
                fields["نوع همکاری"] = value
                break

    if "سابقه کار" not in fields:

        patterns = [
            r"بدون نیاز به سابقه",
            r"بدون سابقه",
            r"حداقل\s*[\d۰-۹]+\s*سال سابقه",
            r"[\d۰-۹]+\s*سال سابقه",
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                text
            )

            if match:
                fields["سابقه کار"] = match.group(0)
                break

    english_text = fa_to_en(text)

    age_patterns = [
        r"(?:سن|سنین|محدوده سنی|شرایط سنی)"
        r"[^.\n]{0,40}"
        r"(\d{1,2})\s*"
        r"(?:تا|الی|-)\s*"
        r"(\d{1,2})\s*سال",

        r"حداقل سن\s*(\d{1,2})\s*سال",

        r"حداکثر سن\s*(\d{1,2})\s*سال",
    ]

    for pattern in age_patterns:

        match = re.search(
            pattern,
            english_text
        )

        if not match:
            continue

        if len(match.groups()) == 2:

            fields["محدوده سنی"] = en_to_fa(
                f"{match.group(1)} تا "
                f"{match.group(2)} سال"
            )

        else:

            original = match.group(0)

            fields["محدوده سنی"] = en_to_fa(
                original
            )

        break

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

    if "ساعت کاری" not in fields:

        for line in description_lines:

            if re.search(
                r"ناهار|شام|استراحت",
                line
            ):
                continue

            english_line = fa_to_en(line)

            pattern = (
                r"(?<!\d)"
                r"\d{1,2}"
                r"(?:[:]\d{2})?"
                r"\s*"
                r"(?:صبح|ظهر|عصر|بعدازظهر)?"
                r"\s*"
                r"(?:تا|الی|-)"
                r"\s*"
                r"\d{1,2}"
                r"(?:[:]\d{2})?"
                r"(?:\s*(?:صبح|ظهر|عصر|بعدازظهر))?"
                r"(?!\d)"
            )

            match = re.search(
                pattern,
                english_line
            )

            if match:

                if any(
                    x in line
                    for x in [
                        "ساعت کاری",
                        "ساعت",
                        "شیفت",
                        "تایم",
                    ]
                ):
                    fields["ساعت کاری"] = line
                    break

    return fields


def build_post(
    title,
    fields,
    description_lines,
    ad_url
):
    output = []

    output.append(
        f"# 🟢 {title}"
    )

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

            if key == "حقوق":

                value = re.sub(
                    r"^حقوق\s*[:：]?\s*",
                    "",
                    value
                ).strip()

            output.append(
                f"🟢 {key}: {value}"
            )

    if description_lines:

        output.append("")
        output.append(
            "### 🟢 توضیحات"
        )

        for line in description_lines:

            if fields.get("حقوق"):

                normalized_line = normalize_text(
                    line
                )

                normalized_salary = normalize_text(
                    fields["حقوق"]
                )

                if normalized_line == normalized_salary:
                    continue

            output.append(
                f"🟢 {line}"
            )

    output.extend([
        "",
        "کانال روبیکا",
        "@karyabi_alborzi",
        "",
        "جهت ثبت آگهی",
        "@Karyabi_karaji",
        "",
        "🔗 لینک آگهی:",
        ad_url
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

                fields = extract_fields(
                    structured,
                    description
                )

                post = build_post(
                    title,
                    fields,
                    description,
                    url
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
