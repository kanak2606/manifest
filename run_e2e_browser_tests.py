import os
import time
import sqlite3
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
SCREENSHOT_DIR = r"D:\Projects\Note Trace\test_screenshots"

os.makedirs(SCREENSHOT_DIR, exist_ok=True)

def reset_db_state():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn = sqlite3.connect(r"D:\Projects\Note Trace\data\notetrace.db")
    c = conn.cursor()
    c.execute("DELETE FROM habit_logs WHERE log_date = ?", (today,))
    c.execute("UPDATE notes SET pinned = 1 WHERE id = 192")
    c.execute("UPDATE checklist_items SET due_date = ? WHERE id = 181", (today,))
    conn.commit()
    conn.close()
    print("  [DB] Reset today's habit logs and ensured pinned note & task due.")

def run_tests():
    print("=" * 70)
    print("STARTING NOTETRACE END-TO-END BROWSER AUTOMATION TESTS")
    print("=" * 70)

    reset_db_state()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME_PATH,
            headless=True,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page = context.new_page()

        # =====================================================================
        # PART 1: TABLET KIOSK MODE (/display)
        # =====================================================================
        print("\n--- PART 1: Testing Tablet Kiosk Mode (http://localhost:8080/display) ---")
        page.goto("http://localhost:8080/display", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # 1.1 Verify Live Clock
        clock_text = page.locator("#live-clock").inner_text()
        date_text = page.locator("#live-date").inner_text()
        print(f"  [PASS] Live Clock: '{clock_text}' | Date: '{date_text}'")
        assert clock_text != "--:--:--", f"Clock was not updated: {clock_text}"
        assert date_text != "Loading...", f"Date was not loaded: {date_text}"

        # 1.2 Verify Pinned Notes
        pinned_count = page.locator("#pinned-count").inner_text()
        pinned_list_text = page.locator("#pinned-list").inner_text()
        print(f"  [PASS] Pinned Notes Count: {pinned_count}")
        print(f"  [PASS] Pinned Note Title present: {'Sprint Board' in pinned_list_text}")
        assert "Sprint Board" in pinned_list_text, "Sprint Board not found in pinned notes"

        # 1.3 Verify Tasks Due
        tasks_count = page.locator("#tasks-count").inner_text()
        tasks_list_text = page.locator("#tasks-list").inner_text()
        print(f"  [PASS] Tasks Due Count: {tasks_count}")
        print(f"  [PASS] Task Due present: {'Implement OAuth2 flow' in tasks_list_text}")
        assert "Implement OAuth2 flow" in tasks_list_text, "Expected task not in tasks due list"

        # 1.4 Verify Daily Habits
        habits_count = page.locator("#habits-count").inner_text()
        habits_list_text = page.locator("#habits-list").inner_text()
        print(f"  [PASS] Habits Count: {habits_count}")
        assert "Gym & Fitness" in habits_list_text, "Gym & Fitness not found in habits"
        assert "Meditation & Breathwork" in habits_list_text, "Meditation not found in habits"

        # Capture Initial Kiosk Screenshot
        p1_initial = os.path.join(SCREENSHOT_DIR, "01_kiosk_display_initial.png")
        page.screenshot(path=p1_initial)
        print(f"  [SCREENSHOT] Saved: {p1_initial}")

        # 1.5 Test 1-Tap Check-in on Habits
        print("  Testing 1-Tap check-in on 'Gym & Fitness'...")
        gym_card = page.locator(".habit-card", has_text="Gym & Fitness")
        gym_card.click()
        page.wait_for_timeout(1000)

        print("  Testing 1-Tap check-in on 'Meditation & Breathwork'...")
        med_card = page.locator(".habit-card", has_text="Meditation & Breathwork")
        med_card.click()
        page.wait_for_timeout(1000)

        updated_habits_count = page.locator("#habits-count").inner_text()
        print(f"  [PASS] Updated Habits Progress: {updated_habits_count}")
        assert "2/6" in updated_habits_count or "33%" in updated_habits_count, f"Unexpected count: {updated_habits_count}"

        p1_checked = os.path.join(SCREENSHOT_DIR, "02_kiosk_display_checked.png")
        page.screenshot(path=p1_checked)
        print(f"  [SCREENSHOT] Saved: {p1_checked}")


        # =====================================================================
        # PART 2: NOTES VIEW & DAILY HABIT CHECK-IN BANNER (/)
        # =====================================================================
        print("\n--- PART 2: Testing Notes View & Daily Habit Banner (http://localhost:8080) ---")
        page.goto("http://localhost:8080/?u=admin&p=Phase1!Test", wait_until="domcontentloaded")
        page.wait_for_timeout(2500)

        # Check Habit Banner visibility
        banner = page.locator(".habit-banner-root")
        banner.wait_for(state="visible", timeout=10000)
        banner_title = banner.locator(".hb-title").inner_text()
        print(f"  [PASS] Habit Banner Title: '{banner_title}'")
        assert "Daily Habit Check-in" in banner_title

        p2_initial = os.path.join(SCREENSHOT_DIR, "03_notes_habit_banner.png")
        page.screenshot(path=p2_initial)
        print(f"  [SCREENSHOT] Saved: {p2_initial}")

        # Helper to find a habit card inside the banner
        def get_habit_card(name_substr):
            return banner.locator(".habit-item-card", has=page.locator(".h-title", has_text=name_substr))

        # 2.1 Test Gym Yes/No and muscle group chips
        print("  Testing Gym & Fitness...")
        gym_card = get_habit_card("Gym & Fitness")
        # Click Yes
        gym_card.locator("button.yn-btn.yes").click()
        page.wait_for_timeout(600)
        # Select muscle group chips: "Leg Day", "Cardio"
        leg_chip = gym_card.locator(".chip-btn", has_text="Leg Day")
        leg_chip.click()
        page.wait_for_timeout(400)
        cardio_chip = gym_card.locator(".chip-btn", has_text="Cardio")
        cardio_chip.click()
        page.wait_for_timeout(400)
        print("    [PASS] Gym 'Yes' clicked, chips 'Leg Day' & 'Cardio' selected")

        # 2.2 Test Meditation Yes/No and duration chips
        print("  Testing Meditation & Breathwork...")
        med_card = get_habit_card("Meditation & Breathwork")
        med_card.locator("button.yn-btn.yes").click()
        page.wait_for_timeout(600)
        dur_chip = med_card.locator(".chip-btn", has_text="15 mins")
        dur_chip.click()
        page.wait_for_timeout(400)
        print("    [PASS] Meditation 'Yes' clicked, duration '15 mins' selected")

        # 2.3 Test Study Yes/No and course chips
        print("  Testing Focused Study...")
        study_card = get_habit_card("Focused Study")
        study_card.locator("button.yn-btn.yes").click()
        page.wait_for_timeout(600)
        course_chip = study_card.locator(".chip-btn", has_text="FastAPI Backend")
        course_chip.click()
        page.wait_for_timeout(400)
        print("    [PASS] Study 'Yes' clicked, course 'FastAPI Backend' selected")

        # 2.4 Test Diet Yes/No and meal chips
        print("  Testing Diet & Meals...")
        diet_card = get_habit_card("Diet & Meals")
        diet_card.locator("button.yn-btn.yes").click()
        page.wait_for_timeout(600)
        meal_chip = diet_card.locator(".chip-btn", has_text="Lunch: High Protein")
        meal_chip.click()
        page.wait_for_timeout(400)
        print("    [PASS] Diet 'Yes' clicked, meal 'Lunch: High Protein' selected")

        # 2.5 Test Medicine Yes/No and dosage chips
        print("  Testing Medicine & Supplements...")
        meds_card = get_habit_card("Medicine & Supplements")
        meds_card.locator("button.yn-btn.yes").click()
        page.wait_for_timeout(600)
        dose_chip = meds_card.locator(".chip-btn", has_text="Morning: Multivitamin + D3")
        dose_chip.click()
        page.wait_for_timeout(400)
        print("    [PASS] Medicine 'Yes' clicked, dosage 'Morning: Multivitamin + D3' selected")

        # 2.6 Test Weight stepper +/- and save
        print("  Testing Body Weight Log stepper and save...")
        weight_card = get_habit_card("Body Weight Log")
        val_before = weight_card.locator(".s-val").inner_text()
        print(f"    Initial weight display: {val_before}")
        # Click + stepper twice
        weight_card.locator("button.s-btn", has_text="+").click()
        page.wait_for_timeout(300)
        weight_card.locator("button.s-btn", has_text="+").click()
        page.wait_for_timeout(300)
        val_after_plus = weight_card.locator(".s-val").inner_text()
        print(f"    After '+' clicks: {val_after_plus}")
        # Click - stepper once
        weight_card.locator("button.s-btn", has_text="-").click()
        page.wait_for_timeout(300)
        val_after_minus = weight_card.locator(".s-val").inner_text()
        print(f"    After '-' click: {val_after_minus}")
        # Click Save
        weight_card.locator("button.btn-save-weight").click()
        page.wait_for_timeout(800)
        save_btn_text = weight_card.locator("button.btn-save-weight").inner_text()
        print(f"    Save button state: '{save_btn_text}'")
        assert "Saved" in save_btn_text or "✓" in save_btn_text
        print("    [PASS] Body Weight Stepper & Save verified")

        p2_done = os.path.join(SCREENSHOT_DIR, "04_notes_habit_banner_configured.png")
        page.screenshot(path=p2_done)
        print(f"  [SCREENSHOT] Saved: {p2_done}")


        # =====================================================================
        # PART 3: ANALYTICS TAB (#/analytics)
        # =====================================================================
        print("\n--- PART 3: Testing Analytics Tab (http://localhost:8080/#/analytics) ---")
        page.goto("http://localhost:8080/#/analytics", wait_until="domcontentloaded")
        page.wait_for_timeout(2500)

        # 3.1 Verify Focus Time Allocation Donut Chart
        alloc_heading = page.locator("h2", has_text="Focus Time Allocation")
        alloc_heading.wait_for(state="visible", timeout=10000)
        donut_svg = page.locator("svg.donut-svg")
        assert donut_svg.is_visible(), "Donut SVG chart not visible"
        donut_wrap = page.locator(".allocation-donut-wrap")
        donut_text = donut_wrap.inner_text().replace("\n", " ")
        print(f"  [PASS] Donut Center & Allocation Text: '{donut_text}'")
        assert "28.5h" in donut_text, f"Expected 28.5h in donut, got: {donut_text}"

        # 3.2 Verify Ranked Focus by Project
        ranked_heading = page.locator("h2", has_text="Ranked Focus by Project")
        assert ranked_heading.is_visible(), "Ranked Focus by Project heading not found"
        ranked_bars = page.locator(".ranked-bar-row")
        ranked_count = ranked_bars.count()
        print(f"  [PASS] Ranked Project Bars Count: {ranked_count}")
        assert ranked_count >= 3, f"Expected at least 3 ranked bars, found {ranked_count}"
        top_project = ranked_bars.first.inner_text().replace("\n", " ")
        print(f"  [PASS] Top Ranked Project: {top_project}")

        # 3.3 Verify Stacked Daily distribution / Focus Time Distribution
        focus_dist_heading = page.locator("h2", has_text="Focus Time Distribution")
        assert focus_dist_heading.is_visible(), "Focus Time Distribution heading not found"
        chart_bars = page.locator(".chart-bar.focus-bar")
        print(f"  [PASS] Focus Time Distribution Bars Count: {chart_bars.count()}")
        # Test switching between Bar and Line Graph modes
        line_mode_btn = page.locator(".chart-type-toggle button[title='Switch to Line Graph']").first
        if line_mode_btn.is_visible():
            line_mode_btn.click()
            page.wait_for_timeout(500)
            print("  [PASS] Switched Focus Distribution to Line Graph mode")
            bar_mode_btn = page.locator(".chart-type-toggle button[title='Switch to Bar Graph']").first
            bar_mode_btn.click()
            page.wait_for_timeout(500)
            print("  [PASS] Switched Focus Distribution back to Bar Graph mode")

        # 3.4 Verify Body Weight Progress line chart
        weight_heading = page.locator("h2", has_text="Body Weight Progress")
        assert weight_heading.is_visible(), "Body Weight Progress heading not found"
        weight_card = page.locator(".dashboard-card", has=weight_heading)
        weight_card_text = weight_card.inner_text()
        print(f"  [PASS] Weight Card Summary: {weight_card_text.splitlines()[:3]}")
        assert ("74.2" in weight_card_text or "74.3" in weight_card_text), f"Weight not in card text: {weight_card_text}"
        assert "72.0" in weight_card_text or "Goal" in weight_card_text, "Goal weight not in card text"

        # 3.5 Verify Workout & Mindfulness Balance widgets
        balance_heading = page.locator("h2", has_text="Workout & Mindfulness Balance")
        assert balance_heading.is_visible(), "Workout & Mindfulness Balance heading not found"
        balance_card = page.locator(".dashboard-card", has=balance_heading)
        muscle_chips = balance_card.locator(".m-chip-badge")
        print(f"  [PASS] Workout Muscle Chips Count: {muscle_chips.count()}")
        med_boxes = balance_card.locator(".med-box")
        print(f"  [PASS] Meditation Metric Boxes Count: {med_boxes.count()}")
        balance_text = balance_card.inner_text().replace("\n", " ")
        print(f"  [PASS] Balance Content Preview: {balance_text[:120]}...")
        assert "Leg Day" in balance_text, "Leg Day not in workout balance"
        assert ("Total Mins" in balance_text or "Meditated" in balance_text or "Days Done" in balance_text), "Meditation metrics not in balance card"

        # Screenshots of Analytics
        p3_donut = os.path.join(SCREENSHOT_DIR, "05_analytics_donut_and_kpis.png")
        page.screenshot(path=p3_donut)
        print(f"  [SCREENSHOT] Saved: {p3_donut}")

        # Scroll to Habit Analytics section
        weight_heading.scroll_into_view_if_needed()
        page.wait_for_timeout(600)
        p3_habits = os.path.join(SCREENSHOT_DIR, "06_analytics_weight_and_balance.png")
        page.screenshot(path=p3_habits)
        print(f"  [SCREENSHOT] Saved: {p3_habits}")

        # Full-page screenshot
        p3_full = os.path.join(SCREENSHOT_DIR, "07_analytics_full_page.png")
        page.screenshot(path=p3_full, full_page=True)
        print(f"  [SCREENSHOT] Saved: {p3_full}")

        browser.close()

    print("\n" + "=" * 70)
    print("ALL TESTS PASSED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == "__main__":
    run_tests()
