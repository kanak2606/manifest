import unittest
from fastapi.testclient import TestClient
from notetrace_backend.main import app
from notetrace_backend.database import clear_all_tables, execute
from notetrace_backend.auth import hash_password, sign_token

class TestHabits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        clear_all_tables()

    def tearDown(self):
        clear_all_tables()

    def create_user_and_auth(self):
        uid = execute(
            "INSERT INTO users (username, password_hash, role) VALUES ('tester', ?, 'user')",
            (hash_password("secret123"),)
        )
        token = sign_token({"id": uid, "username": "tester", "role": "user"})
        return uid, {"Authorization": f"Bearer {token}"}

    def test_habits_defaults_and_logging(self):
        uid, headers = self.create_user_and_auth()

        # 1. GET /api/habits should seed default habits
        res = self.client.get("/api/habits", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreaterEqual(len(data["habits"]), 6)
        self.assertGreaterEqual(data["summary"]["total"], 6)
        self.assertEqual(data["summary"]["completed"], 0)

        gym_habit = next(h for h in data["habits"] if "gym" in h["title"].lower())
        self.assertIn("Leg Day", gym_habit["options"])

        # 2. Log Gym with options
        log_res = self.client.post(
            f"/api/habits/{gym_habit['id']}/log",
            headers=headers,
            json={
                "status": "yes",
                "selected_options": ["Leg Day", "Cardio"],
                "notes": "Felt great"
            }
        )
        self.assertEqual(log_res.status_code, 200)

        # 3. Add custom option to Gym
        opt_res = self.client.post(
            f"/api/habits/{gym_habit['id']}/options",
            headers=headers,
            json={"option": "Swimming"}
        )
        self.assertEqual(opt_res.status_code, 200)
        self.assertIn("Swimming", opt_res.json()["options"])

        # 4. Remove an option from Gym
        del_opt_res = self.client.post(
            f"/api/habits/{gym_habit['id']}/options/remove",
            headers=headers,
            json={"option": "Leg Day"}
        )
        self.assertEqual(del_opt_res.status_code, 200)
        self.assertNotIn("Leg Day", del_opt_res.json()["options"])

        # 5. Verify list returns updated status and streak
        res2 = self.client.get("/api/habits", headers=headers)
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertEqual(data2["summary"]["completed"], 1)
        updated_gym = next(h for h in data2["habits"] if h["id"] == gym_habit["id"])
        self.assertEqual(updated_gym["today_status"], "yes")
        self.assertEqual(updated_gym["streak"], 1)
        self.assertNotIn("Leg Day", updated_gym["options"])

    def test_multi_log_habits_and_timestamps(self):
        uid, headers = self.create_user_and_auth()
        res = self.client.get("/api/habits", headers=headers)
        self.assertEqual(res.status_code, 200)
        habits = res.json()["habits"]

        diet_habit = next(h for h in habits if "diet" in h["title"].lower())
        self.assertTrue(diet_habit["is_multi_log"])
        self.assertEqual(len(diet_habit["today_logs"]), 0)

        # 1. Log Breakfast
        log1 = self.client.post(
            f"/api/habits/{diet_habit['id']}/log",
            headers=headers,
            json={"status": "yes", "selected_options": ["Breakfast: Clean"], "notes": "Oatmeal and eggs"}
        )
        self.assertEqual(log1.status_code, 200)
        self.assertIn("timestamp", log1.json())

        # 2. Log Lunch later
        log2 = self.client.post(
            f"/api/habits/{diet_habit['id']}/log",
            headers=headers,
            json={"status": "yes", "selected_options": ["Lunch: High Protein"], "notes": "Chicken breast salad"}
        )
        self.assertEqual(log2.status_code, 200)

        # 3. Verify GET returns both logs with timestamps
        res2 = self.client.get("/api/habits", headers=headers)
        updated_diet = next(h for h in res2.json()["habits"] if h["id"] == diet_habit["id"])
        self.assertEqual(len(updated_diet["today_logs"]), 2)
        self.assertEqual(updated_diet["today_logs"][0]["selected_options"], ["Breakfast: Clean"])
        self.assertEqual(updated_diet["today_logs"][1]["selected_options"], ["Lunch: High Protein"])
        self.assertTrue(bool(updated_diet["today_logs"][0]["time"]))

        # 4. Delete one of the logs
        first_log_id = updated_diet["today_logs"][0]["id"]
        del_log_res = self.client.delete(f"/api/habits/{diet_habit['id']}/logs/{first_log_id}", headers=headers)
        self.assertEqual(del_log_res.status_code, 200)

        res3 = self.client.get("/api/habits", headers=headers)
        diet_after_del = next(h for h in res3.json()["habits"] if h["id"] == diet_habit["id"])
        self.assertEqual(len(diet_after_del["today_logs"]), 1)
        self.assertEqual(diet_after_del["today_logs"][0]["selected_options"], ["Lunch: High Protein"])

    def test_daily_reset(self):
        uid, headers = self.create_user_and_auth()
        res = self.client.get("/api/habits", headers=headers)
        gym = next(h for h in res.json()["habits"] if "gym" in h["title"].lower())

        # Log for yesterday
        from datetime import datetime, timedelta
        yesterday_str = (datetime.now().date() - timedelta(days=1)).strftime("%Y-%m-%d")
        self.client.post(
            f"/api/habits/{gym['id']}/log",
            headers=headers,
            json={"date": yesterday_str, "status": "yes", "selected_options": ["Chest"]}
        )

        # Today should be fresh / not logged yet
        today_res = self.client.get("/api/habits", headers=headers)
        today_gym = next(h for h in today_res.json()["habits"] if h["id"] == gym["id"])
        self.assertIsNone(today_gym["today_status"])
        self.assertEqual(today_gym["selected_options"], [])
        # But streak should be 1 because yesterday was completed!
        self.assertEqual(today_gym["streak"], 1)

    def test_weight_logging_and_history(self):
        uid, headers = self.create_user_and_auth()

        # Log weight
        w_res = self.client.post(
            "/api/habits/weight",
            headers=headers,
            json={"value": 74.2, "unit": "kg", "notes": "Morning fast"}
        )
        self.assertEqual(w_res.status_code, 200)
        self.assertEqual(w_res.json()["value"], 74.2)

        # Get weight history
        hist_res = self.client.get("/api/habits/weight-history", headers=headers)
        self.assertEqual(hist_res.status_code, 200)
        hist = hist_res.json()
        self.assertEqual(hist["current"], 74.2)
        self.assertGreaterEqual(len(hist["points"]), 1)

    def test_habit_reordering(self):
        uid, headers = self.create_user_and_auth()
        res = self.client.get("/api/habits", headers=headers)
        self.assertEqual(res.status_code, 200)
        original_habits = res.json()["habits"]
        self.assertGreaterEqual(len(original_habits), 6)

        original_ids = [h["id"] for h in original_habits]
        # Reverse the order
        reversed_ids = list(reversed(original_ids))

        # Call reorder endpoint
        reorder_res = self.client.post(
            "/api/habits/reorder",
            headers=headers,
            json={"habit_ids": reversed_ids}
        )
        self.assertEqual(reorder_res.status_code, 200)
        self.assertEqual(reorder_res.json()["ordered_ids"], reversed_ids)

        # Verify GET /api/habits reflects the new order
        res2 = self.client.get("/api/habits", headers=headers)
        self.assertEqual(res2.status_code, 200)
        new_ids = [h["id"] for h in res2.json()["habits"]]
        self.assertEqual(new_ids, reversed_ids)

if __name__ == "__main__":
    unittest.main()
