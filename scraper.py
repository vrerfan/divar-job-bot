import os
import json
import re
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = "8531717188"

SEEN_FILE = "seen_ads.json"

JOB_URL = "https://divar.ir/s/alborz-province/jobs"


def load_seen():
    if not os.path.exists(SEEN_FILE):
        return []

    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)


def get_listing_urls():
    urls = []

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        )
    }

    try:
        response = requests.get(
            JOB_URL,
            headers=headers,
            timeout=30
        )

        print(f"🌐 Jobs page: HTTP {response.status_code}")

        if response.status_code != 200:
            return []

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        for a in soup.find_all("a", href=True):
            href = a["href"]

            if "/v/" not in href:
                continue

            if href.startswith("/"):
                href = "https://divar.ir" + href

            if href not in urls:
                urls.append(href)

        print(f"📋 تعداد آگهی‌های صفحه: {len(urls)}")

        return urls

    except Exception as e:
        print(f"❌ خطا در دریافت لیست آگهی‌ها: {e}")
        return []


def get_ad_details(page, url):
    try:
        print(f"🔎 باز کردن آگهی: {url}")

        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=60000
        )

        page.wait_for_timeout(3000)

        fields = {}

        rows = page.locator(
            'div[data-testid="unexpandable-info-row"]'
        )

        count = rows.count()

        print(f"📊 تعداد فیلدهای ساختاریافته: {count}")

        for i in range(count):
            try:
                row = rows.nth(i)

                title = row.locator(
                    ".kt-unexpandable-row__title"
                ).inner_text().strip()

                value = row.locator(
                    ".kt-unexpandable-row__value"
                ).inner_text().strip()

                if title and value:
                    fields[title] = value

            except Exception as e:
                print(f"⚠️ خطا در خواندن فیلد {i}: {e}")

        # عنوان آگهی
        title = fields.get("عنوان شغلی", "")

        if not title:
            try:
                title = page.locator("h1").first.inner_text().strip()
            except Exception:
                title = ""

        # متن کامل صفحه
        try:
            body_text = page.locator("body").inner_text()
        except Exception:
            body_text = ""

        print(f"📌 عنوان: {title}")
        print(f"📋 فیلدهای ساختاریافته: {fields}")

        return {
            "title": title,
            "fields": fields,
            "description": body_text,
        }

    except Exception as e:
        print(f"❌ خطا در دریافت آگهی: {e}")

        return {
            "title": "",
            "fields": {},
            "description": "",
        }


def clean_text(text):
    if not text:
        return ""

    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_extra_fields(details):
    """
    بعضی آگهی‌های دیوار اطلاعات استخدامی را
    در unexpandable-info-row ندارند و فقط داخل متن صفحه نمایش می‌دهند.
    """

    fields = details["fields"].copy()
    text = details.get("description", "")

    lines = [
        clean_text(line)
        for line in text.splitlines()
        if clean_text(line)
    ]

    # کلمات و متن‌های غیرمرتبط که در body صفحه دیوار دیده می‌شوند
    ignored = {
        "برو به اطلاعات تماس",
        "انتخاب شهر",
        "دسته‌ها",
        "دیوار من",
        "چت و تماس",
        "پشتیبانی",
        "ثبت آگهی",
        "اطلاعات تماس",
        "چت",
        "تماس ناشناس",
        "زنگ خطرهای قبل از همکاری",
        "سایر ویژگی‌ها و امکانات",
        "وضعیت سربازی",
        "ساعت کاری",
        "توضیحات",
    }

    useful = []

    for line in lines:
        if line in ignored:
            continue

        if len(line) < 2:
            continue

        useful.append(line)

    # پیدا کردن اطلاعاتی که دیوار معمولاً در متن صفحه نشان می‌دهد
    for i, line in enumerate(useful):

        # سابقه
        if line == "سابقه" and i + 1 < len(useful):
            value = useful[i + 1]

            if "سابقه کار" not in fields:
                fields["سابقه کار"] = value

        # نوع همکاری
        if line in {
            "تمام وقت",
            "پاره وقت",
            "پروژه‌ای",
            "دورکاری",
            "تمام‌وقت",
            "پاره‌وقت",
        }:
            if "نوع همکاری" not in fields:
                fields["نوع همکاری"] = line

        # شیوه پرداخت
        if line in {
            "ماهانه",
            "هفتگی",
            "روزانه",
            "ساعتی",
            "توافقی",
            "پورسانتی",
        }:
            if "شیوهٔ پرداخت" not in fields:
                fields["شیوهٔ پرداخت"] = line

        # عنوان شغلی
        if line in {
            "فروشنده",
            "سالن کار و گارسون",
            "طراح سایت",
            "نیروی فنی و تولید",
            "پذیرش و اطلاعات",
            "باریستا",
        }:
            if "عنوان شغلی" not in fields:
                fields["عنوان شغلی"] = line

        # حقوق
        if (
            "میلیون تومان" in line
            or "تومان" in line
        ):
            if (
                "حقوق" not in fields
                and "دستمزد" not in fields
                and re.search(r"\d", line)
            ):
                fields["دستمزد"] = line

        # جنسیت
        if line in {
            "آقا",
            "خانم",
            "فرقی نمی‌کند",
            "فرقی نمی کند",
        }:
            if "جنسیت" not in fields:
                fields["جنسیت"] = line

    # سابقه با الگوهای رایج
    for line in useful:

        if re.search(
            r"(حداقل|حداکثر|کم‌تر از|کمتر از)\s*\d+\s*سال",
            line
        ):
            if "سابقه کار" not in fields:
                fields["سابقه کار"] = line

        # حقوق
        if (
            "میلیون تومان" in line
            and re.search(r"\d", line)
        ):
            if (
                "دستمزد" not in fields
                and "حقوق" not in fields
            ):
                fields["دستمزد"] = line

    return fields


def make_post(details):
    fields = extract_extra_fields(details)

    title = fields.get(
        "عنوان شغلی",
        details.get("title", "")
    )

    if not title:
        title = "استخدام نیروی کار"

    salary = fields.get(
        "دستمزد",
        fields.get("حقوق", "")
    )

    gender = fields.get("جنسیت", "")
    experience = fields.get("سابقه کار", "")
    cooperation = fields.get("نوع همکاری", "")
    payment = fields.get("شیوهٔ پرداخت", "")
    insurance = fields.get("بیمه", "")

    lines = []

    # عنوان اصلی
    headline = f"# 🟢 {title}"

    if salary:
        headline += f" | حقوق {salary}"

    lines.append(headline)
    lines.append("")

    # اطلاعات اصلی
    lines.append(
        f"🟢 عنوان شغلی: {title}"
    )

    if gender:
        lines.append(
            f"🟢 جنسیت: {gender}"
        )

    if experience:
        lines.append(
            f"🟢 سابقه کار: {experience}"
        )

    if cooperation:
        lines.append(
            f"🟢 نوع همکاری: {cooperation}"
        )

    if payment:
        lines.append(
            f"🟢 پرداخت: {payment}"
        )

    if salary:
        lines.append(
            f"🟢 حقوق: {salary}"
        )

    if insurance:
        lines.append(
            f"🟢 بیمه: {insurance}"
        )

    lines.append("")

    # توضیحات واقعی آگهی
    description = details.get(
        "description",
        ""
    )

    raw_lines = [
        clean_text(line)
        for line in description.splitlines()
        if clean_text(line)
    ]

    # مواردی که نباید داخل توضیحات بیایند
    ignored_lines = {
        "برو به اطلاعات تماس",
        "انتخاب شهر",
        "دسته‌ها",
        "دیوار من",
        "چت و تماس",
        "پشتیبانی",
        "ثبت آگهی",
        "اطلاعات تماس",
        "چت",
        "تماس ناشناس",
        "زنگ خطرهای قبل از همکاری",
        "سایر ویژگی‌ها و امکانات",
        "وضعیت سربازی",
        "ساعت کاری",
        "توضیحات",
        "سابقه",
        "ماهانه",
        "هفتگی",
        "روزانه",
        "ساعتی",
        "توافقی",
        "تمام وقت",
        "تمام‌وقت",
        "پاره وقت",
        "پاره‌وقت",
        "آقا",
        "خانم",
        "فرقی نمی‌کند",
        "فرقی نمی کند",
    }

    description_lines = []

    for line in raw_lines:

        if line == title:
            continue

        if line in fields:
            continue

        if line in fields.values():
            continue

        if line in ignored_lines:
            continue

        # حذف دسته‌بندی‌ها و مسیرهای منوی دیوار
        if line.startswith("استخدام و کاریابی"):
            continue

        if line.startswith("استخدام "):
            continue

        # حذف متن‌های هشدار خود دیوار
        if "پیش از استخدام پول ندهید" in line:
            continue

        if "پرداخت شما ممکن است" in line:
            continue

        # حذف زمان/مکان آگهی
        if re.search(
            r"(دقایقی پیش|امروز|دیروز|\d+\s*روز پیش)\s+در\s+",
            line
        ):
            continue

        # جلوگیری از تکرار
        if line in description_lines:
            continue

        description_lines.append(line)

    # فقط چند خط اول توضیحات واقعی
    if description_lines:

        lines.append("### 🟢 توضیحات")

        for line in description_lines[:12]:
            lines.append(
                f"🟢 {line}"
            )

        lines.append("")

    # آیدی‌های ثابت
    lines.append("کانال تلگرام")
    lines.append("@karyabi_alborzi")
    lines.append("")

    lines.append("جهت ثبت آگهی")
    lines.append("@Karyabi_karaji")

    return "\n".join(lines)


def send_telegram(text):
    """
    ارسال مستقیم از Telegram Bot API
    بدون استفاده از Bot.send_message async
    """

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

    response = requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": text,
        },
        timeout=30,
    )

    if response.status_code != 200:
        raise Exception(
            f"Telegram API error: "
            f"{response.status_code} - "
            f"{response.text}"
        )

    result = response.json()

    if not result.get("ok"):
        raise Exception(
            f"Telegram API error: {result}"
        )

    print(
        "📨 پیام با موفقیت به تلگرام ارسال شد."
    )


def main():
    print("🚀 شروع ربات")

    seen = load_seen()

    print(
        f"📦 تعداد آگهی‌های قبلی: {len(seen)}"
    )

    # دریافت لیست استخدام استان البرز
    listing_urls = get_listing_urls()

    if not listing_urls:
        print(
            "❌ هیچ آگهی‌ای پیدا نشد."
        )
        return

    # پیدا کردن ۱۰ آگهی جدید
    new_ads = []

    for url in listing_urls:

        match = re.search(
            r"/v/([^/?#]+)",
            url
        )

        if not match:
            continue

        ad_id = match.group(1)

        if ad_id in seen:
            continue

        new_ads.append(
            (ad_id, url)
        )

        if len(new_ads) >= 10:
            break

    print(
        f"🆕 آگهی جدید پیدا شده: "
        f"{len(new_ads)}"
    )

    if not new_ads:
        print(
            "ℹ️ آگهی جدیدی برای ارسال وجود ندارد."
        )
        return

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page(
            viewport={
                "width": 1366,
                "height": 900
            },
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )

        for ad_id, url in new_ads:

            details = get_ad_details(
                page,
                url
            )

            # اگر هیچ اطلاعاتی دریافت نشده،
            # آگهی seen نمی‌شود.
            if (
                not details["fields"]
                and not details["description"]
            ):
                print(
                    f"⚠️ اطلاعات آگهی "
                    f"{ad_id} دریافت نشد."
                )
                continue

            post = make_post(details)

            print(
                "\n=============================="
            )

            print(post)

            print(
                "==============================\n"
            )

            try:
                send_telegram(post)

                print(
                    f"✅ ارسال شد: {ad_id}"
                )

                # فقط بعد از ارسال موفق
                # آگهی seen می‌شود.
                if ad_id not in seen:
                    seen.append(ad_id)

                save_seen(seen)

            except Exception as e:
                print(
                    f"❌ خطا در ارسال تلگرام: {e}"
                )

        browser.close()

    save_seen(seen)

    print("🏁 پایان اجرای ربات")


if __name__ == "__main__":
    main()
