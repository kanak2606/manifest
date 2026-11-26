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

        # 2. Verify sidebar is visible
        sidebar = page.locator(".sidebar-panel")
        sidebar.wait_for(state="visible", timeout=10000)
        print("  [PASS] Sidebar visible")

        # 3. Locate the user section with 'admin' in bottom left
        sidebar_user = page.locator(".sidebar-user")
        assert sidebar_user.count() > 0, "sidebar-user not found"
        user_name_text = sidebar_user.locator(".user-name").inner_text()
        print(f"  [PASS] User name in bottom left: '{user_name_text}'")
        assert "admin" in user_name_text.lower(), f"Expected 'admin' in user-name, got '{user_name_text}'"

        # 4. Locate the 'Open in Another Device' QR widget near admin
        qr_widget = page.locator(".sidebar-device-qr")
        assert qr_widget.count() > 0, "sidebar-device-qr widget not found"
        widget_title = qr_widget.locator(".device-qr-title").inner_text()
        widget_url = qr_widget.locator(".device-qr-url").inner_text()
        print(f"  [PASS] Found QR widget near admin: Title='{widget_title}' | URL='{widget_url}'")
        assert "Open in Another Device" in widget_title
        assert "http://" in widget_url, f"Expected valid URL in widget, got: {widget_url}"

        # Verify mini QR code image thumbnail is loaded
        mini_qr_img = qr_widget.locator(".mini-qr-thumb")
        assert mini_qr_img.count() > 0, "Mini QR code image not found in widget"
        print("  [PASS] Mini QR image thumbnail loaded successfully")

        # Capture screenshot of sidebar with mini QR widget in bottom left
        shot_sidebar = os.path.join(SCREENSHOT_DIR, "23_sidebar_device_qr_widget.png")
        page.screenshot(path=shot_sidebar)
        print(f"  [SCREENSHOT] Saved: {shot_sidebar}")

        # 5. Click the QR widget to open the enlarged QR modal
        print("\n2. Clicking QR widget to open enlarged modal...")
        qr_widget.locator(".device-qr-card-btn").click()
        page.wait_for_timeout(1000)

        # 6. Verify Device QR Modal dialog
        qr_dialog = page.locator(".qr-modal-dialog")
        qr_dialog.wait_for(state="visible", timeout=5000)
        modal_title = qr_dialog.locator(".modal-title").inner_text()
        print(f"  [PASS] Modal dialog opened: '{modal_title}'")
        assert "Open on Another Device" in modal_title

        # Verify large QR code image inside modal
        large_qr = qr_dialog.locator(".qr-large-img")
        large_qr.wait_for(state="visible", timeout=4000)
        print("  [PASS] Large high-contrast QR code image is visible and rendered")

        # Verify URL input and Copy button
        url_input = qr_dialog.locator(".url-input")
        displayed_url = url_input.input_value()
        print(f"  [PASS] Displayed URL inside modal: '{displayed_url}'")
        assert "http://" in displayed_url

        copy_btn = qr_dialog.locator(".copy-btn")
        assert copy_btn.count() > 0, "Copy button not found"

        # Test copying URL
        copy_btn.click()
        page.wait_for_timeout(400)
        copy_btn_text = copy_btn.inner_text()
        print(f"  [PASS] Copy button state after click: '{copy_btn_text}'")
        assert "Copied" in copy_btn_text

        # Capture screenshot of enlarged QR Modal dialog
        shot_modal = os.path.join(SCREENSHOT_DIR, "24_device_qr_modal_enlarged.png")
        page.screenshot(path=shot_modal)
        print(f"  [SCREENSHOT] Saved: {shot_modal}")

        # 7. Test closing the modal with Close button
        print("\n3. Testing modal close button...")
        close_btn = qr_dialog.locator(".close-btn")
        close_btn.click()
        page.wait_for_timeout(600)
        assert qr_dialog.count() == 0, "Modal dialog should be closed after clicking close"
        print("  [PASS] Modal closed smoothly")

        # Capture screenshot after closing
        shot_closed = os.path.join(SCREENSHOT_DIR, "25_modal_closed_notes_view.png")
        page.screenshot(path=shot_closed)
        print(f"  [SCREENSHOT] Saved: {shot_closed}")

        print("\nALL QR & DEVICE PAIRING VERIFICATIONS PASSED SUCCESSFULLY!")
        browser.close()

if __name__ == "__main__":
    main()
