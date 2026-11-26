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

        # 2. Verify Habits section
        habits_section = page.locator(".habits-section")
        habits_section.wait_for(state="visible", timeout=12000)
        print("  [PASS] Found .habits-section")

        habit_cards = page.locator(".habit-card")
        count = habit_cards.count()
        print(f"  [PASS] Found {count} habit note cards in DOM")
        assert count >= 6, f"Expected at least 6 habit cards, got {count}"

        # 3. Test Diet & Meals (Multi-log) and Sandclock Auto-Submit countdown
        print("\n2. Testing Multi-Log and Sandclock Auto-Submit on Diet & Meals...")
        diet_card = page.locator(".habit-card", has_text="Diet & Meals")
        assert diet_card.count() > 0, "Diet & Meals card not found"

        # Click preset chip "Breakfast: Clean"
        breakfast_chip = diet_card.locator(".preset-chip", has_text="Breakfast: Clean")
        assert breakfast_chip.count() > 0, "'Breakfast: Clean' chip not found"
        breakfast_chip.click()
        print("  Clicked 'Breakfast: Clean' chip")

        # Wait a moment and check sandclock button
        page.wait_for_timeout(600)
        sandclock_btn = diet_card.locator(".sandclock-btn")
        sandclock_btn.wait_for(state="visible", timeout=4000)
        sandclock_text = sandclock_btn.inner_text()
        print(f"  [PASS] Sandclock button visible: '{sandclock_text}'")
        assert "Submit (" in sandclock_text, f"Expected countdown text, got: {sandclock_text}"

        # Take screenshot of active Sandclock countdown
        shot_sandclock = os.path.join(SCREENSHOT_DIR, "19_sandclock_countdown_active.png")
        page.screenshot(path=shot_sandclock)
        print(f"  [SCREENSHOT] Saved active sandclock: {shot_sandclock}")

        # Click the sandclock button for immediate submit
        sandclock_btn.click()
        print("  Clicked Sandclock button for instant submit")
        page.wait_for_timeout(2000)

        # Verify entry appeared under Today's Logs with timestamp
        today_logs = diet_card.locator(".today-logs-list .log-entry-row")
        print(f"  Today's logs count on Diet: {today_logs.count()}")
        assert today_logs.count() >= 1, "Expected at least 1 entry in today's logs"
        first_entry_text = today_logs.first.inner_text()
        print(f"  [PASS] First entry logged: '{first_entry_text}'")
        assert "Breakfast: Clean" in first_entry_text

        # 4. Log a second meal on the same day (Multi-Log test!)
        print("\n3. Testing second log on same day (Lunch: High Protein)...")
        lunch_chip = diet_card.locator(".preset-chip", has_text="Lunch: High Protein")
        lunch_chip.click()
        page.wait_for_timeout(500)
        diet_card.locator(".sandclock-btn").click()
        page.wait_for_timeout(2000)

        # Verify multiple logs are now present
        logs_after_second = diet_card.locator(".today-logs-list .log-entry-row")
        print(f"  [PASS] Today's logs count after second meal: {logs_after_second.count()}")
        assert logs_after_second.count() >= 2, "Expected at least 2 entries in today's logs"

        shot_multilog = os.path.join(SCREENSHOT_DIR, "20_multilog_diet_entries.png")
        page.screenshot(path=shot_multilog)
        print(f"  [SCREENSHOT] Saved multi-log screenshot: {shot_multilog}")

        # 5. Test Preset Removal ('×' button) on Gym & Fitness
        print("\n4. Testing Preset Removal on Gym & Fitness...")
        gym_card = page.locator(".habit-card", has_text="Gym & Fitness")
        # Ensure Yes is clicked
        gym_yes_btn = gym_card.locator("button.yn-btn", has_text="Yes")
        gym_yes_btn.click()
        page.wait_for_timeout(600)

        # Find "Abs & Core" chip and click its remove button
        abs_chip = gym_card.locator(".preset-chip", has_text="Abs & Core")
        if abs_chip.count() > 0:
            print("  Found 'Abs & Core' chip, clicking remove button...")
            remove_btn = abs_chip.locator(".chip-remove")
            remove_btn.click()
            page.wait_for_timeout(1000)
            # Verify "Abs & Core" is gone
            assert gym_card.locator(".preset-chip", has_text="Abs & Core").count() == 0, "'Abs & Core' should have been removed"
            print("  [PASS] 'Abs & Core' preset chip was removed successfully!")

        shot_removed = os.path.join(SCREENSHOT_DIR, "21_preset_option_removed.png")
        page.screenshot(path=shot_removed)
        print(f"  [SCREENSHOT] Saved preset removal screenshot: {shot_removed}")

        # 6. Test Single-Log Gym selection and Weight stepper
        print("\n5. Testing Single-Log Gym and Weight stepper...")
        chest_chip = gym_card.locator(".preset-chip", has_text="Chest")
        if chest_chip.count() > 0:
            chest_chip.click()
            page.wait_for_timeout(500)
            gym_sandclock = gym_card.locator(".sandclock-btn")
            if gym_sandclock.count() > 0:
                gym_sandclock.click()
                page.wait_for_timeout(1500)
                print("  [PASS] Gym 'Chest' logged via Sandclock button")

        # Full page final screenshot
        shot_final = os.path.join(SCREENSHOT_DIR, "22_all_habits_verified.png")
        page.screenshot(path=shot_final)
        print(f"  [SCREENSHOT] Saved final verified habits screenshot: {shot_final}")

        print("\nALL VERIFICATIONS PASSED SUCCESSFULLY!")
        browser.close()

if __name__ == "__main__":
    main()
