import time
from playwright.sync_api import sync_playwright

def test_kiosk():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            headless=True,
            args=["--no-sandbox", "--disable-gpu"]
        )
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        
        print("1. Navigating to http://localhost:8080/display...")
        page.goto("http://localhost:8080/display", wait_until="networkidle")
        page.wait_for_timeout(2000)
        
        # Verify Clock
        clock_text = page.locator("#live-clock").inner_text()
        date_text = page.locator("#live-date").inner_text()
        print(f"Clock: {clock_text}, Date: {date_text}")
        assert clock_text != "--:--:--", "Clock should be updated"
        assert date_text != "Loading...", "Date should be updated"
        
        # Verify Pinned Notes
        pinned_count = page.locator("#pinned-count").inner_text()
        pinned_list_text = page.locator("#pinned-list").inner_text()
        print(f"Pinned Count: {pinned_count}")
        print(f"Pinned Notes Text:\n{pinned_list_text}")
        assert "Sprint Board" in pinned_list_text, "Sprint Board should be in pinned notes"
        
        # Verify Tasks Due
        tasks_count = page.locator("#tasks-count").inner_text()
        tasks_list_text = page.locator("#tasks-list").inner_text()
        print(f"Tasks Count: {tasks_count}")
        print(f"Tasks Due Text:\n{tasks_list_text}")
        assert "Implement OAuth2 flow" in tasks_list_text, "Task should be in tasks due"
        
        # Verify Habits
        habits_count = page.locator("#habits-count").inner_text()
        habits_list_text = page.locator("#habits-list").inner_text()
        print(f"Habits Count: {habits_count}")
        print(f"Habits List Text:\n{habits_list_text}")
        assert "Gym & Fitness" in habits_list_text, "Gym & Fitness should be listed"
        assert "Meditation & Breathwork" in habits_list_text, "Meditation should be listed"
        
        # Take initial screenshot
        page.screenshot(path="test_screenshots/01_tablet_kiosk_initial.png")
        print("Captured 01_tablet_kiosk_initial.png")
        
        # Test 1-Tap Check-in on habit card
        # Locate the Gym & Fitness card
        gym_card = page.locator(".habit-card", has_text="Gym & Fitness")
        print("Tapping Gym & Fitness card...")
        gym_card.click()
        page.wait_for_timeout(1500)
        
        # Verify updated count and card status
        updated_habits_count = page.locator("#habits-count").inner_text()
        print(f"Updated Habits Count: {updated_habits_count}")
        assert "1/6" in updated_habits_count or "Done" in gym_card.inner_text(), "Gym & Fitness should be marked done"
        
        # Tap second habit: Meditation & Breathwork
        meditation_card = page.locator(".habit-card", has_text="Meditation & Breathwork")
        print("Tapping Meditation & Breathwork card...")
        meditation_card.click()
        page.wait_for_timeout(1500)
        
        updated_habits_count2 = page.locator("#habits-count").inner_text()
        print(f"Updated Habits Count after 2nd tap: {updated_habits_count2}")
        
        # Take updated screenshot
        page.screenshot(path="test_screenshots/02_tablet_kiosk_checked.png")
        print("Captured 02_tablet_kiosk_checked.png")
        
        browser.close()
        print("Kiosk test completed successfully!")

if __name__ == "__main__":
    test_kiosk()
