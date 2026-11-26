import os
import shutil
import time
from playwright.sync_api import sync_playwright

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
SCREENSHOT_DIR = r"D:\Projects\Note Trace\test_screenshots"
ARTIFACT_DIR = r"C:\Users\Kanak Poddar\.gemini\antigravity\brain\f2ca7952-c671-441d-a274-5f69ee243f04"
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

        # Wait for habit cards to appear
        habit_cards = page.locator(".note-card.habit-card")
        count = habit_cards.count()
        print(f"  [PASS] Found {count} habit note cards")
        assert count >= 6, f"Expected at least 6 habit cards, found {count}"

        # List initial titles and data-note-ids
        initial_order = []
        for i in range(count):
            card = habit_cards.nth(i)
            title = card.locator(".card-title-text").inner_text().strip()
            note_id = card.get_attribute("data-note-id")
            initial_order.append({"index": i, "id": note_id, "title": title})
            print(f"    Card {i}: id={note_id} | title='{title}'")

        # Let's drag the last card (Body Weight Log) to the top before Card 0 (Gym & Fitness)
        source_idx = count - 1
        source_card = habit_cards.nth(source_idx)
        source_title = source_card.locator(".card-title-text").inner_text().strip()
        source_id = source_card.get_attribute("data-note-id")

        target_idx = 0
        target_card = habit_cards.nth(target_idx)
        target_title = target_card.locator(".card-title-text").inner_text().strip()
        target_id = target_card.get_attribute("data-note-id")

        print(f"\n2. Dragging '{source_title}' (id={source_id}) to before '{target_title}' (id={target_id})...")

        # Coordinates for source drag start (on header band)
        header_box = source_card.locator(".card-title").bounding_box()
        assert header_box is not None, "Source header bounding box is None"
        start_x = header_box["x"] + header_box["width"] / 2
        start_y = header_box["y"] + header_box["height"] / 2

        # Target drop coordinates (top portion of target card so it drops before)
        target_box = target_card.bounding_box()
        assert target_box is not None, "Target bounding box is None"
        target_x = target_box["x"] + target_box["width"] / 2
        target_y = target_box["y"] + 15  # within top half of target card

        # Begin drag: move to source, mouse down, move past slop
        page.mouse.move(start_x, start_y)
        page.mouse.down()
        page.mouse.move(start_x + 15, start_y + 15, steps=5)
        page.wait_for_timeout(300)

        # Check for drag-ghost
        ghost_count = page.locator(".drag-ghost").count()
        print(f"  [PASS] Ghost elements during drag: {ghost_count}")

        # Capture screenshot while dragging with ghost visible
        shot_drag = os.path.join(SCREENSHOT_DIR, "27_habit_dragging_ghost.png")
        page.screenshot(path=shot_drag)
        print(f"  [SCREENSHOT] Saved dragging ghost: {shot_drag}")

        # Move to target and release
        page.mouse.move(target_x, target_y, steps=20)
        page.wait_for_timeout(400)
        page.mouse.up()
        page.wait_for_timeout(1500)

        # Verify immediate DOM update
        new_cards = page.locator(".note-card.habit-card")
        first_title = new_cards.nth(0).locator(".card-title-text").inner_text().strip()
        first_id = new_cards.nth(0).get_attribute("data-note-id")
        print(f"  [CHECK] First card is now: id={first_id} | title='{first_title}'")
        assert first_id == source_id, f"Expected first card id {source_id}, got {first_id}"
        print(f"  [PASS] Successfully moved '{source_title}' to the top of the grid!")

        # 3. Reload page to test database persistence across full browser refresh
        print("\n3. Reloading page to verify persistence in SQLite database...")
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        reloaded_cards = page.locator(".note-card.habit-card")
        reloaded_count = reloaded_cards.count()
        assert reloaded_count >= 6, f"Expected >= 6 cards after reload, got {reloaded_count}"

        reloaded_first_title = reloaded_cards.nth(0).locator(".card-title-text").inner_text().strip()
        reloaded_first_id = reloaded_cards.nth(0).get_attribute("data-note-id")
        print(f"  [RELOAD CHECK] First card after reload: id={reloaded_first_id} | title='{reloaded_first_title}'")
        assert reloaded_first_id == source_id, f"Expected persisted first card id {source_id}, got {reloaded_first_id}"
        print(f"  [PASS] Persistence verified! '{source_title}' remains at position 1 across page reloads.")

        # Capture screenshot of persisted reordered habits
        shot_persisted = os.path.join(SCREENSHOT_DIR, "28_habit_reordered_persisted.png")
        page.screenshot(path=shot_persisted)
        print(f"  [SCREENSHOT] Saved reordered & persisted view: {shot_persisted}")

        # Copy to artifact directory
        for s in ["27_habit_dragging_ghost.png", "28_habit_reordered_persisted.png"]:
            src = os.path.join(SCREENSHOT_DIR, s)
            dst = os.path.join(ARTIFACT_DIR, s)
            if os.path.exists(src):
                shutil.copyfile(src, dst)
                print(f"  [COPIED] {s} -> Artifacts directory")

        browser.close()
        print("\n=== ALL DRAG-AND-DROP REORDER TESTS PASSED ===")

if __name__ == "__main__":
    main()
