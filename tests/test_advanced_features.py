import io
import json
import os
import unittest
from fastapi.testclient import TestClient

from notetrace_backend.main import app
from notetrace_backend.main import app
from notetrace_backend.database import clear_all_tables, init_db
from notetrace_backend.config import DB_PATH

class AdvancedParityTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        clear_all_tables()
        cls.client = TestClient(app)

        # 1. Create admin user
        reg_admin = cls.client.post("/api/auth/register", json={
            "username": "superadmin",
            "password": "Password123!",
            "full_name": "Super Admin"
        }).json()
        cls.admin_token = cls.client.post("/api/auth/login", json={
            "username": "superadmin",
            "password": "Password123!"
        }).json()["token"]
        cls.admin_headers = {"Authorization": f"Bearer {cls.admin_token}"}

        # 2. Create normal user
        reg_user = cls.client.post("/api/auth/register", json={
            "username": "colleague",
            "password": "Password123!",
            "full_name": "Colleague"
        }).json()
        cls.user_id = reg_user["user"]["id"]
        cls.user_token = cls.client.post("/api/auth/login", json={
            "username": "colleague",
            "password": "Password123!"
        }).json()["token"]
        cls.user_headers = {"Authorization": f"Bearer {cls.user_token}"}

    def test_01_api_tokens_and_bearer_auth(self):
        # Admin creates API token
        res = self.client.post("/api/admin/api-tokens", json={"name": "tablet-cli"}, headers=self.admin_headers)
        self.assertIn(res.status_code, (200, 201))
        data = res.json()
        raw_token = data.get("raw")
        self.assertTrue(raw_token.startswith("note_pat_"))

        # Verify we can authenticate with this Bearer token
        token_headers = {"Authorization": f"Bearer {raw_token}"}
        who = self.client.get("/api/auth/me", headers=token_headers)
        self.assertEqual(who.status_code, 200)
        self.assertEqual(who.json()["user"]["username"], "superadmin")

        # Create note using API token
        note = self.client.post("/api/notes", json={"title": "Via Token", "body_md": "Automated note"}, headers=token_headers)
        self.assertEqual(note.status_code, 200)
        self.assertEqual(note.json()["title"], "Via Token")

    def test_02_note_sharing_and_permissions(self):
        # Superadmin creates a private note
        n1 = self.client.post("/api/notes", json={"title": "Secret Note", "body_md": "Confidential"}, headers=self.admin_headers).json()
        n1_id = n1["id"]

        # Colleague cannot see secret note
        c_notes = self.client.get("/api/notes", headers=self.user_headers).json()
        self.assertNotIn(n1_id, [n["id"] for n in c_notes])

        # Colleague cannot view or edit
        get_res = self.client.get(f"/api/notes/{n1_id}", headers=self.user_headers)
        self.assertEqual(get_res.status_code, 404)

        # Admin invites colleague as 'view'
        invite = self.client.post(f"/api/notes/{n1_id}/members", json={"username": "colleague", "role": "view"}, headers=self.admin_headers)
        self.assertEqual(invite.status_code, 200)

        # Colleague can now view note
        c_view = self.client.get(f"/api/notes/{n1_id}", headers=self.user_headers)
        self.assertEqual(c_view.status_code, 200)
        self.assertEqual(c_view.json()["title"], "Secret Note")

        # Colleague CANNOT edit content
        c_edit = self.client.patch(f"/api/notes/{n1_id}", json={"body_md": "Hacked!"}, headers=self.user_headers)
        # With 'view' role, body changes are ignored and note remains confidential
        refreshed = self.client.get(f"/api/notes/{n1_id}", headers=self.admin_headers).json()
        self.assertEqual(refreshed["body_md"], "Confidential")

        # Colleague CANNOT delete note
        c_del = self.client.delete(f"/api/notes/{n1_id}", headers=self.user_headers)
        self.assertIn(c_del.status_code, (403, 404))

    def test_03_sync_push_and_pull(self):
        # Client pushes a new note with temp UUID
        push_payload = {
            "tables": {
                "notes": [
                    {
                        "client_id": "tmp-uuid-101",
                        "title": "Offline Created Note",
                        "body_md": "Created on tablet while offline",
                        "kind": "text",
                        "color": "lavender",
                        "updated_at": "2026-03-01T12:00:00Z"
                    }
                ],
                "labels": [
                    {
                        "client_id": "tmp-lbl-202",
                        "name": "SyncTest",
                        "color": "berry"
                    }
                ],
                "note_labels": [
                    {
                        "note_id": "tmp-uuid-101",
                        "label_id": "tmp-lbl-202",
                        "_local_fks": ["note_id", "label_id"]
                    }
                ]
            }
        }
        res = self.client.post("/api/sync/push", json=push_payload, headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        tables = data.get("tables", {})
        self.assertIn("notes", tables)
        note_entry = next(e for e in tables["notes"] if e["client_id"] == "tmp-uuid-101")
        new_server_id = note_entry["server_id"]
        self.assertTrue(new_server_id)

        # Pull sync changes since start of 2026
        pull_res = self.client.get("/api/sync/pull?since=2026-01-01T00:00:00Z", headers=self.admin_headers)
        self.assertEqual(pull_res.status_code, 200)
        p_data = pull_res.json()
        tables = p_data.get("tables", {})
        self.assertIn("notes", tables)
        pulled_ids = [n["id"] for n in tables["notes"]]
        self.assertIn(new_server_id, pulled_ids)

    def test_04_wikilink_propagation(self):
        # Note A refers to Note B via [[Project Alpha]]
        b = self.client.post("/api/notes", json={"title": "Project Alpha", "body_md": "Alpha details"}, headers=self.admin_headers).json()
        b_id = b["id"]

        a = self.client.post("/api/notes", json={"title": "Dashboard", "body_md": "See [[Project Alpha]] for status"}, headers=self.admin_headers).json()
        a_id = a["id"]

        # Check backlinks on B
        b_links = self.client.get(f"/api/notes/{b_id}/backlinks", headers=self.admin_headers).json()
        self.assertEqual(len(b_links), 1)
        self.assertEqual(b_links[0]["id"], a_id)

        # Rename Note B to Project Beta with rename_links_from
        self.client.patch(f"/api/notes/{b_id}", json={
            "title": "Project Beta",
            "rename_links_from": "Project Alpha"
        }, headers=self.admin_headers)

        # Note A's body should automatically be updated to [[Project Beta]]!
        a_refreshed = self.client.get(f"/api/notes/{a_id}", headers=self.admin_headers).json()
        self.assertIn("[[Project Beta]]", a_refreshed["body_md"])

    def test_05_webhooks_and_events(self):
        # Admin creates a webhook
        wh = self.client.post("/api/admin/webhooks", json={
            "url": "http://127.0.0.1:9999/webhook",
            "events": ["note.created", "note.updated"]
        }, headers=self.admin_headers)
        self.assertIn(wh.status_code, (200, 201))
        wh_data = wh.json()["webhook"]
        self.assertEqual(wh_data["url"], "http://127.0.0.1:9999/webhook")

        # List webhooks
        wh_list = self.client.get("/api/admin/webhooks", headers=self.admin_headers).json()
        self.assertEqual(len(wh_list["webhooks"]), 1)

        # Test webhook ping
        ping = self.client.post(f"/api/admin/webhooks/{wh_data['id']}/test", headers=self.admin_headers)
        self.assertEqual(ping.status_code, 200)

if __name__ == "__main__":
    unittest.main()
