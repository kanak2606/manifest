import unittest
from fastapi.testclient import TestClient
from notetrace_backend.main import app
from notetrace_backend.database import init_db, execute

class TestPomodoroAssignFeature(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)
        cls.client.post("/api/auth/register", json={
            "username": "admin",
            "password": "Phase1!Test"
        })
        login = cls.client.post("/api/auth/login", json={
            "username": "admin",
            "password": "Phase1!Test"
        })
        cls.token = login.json().get("token")
        cls.headers = {"Authorization": f"Bearer {cls.token}"}

    def setUp(self):
        # Clear out focus sessions for a clean test state
        execute("DELETE FROM focus_sessions")

    def test_start_unassigned_pomodoro_and_complete(self):
        """Test starting a Pomodoro without a task, recording time, and verifying it is marked unassigned."""
        # 1. Start session with no task or note assigned
        start_res = self.client.post("/api/focus/start", json={
            "session_type": "focus",
            "duration_min": 25
        }, headers=self.headers)
        self.assertEqual(start_res.status_code, 200)
        session = start_res.json()["session"]
        self.assertEqual(session["status"], "active")
        self.assertIsNone(session["note_id"])
        self.assertIsNone(session["item_uuid"])
        session_id = session["id"]

        # 2. Complete session with 1500 seconds (25 minutes) recorded
        comp_res = self.client.post("/api/focus/complete", json={
            "actual_sec": 1500
        }, headers=self.headers)
        self.assertEqual(comp_res.status_code, 200)
        self.assertEqual(comp_res.json()["actual_sec"], 1500)

        # 3. Check unassigned sessions endpoint - time must be tracked here!
        unassigned_res = self.client.get("/api/focus/unassigned", headers=self.headers)
        self.assertEqual(unassigned_res.status_code, 200)
        unassigned_data = unassigned_res.json()
        self.assertEqual(unassigned_data["count"], 1)
        self.assertEqual(unassigned_data["total_unassigned_sec"], 1500)
        self.assertEqual(unassigned_data["unassigned"][0]["id"], session_id)

        # 4. Check history includes is_assigned=False
        hist_res = self.client.get("/api/focus/history", headers=self.headers)
        self.assertEqual(hist_res.status_code, 200)
        history = hist_res.json()["history"]
        self.assertEqual(len(history), 1)
        self.assertFalse(history[0]["is_assigned"])

    def test_stop_session_records_elapsed_time(self):
        """Test stopping a Pomodoro early still records time so no time is left untracked."""
        start_res = self.client.post("/api/focus/start", json={
            "session_type": "focus",
            "duration_min": 50
        }, headers=self.headers)
        self.assertEqual(start_res.status_code, 200)

        # Stop session after 12 minutes (720 seconds) with save_time=True
        stop_res = self.client.post("/api/focus/stop", json={
            "save_time": True,
            "actual_sec": 720
        }, headers=self.headers)
        self.assertEqual(stop_res.status_code, 200)
        self.assertTrue(stop_res.json()["saved_as_completed"])
        self.assertEqual(stop_res.json()["actual_sec"], 720)

        # Verify it was saved as completed in history
        hist_res = self.client.get("/api/focus/history", headers=self.headers)
        history = hist_res.json()["history"]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["status"], "completed")
        self.assertEqual(history[0]["actual_sec"], 720)

    def test_assign_completed_session_to_checklist_item(self):
        """Test assigning a completed unassigned Pomodoro session to any checklist task."""
        # 1. Create a note and checklist item
        n_res = self.client.post("/api/notes", json={"title": "Sprint Board", "kind": "checklist"}, headers=self.headers)
        note_id = n_res.json()["id"]

        item_res = self.client.post(f"/api/notes/{note_id}/items", json={"text": "Implement OAuth2 flow"}, headers=self.headers)
        item_uuid = item_res.json()["items"][0]["uuid"]

        # 2. Run and complete an unassigned Pomodoro session
        self.client.post("/api/focus/start", json={"duration_min": 25}, headers=self.headers)
        comp_res = self.client.post("/api/focus/complete", json={"actual_sec": 1500}, headers=self.headers)
        session_id = comp_res.json()["session"]["id"]

        # Verify it is unassigned initially
        u_res1 = self.client.get("/api/focus/unassigned", headers=self.headers)
        self.assertEqual(u_res1.json()["count"], 1)

        # 3. Assign this completed session back to the checklist task
        assign_res = self.client.post("/api/focus/assign", json={
            "session_id": session_id,
            "note_id": note_id,
            "item_uuid": item_uuid,
            "notes": "Focused work on OAuth2"
        }, headers=self.headers)
        self.assertEqual(assign_res.status_code, 200)
        updated = assign_res.json()["session"]
        self.assertEqual(updated["note_id"], note_id)
        self.assertEqual(updated["item_uuid"], item_uuid)
        self.assertEqual(updated["note_title"], "Sprint Board")
        self.assertEqual(updated["item_text"], "Implement OAuth2 flow")

        # 4. It should NO LONGER be unassigned
        u_res2 = self.client.get("/api/focus/unassigned", headers=self.headers)
        self.assertEqual(u_res2.json()["count"], 0)

        # 5. Check history reflects the assignment
        hist_res = self.client.get("/api/focus/history", headers=self.headers)
        history = hist_res.json()["history"]
        self.assertEqual(len(history), 1)
        self.assertTrue(history[0]["is_assigned"])
        self.assertEqual(history[0]["item_text"], "Implement OAuth2 flow")

    def test_assign_via_rest_session_id_url(self):
        """Test assigning via /api/focus/sessions/{session_id}/assign endpoint."""
        # Create a note
        n_res = self.client.post("/api/notes", json={"title": "Architecture Doc", "body_md": "Notes"}, headers=self.headers)
        note_id = n_res.json()["id"]

        # Start and complete unassigned session
        start_res = self.client.post("/api/focus/start", json={"duration_min": 30}, headers=self.headers)
        sess_id = start_res.json()["session"]["id"]
        self.client.post("/api/focus/complete", json={"session_id": sess_id, "actual_sec": 1800}, headers=self.headers)

        # Assign directly using URL parameter
        assign_res = self.client.post(f"/api/focus/sessions/{sess_id}/assign", json={
            "note_id": note_id,
            "notes": "Drafted system diagram"
        }, headers=self.headers)
        self.assertEqual(assign_res.status_code, 200)
        self.assertEqual(assign_res.json()["session"]["note_id"], note_id)
        self.assertEqual(assign_res.json()["session"]["note_title"], "Architecture Doc")

    def test_reassign_session_to_another_task(self):
        """Test that an assigned session can be easily reassigned to another task."""
        n_res = self.client.post("/api/notes", json={"title": "Tasks", "kind": "checklist"}, headers=self.headers)
        note_id = n_res.json()["id"]

        i1 = self.client.post(f"/api/notes/{note_id}/items", json={"text": "Task A"}, headers=self.headers).json()["items"][0]["uuid"]
        i2 = self.client.post(f"/api/notes/{note_id}/items", json={"text": "Task B"}, headers=self.headers).json()["items"][1]["uuid"]

        # Start assigned to Task A
        self.client.post("/api/focus/start", json={"note_id": note_id, "item_uuid": i1}, headers=self.headers)
        c = self.client.post("/api/focus/complete", json={"actual_sec": 1200}, headers=self.headers)
        session_id = c.json()["session"]["id"]

        # Reassign to Task B
        r_res = self.client.post("/api/focus/assign", json={
            "session_id": session_id,
            "note_id": note_id,
            "item_uuid": i2,
            "notes": "Task B"
        }, headers=self.headers)
        self.assertEqual(r_res.status_code, 200)
        self.assertEqual(r_res.json()["session"]["item_uuid"], i2)
        self.assertEqual(r_res.json()["session"]["item_text"], "Task B")

    def test_focus_summary_and_task_aggregation(self):
        """Test /api/focus/summary returns breakdown by item and note."""
        n_res = self.client.post("/api/notes", json={"title": "Work Project", "kind": "checklist"}, headers=self.headers)
        note_id = n_res.json()["id"]

        item = self.client.post(f"/api/notes/{note_id}/items", json={"text": "Write Unit Tests"}, headers=self.headers).json()["items"][0]["uuid"]

        # Session 1: assigned to task (1500s = 25m)
        self.client.post("/api/focus/start", json={"note_id": note_id, "item_uuid": item}, headers=self.headers)
        self.client.post("/api/focus/complete", json={"actual_sec": 1500}, headers=self.headers)

        # Session 2: unassigned (600s = 10m)
        self.client.post("/api/focus/start", json={}, headers=self.headers)
        self.client.post("/api/focus/complete", json={"actual_sec": 600}, headers=self.headers)

        # Check summary
        summary_res = self.client.get("/api/focus/summary", headers=self.headers)
        self.assertEqual(summary_res.status_code, 200)
        data = summary_res.json()

        self.assertEqual(data["total_sec"], 2100)
        self.assertEqual(data["total_count"], 2)
        self.assertEqual(data["unassigned_sec"], 600)
        self.assertEqual(data["unassigned_count"], 1)
        self.assertEqual(data["assigned_sec"], 1500)

        # Check by_item breakdown
        self.assertIn(item, data["by_item"])
        self.assertEqual(data["by_item"][item]["total_sec"], 1500)
        self.assertEqual(data["by_item"][item]["session_count"], 1)

        # Check by_note breakdown
        self.assertIn(str(note_id), data["by_note"])
        self.assertEqual(data["by_note"][str(note_id)]["total_sec"], 1500)

    def test_delete_session(self):
        """Test deleting a focus session."""
        start_res = self.client.post("/api/focus/start", json={"duration_min": 15}, headers=self.headers)
        sess_id = start_res.json()["session"]["id"]
        self.client.post("/api/focus/complete", json={"session_id": sess_id, "actual_sec": 900}, headers=self.headers)

        del_res = self.client.delete(f"/api/focus/sessions/{sess_id}", headers=self.headers)
        self.assertEqual(del_res.status_code, 200)
        self.assertTrue(del_res.json()["ok"])

        hist_res = self.client.get("/api/focus/history", headers=self.headers)
        self.assertEqual(len(hist_res.json()["history"]), 0)

if __name__ == "__main__":
    unittest.main()
