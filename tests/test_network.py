import unittest
from fastapi.testclient import TestClient
from notetrace_backend.main import app
from notetrace_backend.database import clear_all_tables, execute
from notetrace_backend.auth import hash_password, sign_token

class TestNetwork(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_network_info_and_qr(self):
        res = self.client.get("/api/system/network")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("ip", data)
        self.assertIn("port", data)
        self.assertIn("url", data)
        self.assertIn("qr_data_url", data)
        self.assertTrue(data["qr_data_url"].startswith("data:image/svg+xml"))
        self.assertIn("http://", data["url"])
        self.assertGreaterEqual(len(data["all_ips"]), 1)

    def test_custom_url_qr(self):
        target = "http://192.168.1.50:8080/?u=tester"
        res = self.client.get(f"/api/system/network/qr?url={target}")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["url"], target)
        self.assertTrue(data["qr_data_url"].startswith("data:image/svg+xml"))

if __name__ == "__main__":
    unittest.main()
