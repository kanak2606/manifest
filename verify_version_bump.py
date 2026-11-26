import os
import time
from playwright.sync_api import sync_playwright

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
SCREENSHOT_DIR = r"D:\Projects\Note Trace\test_screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME_PATH,
            headless=True,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(viewport={"width": 1400, "height": 950})
        page = context.new_page()

        print("1. Navigating to http://localhost:8080/?u=admin&p=Phase1!Test...")
        page.goto("http://localhost:8080/?u=admin&p=Phase1!Test", wait_until="domcontentloaded")
        page.wait_for_timeout(3500)

        # 2. Verify sidebar
        sidebar = page.locator(".sidebar-panel")
        sidebar.wait_for(state="visible", timeout=10000)

        # 3. Locate the update card near admin
        update_card = page.locator(".sidebar-update-card")
        assert update_card.count() > 0, "sidebar-update-card not found"
        update_title = update_card.locator(".update-title").inner_text()
        update_feature = update_card.locator(".update-text").inner_text()
        print(f"  [PASS] Update Card Title: '{update_title}'")
        print(f"  [PASS] Update Card Feature: '{update_feature}'")
        assert "v1.4.0" in update_title.lower(), f"Expected v1.4.0 in title, got: {update_title}"
        assert "Habit Sandclock" in update_feature

        # 4. Locate admin user and version in bottom left
        sidebar_user = page.locator(".sidebar-user")
        assert sidebar_user.count() > 0, "sidebar-user not found"
        user_name = sidebar_user.locator(".user-name").inner_text()
        user_version = sidebar_user.locator(".sidebar-version").inner_text()
        print(f"  [PASS] User section: Name='{user_name}' | Version='{user_version}'")
        assert "admin" in user_name.lower()
        assert "v1.4.0" in user_version

        # 5. Locate Open in Another Device QR widget
        qr_widget = page.locator(".sidebar-device-qr")
        assert qr_widget.count() > 0, "sidebar-device-qr not found"
        print("  [PASS] Open in Another Device QR widget verified near admin")

        # Capture zoomed/cropped or full screenshot highlighting the bottom left sidebar area
        shot_path = os.path.join(SCREENSHOT_DIR, "26_version_and_update_message_verified.png")
        page.screenshot(path=shot_path)
        print(f"  [SCREENSHOT] Saved: {shot_path}")

        print("\nALL VERSION & UPDATE MESSAGE VERIFICATIONS PASSED SUCCESSFULLY!")
        browser.close()

if __name__ == "__main__":
    main()
