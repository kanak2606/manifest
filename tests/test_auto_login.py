import os
import unittest
from fastapi.testclient import TestClient

from notetrace_backend.main import app
from notetrace_backend.database import clear_all_tables, init_db
from notetrace_backend.config import DB_PATH

class AutoLoginTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        clear_all_tables()
        cls.client = TestClient(app, follow_redirects=False)

        # 1. Register admin user
        cls.client.post("/api/auth/register", json={
            "username": "admin",
            "password": "Phase1!Test",
            "full_name": "Admin User"
        })

    def test_01_auto_login_via_get_params(self):
        # Visit /?username=admin&password=Phase1!Test
        res = self.client.get("/?username=admin&password=Phase1!Test")
        # Must return 303 See Other
        self.assertEqual(res.status_code, 303)
        self.assertEqual(res.headers.get("location"), "/")
        # Must set note_token cookie
        self.assertIn("note_token", res.cookies)

        # Follow with the cookie to verify authentication
        me_res = self.client.get("/api/auth/me", cookies=res.cookies)
        self.assertEqual(me_res.status_code, 200)
        self.assertEqual(me_res.json()["user"]["username"], "admin")

    def test_02_auto_login_via_shorthand_u_and_p(self):
        # Visit /?u=admin&p=Phase1!Test
        res = self.client.get("/?u=admin&p=Phase1!Test")
        self.assertEqual(res.status_code, 303)
        self.assertEqual(res.headers.get("location"), "/")
        self.assertIn("note_token", res.cookies)

    def test_03_auto_login_with_target_redirect(self):
        # Redirect directly to kiosk display
        res = self.client.get("/?u=admin&p=Phase1!Test&redirect=/display")
        self.assertEqual(res.status_code, 303)
        self.assertEqual(res.headers.get("location"), "/display")

    def test_04_auto_login_invalid_credentials_fails(self):
        # Wrong password
        res = self.client.get("/?u=admin&p=WrongPassword")
        self.assertEqual(res.status_code, 401)
        self.assertNotIn("note_token", res.cookies)

    def test_05_auto_login_token_based(self):
        # Create an API PAT token
        login_res = self.client.post("/api/auth/login", json={"username": "admin", "password": "Phase1!Test"})
        jwt_token = login_res.json()["token"]
        headers = {"Authorization": f"Bearer {jwt_token}"}

        pat_res = self.client.post("/api/admin/api-tokens", json={"name": "tablet-auto"}, headers=headers)
        raw_pat = pat_res.json()["raw"]

        # Use the token in GET query param
        token_res = self.client.get(f"/?token={raw_pat}")
        self.assertEqual(token_res.status_code, 303)
        self.assertEqual(token_res.headers.get("location"), "/")
        self.assertIn("note_token", token_res.cookies)

    def test_06_open_redirect_mitigation(self):
        # Attempt open redirect to malicious domain
        res = self.client.get("/?u=admin&p=Phase1!Test&redirect=https://evil.com")
        self.assertEqual(res.status_code, 303)
        # Must sanitize to local "/"
        self.assertEqual(res.headers.get("location"), "/")

if __name__ == "__main__":
    unittest.main()
