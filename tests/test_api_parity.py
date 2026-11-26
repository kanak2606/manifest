import io
import json
import os
import sys
import unittest
from fastapi.testclient import TestClient

from notetrace_backend.main import app
from notetrace_backend.database import clear_all_tables, get_connection, init_db
from notetrace_backend.config import DB_PATH, UPLOADS_PATH

class NoteTraceParityTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        clear_all_tables()
        cls.client = TestClient(app)

    def test_01_health_and_setup_required(self):
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("ok"))
        self.assertTrue(data.get("setup_required"))

    def test_02_auth_register_and_login(self):
        # Register first user (auto-admin)
        reg_payload = {
            "username": "admin",
            "password": "Phase1!Test",
            "full_name": "Admin User"
        }
        res = self.client.post("/api/auth/register", json=reg_payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("user", data)
        self.assertEqual(data["user"]["role"], "admin")
        self.assertEqual(data["user"]["username"], "admin")

        # Login
        login_res = self.client.post("/api/auth/login", json={"username": "admin", "password": "Phase1!Test"})
        self.assertEqual(login_res.status_code, 200)
        token = login_res.json().get("token")
        self.assertTrue(token)
        self.__class__.admin_token = token
        self.__class__.auth_headers = {"Authorization": f"Bearer {token}"}

    def test_03_notes_crud_and_palette(self):
        headers = self.__class__.auth_headers

        # Create text note with valid color 'tide'
        t_note = self.client.post(
            "/api/notes",
            json={"title": "Homelab to-do", "body_md": "Move **Jellyfin** transcodes to Arc card", "color": "tide"},
            headers=headers
        ).json()
        self.assertTrue(t_note.get("id"))
        self.assertEqual(t_note.get("kind"), "text")
        self.assertEqual(t_note.get("color"), "tide")
        self.__class__.text_note_id = t_note["id"]

        # Create checklist note
        c_note = self.client.post(
            "/api/notes",
            json={"title": "Groceries", "kind": "checklist", "items": [{"text": "Limes"}, {"text": "Jasmine rice"}]},
            headers=headers
        ).json()
        self.assertEqual(len(c_note.get("items", [])), 2)
        self.assertTrue(c_note["items"][0].get("uuid"))
        self.__class__.checklist_note_id = c_note["id"]

        # Invalid color rejected to null
        bad_col = self.client.post("/api/notes", json={"title": "x", "color": "neon"}, headers=headers).json()
        self.assertIsNone(bad_col.get("color"))

    def test_04_checklist_items_operations(self):
        headers = self.__class__.auth_headers
        cid = self.__class__.checklist_note_id

        # Add item appends
        n = self.client.post(f"/api/notes/{cid}/items", json={"text": "Cilantro"}, headers=headers).json()
        self.assertEqual(len(n["items"]), 3)
        self.assertEqual(n["items"][2]["text"], "Cilantro")

        uuids = [i["uuid"] for i in n["items"]]
        i1, i2, i3 = uuids[0], uuids[1], uuids[2]

        # Reorder items
        n = self.client.put(f"/api/notes/{cid}/items/order", json={"uuids": [i3, i1, i2]}, headers=headers).json()
        self.assertEqual([i["uuid"] for i in n["items"]], [i3, i1, i2])

        # Check items
        self.client.patch(f"/api/notes/{cid}/items/{i1}", json={"checked": True}, headers=headers)
        self.client.patch(f"/api/notes/{cid}/items/{i2}", json={"checked": True}, headers=headers)

        # Delete item
        n = self.client.delete(f"/api/notes/{cid}/items/{i3}", headers=headers).json()
        self.assertEqual(len(n["items"]), 2)
        self.assertTrue(all(i["checked"] for i in n["items"]))

    def test_05_tasks_due_count_and_repeating_tasks(self):
        headers = self.__class__.auth_headers

        # Tasks due count
        due = self.client.post(
            "/api/notes",
            json={
                "title": "Errands",
                "kind": "checklist",
                "items": [
                    {"text": "Renew passport", "due_date": "2026-01-05"},
                    {"text": "Later", "due_date": "2099-12-31"},
                    {"text": "No date"}
                ]
            },
            headers=headers
        ).json()

        counts = self.client.get("/api/notes/counts?today=2026-01-05", headers=headers).json()
        self.assertEqual(counts["tasksDue"], 1)

        # Repeating tasks
        rep = self.client.post(
            "/api/notes",
            json={
                "title": "Chores",
                "kind": "checklist",
                "items": [
                    {"text": "Bins out", "due_date": "2026-09-15", "due_repeat": "weekly"},
                    {"text": "One-off", "due_date": "2026-09-15"}
                ]
            },
            headers=headers
        ).json()
        bins = next(i for i in rep["items"] if i["text"] == "Bins out")
        self.assertEqual(bins["due_repeat"], "weekly")

        # Ticking repeating task moves date forward and leaves open
        after = self.client.patch(
            f"/api/notes/{rep['id']}/items/{bins['uuid']}",
            json={"checked": True, "today": "2026-09-15"},
            headers=headers
        ).json()
        bins_now = next(i for i in after["items"] if i["uuid"] == bins["uuid"])
        self.assertFalse(bins_now["checked"])
        self.assertEqual(bins_now["due_date"], "2026-09-22")

    def test_06_labels_and_tagging(self):
        headers = self.__class__.auth_headers
        cid = self.__class__.checklist_note_id

        home = self.client.post("/api/labels", json={"name": "Home", "color": "moss"}, headers=headers).json()
        self.assertTrue(home.get("id"))

        # Duplicate label name rejected
        dup = self.client.post("/api/labels", json={"name": "home"}, headers=headers)
        self.assertEqual(dup.status_code, 400)

        # Attach label to note
        n = self.client.patch(f"/api/notes/{cid}", json={"labels": [home["id"]]}, headers=headers).json()
        self.assertEqual(len(n["labels"]), 1)

        # Filter notes by label
        filtered = self.client.get(f"/api/notes?label={home['id']}", headers=headers).json()
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["id"], cid)

    def test_07_search_fts5(self):
        headers = self.__class__.auth_headers
        tid = self.__class__.text_note_id
        cid = self.__class__.checklist_note_id

        # Prefix search in body
        s1 = self.client.get("/api/notes?q=jelly", headers=headers).json()
        self.assertEqual(len(s1), 1)
        self.assertEqual(s1[0]["id"], tid)

        # Search checklist item text
        s2 = self.client.get("/api/notes?q=jasmine", headers=headers).json()
        self.assertEqual(len(s2), 1)
        self.assertEqual(s2[0]["id"], cid)

    def test_08_pin_archive_versions_convert(self):
        headers = self.__class__.auth_headers
        tid = self.__class__.text_note_id
        cid = self.__class__.checklist_note_id

        # Pinning
        n = self.client.patch(f"/api/notes/{tid}", json={"pinned": True}, headers=headers).json()
        self.assertTrue(n["pinned"])

        # Edit triggers version snapshot
        self.client.patch(f"/api/notes/{tid}", json={"body_md": "Move Jellyfin transcodes. Renew cert."}, headers=headers)
        versions = self.client.get(f"/api/notes/{tid}/versions", headers=headers).json()
        self.assertGreaterEqual(len(versions), 1)
        self.assertIn("Arc card", versions[0]["body_md"])

        # Convert checklist to text
        conv = self.client.post(f"/api/notes/{cid}/convert", json={"kind": "text"}, headers=headers).json()
        self.assertEqual(conv["kind"], "text")
        self.assertIn("- [x] Limes", conv["body_md"])

        # Convert back
        conv2 = self.client.post(f"/api/notes/{cid}/convert", json={"kind": "checklist"}, headers=headers).json()
        self.assertEqual(conv2["kind"], "checklist")
        self.assertEqual(len(conv2["items"]), 2)

    def test_09_trash_and_restore(self):
        headers = self.__class__.auth_headers
        cid = self.__class__.checklist_note_id

        # Trash note
        self.client.delete(f"/api/notes/{cid}", headers=headers)
        trash_list = self.client.get("/api/notes?view=trash", headers=headers).json()
        self.assertEqual(len(trash_list), 1)

        # Restore
        self.client.post(f"/api/notes/{cid}/restore", headers=headers)
        trash_list2 = self.client.get("/api/notes?view=trash", headers=headers).json()
        self.assertEqual(len(trash_list2), 0)

    def test_10_public_link(self):
        headers = self.__class__.auth_headers
        tid = self.__class__.text_note_id

        # Create public link
        link = self.client.post(f"/api/notes/{tid}/public-link", headers=headers).json()
        token = link.get("token")
        self.assertTrue(token)

        # Read anonymously
        anon_res = self.client.get(f"/api/n/{token}")
        self.assertEqual(anon_res.status_code, 200)
        self.assertEqual(anon_res.json()["title"], "Homelab to-do")

        # HTML page with meta tags
        html_res = self.client.get(f"/n/{token}")
        self.assertEqual(html_res.status_code, 200)
        self.assertIn("og:title", html_res.text)

    def test_11_attachments_upload(self):
        headers = self.__class__.auth_headers

        # 2x2 png bytes
        png_bytes = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x02\x00\x00\x00\x02\x08\x02\x00\x00\x00\xfd\xd4\x9a\x73\x00\x00\x00\x10IDATx\x9cc\xf8\xcf\xc0\xf0\x1f\x01\x08\x18\x03\x00\x1d\xe0\x03\xfd\\\xa1E\xd5\x00\x00\x00\x00IEND\xaeB`\x82'
        files = {"file": ("dot.png", io.BytesIO(png_bytes), "image/png")}
        up = self.client.post("/api/upload", files=files, headers=headers).json()
        self.assertTrue(up["url"].startswith("/uploads/"))

    def test_12_display_kiosk_route(self):
        # Kiosk view loads without auth
        disp = self.client.get("/display")
        self.assertEqual(disp.status_code, 200)
        self.assertIn("NiKiosk Display", disp.text)
        self.assertIn("LIVE SYNC", disp.text)

        # Kiosk data endpoint
        data_res = self.client.get("/api/display/data")
        self.assertEqual(data_res.status_code, 200)
        data = data_res.json()
        self.assertIn("pinned_notes", data)
        self.assertIn("tasks_due", data)
        self.assertIn("reminders", data)

    def test_13_full_backup_and_restore(self):
        headers = self.__class__.auth_headers

        # Create backup
        bk = self.client.post("/api/full-backup", headers=headers).json()
        self.assertTrue(bk.get("filename"))

        # Restore backup
        res = self.client.post(f"/api/full-backup/{bk['filename']}/restore", headers=headers).json()
        self.assertTrue(res.get("ok"))

        # Verify search works after restore
        s = self.client.get("/api/notes?q=jelly", headers=headers).json()
        self.assertEqual(len(s), 1)

if __name__ == "__main__":
    unittest.main()
