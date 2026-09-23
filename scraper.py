import os
import json
import re
import requests
from bs4 import BeautifulSoup
from telegram import Bot
from playwright.sync_api import sync_playwright


BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = "8531717188"

SEEN_FILE = "seen_ads.json"

CITIES = [
    "karaj",
    "fardis",
    "nazarabad",
    "hashtgerd",
    "taleghan",
    "eshtehard",
    "savojbolagh",
    "kordan",
    "mahdasht",
    "mohammadshahr",
    "meshkindasht",
]


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

    for city in CITIES:
        url = f"https://divar.ir/s/{city}/employment-business"

        try:
            response = requests.get(url, headers=headers, timeout=30)

            if response.status_code != 200:
                print(f"❌ {city}: HTTP {response.status_code}")
                continue

            soup = BeautifulSoup(response.text, "html.parser")

            for a in soup.find_all("a", href=True):
                href = a["href"]

                if "/v/" in href:
                    if href.startswith("/"):
                        href = "https://divar.ir" + href

                    if href not in urls:
                        urls.append(href)

            print(f"✅ {city}: {len(urls)} آگهی پیدا شد")

        except Exception as e:
            print(f"❌ خطا در {city}: {e}")

    return urls


def get_ad_details(page, url):
    try:
        print(f"🔎 باز کردن: {url}")

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

        for i in range(count):
            row = rows.nth(i)

            title = row.locator(
                ".kt-unexpandable-row__title"
            ).inner_text().strip()

            value = row.locator(
                ".kt-unexpandable-row__value"
            ).inner_text().strip()

            if title and value:
                fields[title] = value

        # پیدا کردن متن توضیحات از DOM
        body_text = page.locator("body").inner_text()

        # عنوان آگهی
        title = fields.get("عنوان شغلی", "")

        if not title:
            try:
                title = page.locator("h1").first.inner_text().strip()
            except Exception:
                title = ""

        print(f"📌 عنوان: {title}")
        print(f"📋 فیلدها: {fields}")

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

    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def make_post(details):
    fields = details["fields"]
    title = details["title"]

    if not title:
        title = "استخدام نیروی کار"

    # اطلاعات ساختاریافته دیوار
    salary = fields.get("دستمزد", "")
    gender = fields.get("جنسیت", "")
    experience = fields.get("سابقه کار", "")
    cooperation = fields.get("نوع همکاری", "")
    payment = fields.get("شیوهٔ پرداخت", "")
    insurance = fields.get("بیمه", "")

    lines = []

    # عنوان
    headline = f"# 🟢 {title}"

    if salary:
        headline += f" | حقوق {salary}"

    lines.append(headline)
    lines.append("")

    # فیلدها
    lines.append(f"🟢 عنوان شغلی: {title}")

    if gender:
        lines.append(f"🟢 جنسیت: {gender}")

    if experience:
        lines.append(f"🟢 سابقه کار: {experience}")

    if cooperation:
        lines.append(f"🟢 نوع همکاری: {cooperation}")

    if payment:
        lines.append(f"🟢 شیوه پرداخت: {payment}")

    if insurance:
        lines.append(f"🟢 بیمه: {insurance}")

    if salary:
        lines.append(f"🟢 حقوق: {salary}")

    lines.append("")

    # توضیحات
    description = details.get("description", "")

    # حذف بخش‌های غیرضروری از متن body
    description_lines = []

    for line in description.splitlines():
        line = line.strip()

        if not line:
            continue

        if line in fields:
            continue

        if line in fields.values():
            continue

        if len(line) < 2:
            continue

        description_lines.append(line)

    # فقط بخش‌هایی که احتمالاً توضیح آگهی هستند
    useful_description = []

    for line in description_lines:
        if line == title:
            continue

        if line.startswith("شیوهٔ پرداخت"):
            continue

        if line.startswith("عنوان شغلی"):
            continue

        if line.startswith("دستمزد"):
            continue

        if line.startswith("جنسیت"):
            continue

        if line.startswith("بیمه"):
            continue

        if line.startswith("سابقه کار"):
            continue

        if line.startswith("نوع همکاری"):
            continue

        useful_description.append(line)

    # جلوگیری از متن‌های خیلی طولانی و بی‌ربط
    if useful_description:
        lines.append("### 🟢 توضیحات")

        for line in useful_description[:20]:
            lines.append(f"🟢 {clean_text(line)}")

        lines.append("")

    # آیدی‌های ثابت
    lines.append("کانال تلگرام")
    lines.append("@karyabi_alborzi")
    lines.append("")
    lines.append("جهت ثبت آگهی")
    lines.append("@Karyabi_karaji")

    return "\n".join(lines)


def send_telegram(text):
    bot = Bot(token=BOT_TOKEN)

    bot.send_message(
        chat_id=CHAT_ID,
        text=text
    )


def main():
    print("🚀 شروع ربات")

    seen = load_seen()

    print(f"📦 تعداد آگهی‌های قبلی: {len(seen)}")

    listing_urls = get_listing_urls()

    if not listing_urls:
        print("❌ هیچ آگهی‌ای پیدا نشد.")
        return

    new_ads = []

    for url in listing_urls:
        match = re.search(r"/v/([^/?#]+)", url)

        if not match:
            continue

        ad_id = match.group(1)

        if ad_id in seen:
            continue

        new_ads.append((ad_id, url))

        if len(new_ads) >= 10:
            break

    print(f"🆕 آگهی جدید پیدا شده: {len(new_ads)}")

    if not new_ads:
        print("ℹ️ آگهی جدیدی برای ارسال وجود ندارد.")
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

            details = get_ad_details(page, url)

            # اگر صفحه اطلاعات واقعی نداد،
            # آگهی را seen نکن تا در اجرای بعدی دوباره امتحان شود.
            if not details["fields"] and not details["description"]:
                print(f"⚠️ اطلاعات آگهی {ad_id} دریافت نشد.")
                continue

            post = make_post(details)

            print("\n==============================")
            print(post)
            print("==============================\n")

            try:
                send_telegram(post)

                print(f"✅ ارسال شد: {ad_id}")

                seen.append(ad_id)
                save_seen(seen)

            except Exception as e:
                print(f"❌ خطا در ارسال تلگرام: {e}")

        browser.close()

    save_seen(seen)

    print("🏁 پایان اجرای ربات")


if __name__ == "__main__":
    main()
