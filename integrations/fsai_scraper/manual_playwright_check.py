
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage"
        ]
    )

    page = browser.new_page()
    response = page.goto(
        "https://example.com",
        wait_until="domcontentloaded",
        timeout=60000
    )

    print("SUCCESS")
    print("HTTP status:", response.status if response else None)
    print("Title:", page.title())

    browser.close()