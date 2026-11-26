import unittest
from fastapi.testclient import TestClient
from notetrace_backend.main import app
from notetrace_backend.database import init_db, execute

class TestFocusAndAnalytics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)
        login = cls.client.post("/api/auth/login", json={
            "username": "admin",
            "password": "Phase1!Test"
        })
        cls.token = login.json()["token"]
        cls.headers = {"Authorization": f"Bearer {cls.token}"}

    def test_focus_lifecycle_and_analytics(self):
        # 1. Create a note and checklist item to attach
        n_res = self.client.post("/api/notes", json={"title": "Deep Work Note", "body_md": "Focus goals"}, headers=self.headers)
        self.assertIn(n_res.status_code, (200, 201))
        note_id = n_res.json()["id"]

        item_res = self.client.post(f"/api/notes/{note_id}/items", json={"text": "Write code module"}, headers=self.headers)
        self.assertEqual(item_res.status_code, 200)
        item_uuid = item_res.json()["items"][0]["uuid"]

        # 2. Check active focus initially
        res = self.client.get("/api/focus/active", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()["active"])

        # 3. Start a focus session attached to the note and item
        start_res = self.client.post("/api/focus/start", json={
            "session_type": "focus",
            "duration_min": 25,
            "note_id": note_id,
            "item_uuid": item_uuid
        }, headers=self.headers)
        self.assertEqual(start_res.status_code, 200)
        self.assertTrue(start_res.json()["active"])
        session = start_res.json()["session"]
        self.assertEqual(session["status"], "active")
        self.assertEqual(session["note_title"], "Deep Work Note")

        # 4. Check active returns the running session
        active_res = self.client.get("/api/focus/active", headers=self.headers)
        self.assertTrue(active_res.json()["active"])
        self.assertGreater(active_res.json()["session"]["remaining_sec"], 0)

        # 5. Pause the session
        pause_res = self.client.post("/api/focus/pause", headers=self.headers)
        self.assertEqual(pause_res.status_code, 200)

        # Verify paused state
        active_res = self.client.get("/api/focus/active", headers=self.headers)
        self.assertEqual(active_res.json()["session"]["status"], "paused")

        # 6. Resume the session
        resume_res = self.client.post("/api/focus/resume", headers=self.headers)
        self.assertEqual(resume_res.status_code, 200)

        # 7. Complete the session
        comp_res = self.client.post("/api/focus/complete", json={"actual_sec": 1500}, headers=self.headers)
        self.assertEqual(comp_res.status_code, 200)

        # Active should now be False
        active_res = self.client.get("/api/focus/active", headers=self.headers)
        self.assertFalse(active_res.json()["active"])

        # 8. Check History
        hist_res = self.client.get("/api/focus/history", headers=self.headers)
        self.assertEqual(hist_res.status_code, 200)
        history = hist_res.json()["history"]
        self.assertGreaterEqual(len(history), 1)
        self.assertEqual(history[0]["actual_sec"], 1500)

        # 9. Check Analytics
        analytics_res = self.client.get("/api/analytics", headers=self.headers)
        self.assertEqual(analytics_res.status_code, 200)
        data = analytics_res.json()
        self.assertIn("tasks", data)
        self.assertIn("notes", data)
        self.assertIn("focus", data)
        self.assertIn("charts", data)
        self.assertGreater(data["focus"]["min_today"], 0)
        self.assertGreaterEqual(data["focus"]["sessions_today"], 1)

if __name__ == "__main__":
    unittest.main()
