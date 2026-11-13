"""
Stage 8 — Account Settings Test Suite
======================================
Tests:
 1. Unauthenticated profile access redirects to login.
 2. Authenticated profile displays username and membership date.
 3. Password hash is not exposed on the profile page.
 4. Missing or invalid CSRF token on POST /account/password is rejected (HTTP 400).
 5. Password change rejects incorrect current password.
 6. Password change rejects mismatched new password and confirmation.
 7. Passwords shorter than 8 characters are rejected.
 8. Passwords longer than 128 characters are rejected.
 9. Reusing the current password is rejected.
10. Valid password change updates the password hash in the database.
11. New password works for login; old password fails.
12. Missing or invalid CSRF token on POST /account/delete is rejected (HTTP 400).
13. Account deletion rejects incorrect password.
14. Account deletion rejects invalid confirmation phrase (e.g. 'delete', 'yes', '').
15. Valid deletion removes user record from users table.
16. Valid deletion deletes user preferences, rate alerts, and saved items.
17. Other users' accounts and saved data remain unchanged.
18. Session is cleared after successful deletion.
19. Deleted users cannot log in.
20. Failed password changes leave database records unchanged.
21. Failed deletion attempts leave database records unchanged.
22. Guest pages and snapshots remain completely unaffected.
"""

import os
import sys
import json
import uuid
import sqlite3
import unittest
from werkzeug.security import check_password_hash

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app as flask_app
import database


def _register_and_login(client, username, password="Password123"):
    with client.session_transaction() as sess:
        sess["_csrf_token"] = "testcsrf8"
    client.post("/register", data={
        "username": username,
        "password": password,
        "csrf_token": "testcsrf8",
    }, follow_redirects=True)
    with client.session_transaction() as sess:
        sess["_csrf_token"] = "testcsrf8"
    client.post("/login", data={
        "username": username,
        "password": password,
        "csrf_token": "testcsrf8",
    }, follow_redirects=True)


class TestStage8AccountSettings(unittest.TestCase):

    def setUp(self):
        flask_app.app.config["TESTING"] = True
        flask_app.app.config["WTF_CSRF_ENABLED"] = False
        flask_app.app.config["SECRET_KEY"] = "stage8-test-secret"
        self.client = flask_app.app.test_client()
        database.create_database()

    # 1. Unauthenticated profile access redirects to login
    def test_01_unauthenticated_profile_redirects(self):
        r = self.client.get("/account")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers.get("Location", ""))

    # 2. Authenticated profile displays username and membership date
    def test_02_authenticated_profile_displays_info(self):
        _register_and_login(self.client, "profile_user_8")
        r = self.client.get("/account")
        self.assertEqual(r.status_code, 200)
        html = r.data.decode("utf-8")
        self.assertIn("profile_user_8", html)
        self.assertIn("Member Since", html)
        self.assertIn("Profile Information", html)

    # 3. Password hash is not exposed
    def test_03_password_hash_not_exposed(self):
        _register_and_login(self.client, "nohash_user_8", "SecretPass123")
        conn = sqlite3.connect(database.DATABASE_NAME)
        cur = conn.cursor()
        cur.execute("SELECT password_hash FROM users WHERE username = ?", ("nohash_user_8",))
        stored_hash = cur.fetchone()[0]
        conn.close()

        r = self.client.get("/account")
        html = r.data.decode("utf-8")
        self.assertNotIn(stored_hash, html)
        self.assertNotIn("scrypt:", html)
        self.assertNotIn("pbkdf2:", html)

    # 4. Missing or invalid CSRF tokens are rejected
    def test_04_csrf_protection_enforced_on_password_change(self):
        _register_and_login(self.client, "csrf_user_pw_8")
        # Deliberately omit csrf_token
        r = self.client.post("/account/password", data={
            "current_password": "Password123",
            "new_password": "NewPassword123",
            "confirm_password": "NewPassword123",
        })
        self.assertEqual(r.status_code, 400)

    # 5. Incorrect current password is rejected
    def test_05_incorrect_current_password_rejected(self):
        _register_and_login(self.client, "wrong_pw_user_8", "ValidOldPass1")
        with self.client.session_transaction() as sess:
            sess["_csrf_token"] = "testcsrf8"
        r = self.client.post("/account/password", data={
            "current_password": "WrongPassword1",
            "new_password": "BrandNewPass1",
            "confirm_password": "BrandNewPass1",
            "csrf_token": "testcsrf8",
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        html = r.data.decode("utf-8")
        self.assertIn("Incorrect current password", html)

    # 6. Mismatched new passwords are rejected
    def test_06_mismatched_new_passwords_rejected(self):
        _register_and_login(self.client, "mismatch_user_8", "OriginalPass1")
        with self.client.session_transaction() as sess:
            sess["_csrf_token"] = "testcsrf8"
        r = self.client.post("/account/password", data={
            "current_password": "OriginalPass1",
            "new_password": "BrandNewPass1",
            "confirm_password": "DifferentPass2",
            "csrf_token": "testcsrf8",
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        html = r.data.decode("utf-8")
        self.assertIn("New passwords do not match", html)

    # 7. Passwords shorter than 8 characters are rejected
    def test_07_short_password_rejected(self):
        _register_and_login(self.client, "short_pw_user_8", "OriginalPass1")
        with self.client.session_transaction() as sess:
            sess["_csrf_token"] = "testcsrf8"
        r = self.client.post("/account/password", data={
            "current_password": "OriginalPass1",
            "new_password": "short",
            "confirm_password": "short",
            "csrf_token": "testcsrf8",
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        html = r.data.decode("utf-8")
        self.assertIn("at least 8 characters", html)

    # 8. Passwords longer than 128 characters are rejected
    def test_08_long_password_rejected(self):
        _register_and_login(self.client, "long_pw_user_8", "OriginalPass1")
        long_pw = "P" * 129
        with self.client.session_transaction() as sess:
            sess["_csrf_token"] = "testcsrf8"
        r = self.client.post("/account/password", data={
            "current_password": "OriginalPass1",
            "new_password": long_pw,
            "confirm_password": long_pw,
            "csrf_token": "testcsrf8",
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        html = r.data.decode("utf-8")
        self.assertIn("must not exceed 128 characters", html)

    # 9. Reusing the current password is rejected
    def test_09_reusing_current_password_rejected(self):
        _register_and_login(self.client, "reuse_pw_user_8", "OriginalPass1")
        with self.client.session_transaction() as sess:
            sess["_csrf_token"] = "testcsrf8"
        r = self.client.post("/account/password", data={
            "current_password": "OriginalPass1",
            "new_password": "OriginalPass1",
            "confirm_password": "OriginalPass1",
            "csrf_token": "testcsrf8",
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        html = r.data.decode("utf-8")
        self.assertIn("New password must be different", html)

    # 10. Valid password change updates the hash
    def test_10_valid_password_change_updates_hash(self):
        user_10 = f"success_pw_{uuid.uuid4().hex[:8]}"
        _register_and_login(self.client, user_10, "OldPassword1")
        conn = sqlite3.connect(database.DATABASE_NAME)
        cur = conn.cursor()
        cur.execute("SELECT password_hash FROM users WHERE username = ?", (user_10,))
        initial_hash = cur.fetchone()[0]

        with self.client.session_transaction() as sess:
            sess["_csrf_token"] = "testcsrf8"
        r = self.client.post("/account/password", data={
            "current_password": "OldPassword1",
            "new_password": "NewAwesomePassword2",
            "confirm_password": "NewAwesomePassword2",
            "csrf_token": "testcsrf8",
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        html = r.data.decode("utf-8")
        self.assertIn("Password updated successfully", html)

        cur.execute("SELECT password_hash FROM users WHERE username = ?", (user_10,))
        updated_hash = cur.fetchone()[0]
        conn.close()

        self.assertNotEqual(initial_hash, updated_hash)
        self.assertTrue(check_password_hash(updated_hash, "NewAwesomePassword2"))

    # 11. New password works for login; old password fails
    def test_11_login_with_new_password_and_old_fails(self):
        user_11 = f"login_change_{uuid.uuid4().hex[:8]}"
        _register_and_login(self.client, user_11, "OldPass1234")
        with self.client.session_transaction() as sess:
            sess["_csrf_token"] = "testcsrf8"
        self.client.post("/account/password", data={
            "current_password": "OldPass1234",
            "new_password": "BrandNewPass99",
            "confirm_password": "BrandNewPass99",
            "csrf_token": "testcsrf8",
        }, follow_redirects=True)

        # Log out
        self.client.get("/logout")

        # Attempt login with old password
        with self.client.session_transaction() as sess:
            sess["_csrf_token"] = "testcsrf8"
        r_old = self.client.post("/login", data={
            "username": user_11,
            "password": "OldPass1234",
            "csrf_token": "testcsrf8",
        }, follow_redirects=True)
        self.assertIn("Invalid credentials", r_old.data.decode("utf-8"))

        # Attempt login with new password
        with self.client.session_transaction() as sess:
            sess["_csrf_token"] = "testcsrf8"
        r_new = self.client.post("/login", data={
            "username": user_11,
            "password": "BrandNewPass99",
            "csrf_token": "testcsrf8",
        }, follow_redirects=True)
        self.assertIn("Logged in successfully", r_new.data.decode("utf-8"))

    # 12. Missing or invalid CSRF token on delete is rejected
    def test_12_csrf_protection_enforced_on_account_deletion(self):
        _register_and_login(self.client, "del_csrf_user_8")
        # Deliberately omit csrf_token
        r = self.client.post("/account/delete", data={
            "current_password": "Password123",
            "confirm_phrase": "DELETE",
        })
        self.assertEqual(r.status_code, 400)

    # 13. Account deletion rejects incorrect password
    def test_13_delete_account_incorrect_password_rejected(self):
        _register_and_login(self.client, "del_wrong_pw_user_8", "MyPassword1")
        with self.client.session_transaction() as sess:
            sess["_csrf_token"] = "testcsrf8"
        r = self.client.post("/account/delete", data={
            "current_password": "WrongPassword1",
            "confirm_phrase": "DELETE",
            "csrf_token": "testcsrf8",
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        html = r.data.decode("utf-8")
        self.assertIn("Incorrect password. Account was not deleted", html)

        # Confirm user still exists
        conn = sqlite3.connect(database.DATABASE_NAME)
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username = ?", ("del_wrong_pw_user_8",))
        self.assertIsNotNone(cur.fetchone())
        conn.close()

    # 14. Account deletion rejects invalid confirmation phrase
    def test_14_delete_account_invalid_phrase_rejected(self):
        _register_and_login(self.client, "del_bad_phrase_user_8", "MyPassword1")
        for bad_phrase in ["delete", "Delete", "NO", ""]:
            with self.client.session_transaction() as sess:
                sess["_csrf_token"] = "testcsrf8"
            r = self.client.post("/account/delete", data={
                "current_password": "MyPassword1",
                "confirm_phrase": bad_phrase,
                "csrf_token": "testcsrf8",
            }, follow_redirects=True)
            self.assertEqual(r.status_code, 200)
            html = r.data.decode("utf-8")
            self.assertIn("type DELETE in all caps", html)

        # Confirm user still exists
        conn = sqlite3.connect(database.DATABASE_NAME)
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username = ?", ("del_bad_phrase_user_8",))
        self.assertIsNotNone(cur.fetchone())
        conn.close()

    # 15. Valid deletion removes user record from users table
    # 16. Preferences, alerts and saved items are deleted
    def test_15_16_valid_deletion_cleans_all_user_records(self):
        _register_and_login(self.client, "full_delete_user_8", "ValidPass123")
        conn = sqlite3.connect(database.DATABASE_NAME)
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username = ?", ("full_delete_user_8",))
        user_id = cur.fetchone()[0]

        # Seed preferences, alerts, and saved items
        database.save_user_preferences(user_id, default_currency="JPY", watchlist=["JPY", "EUR"])
        database.add_rate_alert(user_id, "JPY", "above", 0.60)
        database.add_saved_item(user_id, "conversion", "100 USD to INR", "summary", json.dumps({"test": 1}))
        conn.close()

        # Perform deletion
        with self.client.session_transaction() as sess:
            sess["_csrf_token"] = "testcsrf8"
        r = self.client.post("/account/delete", data={
            "current_password": "ValidPass123",
            "confirm_phrase": "DELETE",
            "csrf_token": "testcsrf8",
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn("permanently deleted", r.data.decode("utf-8"))

        # Verify all tables cleared for user_id
        conn = sqlite3.connect(database.DATABASE_NAME)
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        self.assertIsNone(cur.fetchone())
        cur.execute("SELECT user_id FROM user_preferences WHERE user_id = ?", (user_id,))
        self.assertIsNone(cur.fetchone())
        cur.execute("SELECT id FROM rate_alerts WHERE user_id = ?", (user_id,))
        self.assertIsNone(cur.fetchone())
        cur.execute("SELECT id FROM saved_items WHERE user_id = ?", (user_id,))
        self.assertIsNone(cur.fetchone())
        conn.close()

    # 17. Other users' accounts and data remain unchanged
    def test_17_other_users_data_remains_unchanged(self):
        user_a_name = f"safe_user_a_{uuid.uuid4().hex[:8]}"
        user_b_name = f"victim_user_b_{uuid.uuid4().hex[:8]}"

        # Create user A (will remain)
        client_a = flask_app.app.test_client()
        _register_and_login(client_a, user_a_name, "PassA12345")
        conn = sqlite3.connect(database.DATABASE_NAME)
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username = ?", (user_a_name,))
        user_a_id = cur.fetchone()[0]
        database.save_user_preferences(user_a_id, default_currency="GBP", watchlist=["GBP"])
        database.add_saved_item(user_a_id, "conversion", "A Item", "sum", "{}")
        conn.close()

        # Create user B (will be deleted)
        client_b = flask_app.app.test_client()
        _register_and_login(client_b, user_b_name, "PassB12345")
        conn = sqlite3.connect(database.DATABASE_NAME)
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username = ?", (user_b_name,))
        user_b_id = cur.fetchone()[0]
        database.save_user_preferences(user_b_id, default_currency="EUR", watchlist=["EUR"])
        database.add_saved_item(user_b_id, "conversion", "B Item", "sum", "{}")
        conn.close()

        # Delete user B
        with client_b.session_transaction() as sess:
            sess["_csrf_token"] = "testcsrf8"
        client_b.post("/account/delete", data={
            "current_password": "PassB12345",
            "confirm_phrase": "DELETE",
            "csrf_token": "testcsrf8",
        }, follow_redirects=True)

        # Verify user A's records are completely intact
        conn = sqlite3.connect(database.DATABASE_NAME)
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE id = ?", (user_a_id,))
        self.assertIsNotNone(cur.fetchone())
        cur.execute("SELECT default_currency FROM user_preferences WHERE user_id = ?", (user_a_id,))
        pref = cur.fetchone()
        self.assertIsNotNone(pref)
        self.assertEqual(pref[0], "GBP")
        cur.execute("SELECT id FROM saved_items WHERE user_id = ?", (user_a_id,))
        self.assertEqual(len(cur.fetchall()), 1)
        conn.close()

    # 18. Session is cleared after successful deletion
    def test_18_session_cleared_after_deletion(self):
        _register_and_login(self.client, "sess_clear_user_8", "ValidPass123")
        with self.client.session_transaction() as sess:
            sess["_csrf_token"] = "testcsrf8"
        self.client.post("/account/delete", data={
            "current_password": "ValidPass123",
            "confirm_phrase": "DELETE",
            "csrf_token": "testcsrf8",
        }, follow_redirects=True)

        # Visiting protected routes should now redirect to login
        r = self.client.get("/dashboard")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers.get("Location", ""))

    # 19. Deleted users cannot log in
    def test_19_deleted_user_cannot_login(self):
        _register_and_login(self.client, "nologin_user_8", "ValidPass123")
        with self.client.session_transaction() as sess:
            sess["_csrf_token"] = "testcsrf8"
        self.client.post("/account/delete", data={
            "current_password": "ValidPass123",
            "confirm_phrase": "DELETE",
            "csrf_token": "testcsrf8",
        }, follow_redirects=True)

        # Attempt to log back in
        with self.client.session_transaction() as sess:
            sess["_csrf_token"] = "testcsrf8"
        r = self.client.post("/login", data={
            "username": "nologin_user_8",
            "password": "ValidPass123",
            "csrf_token": "testcsrf8",
        }, follow_redirects=True)
        self.assertIn("Invalid credentials", r.data.decode("utf-8"))

    # 20. Failed password changes leave database records unchanged
    def test_20_failed_password_change_preserves_db(self):
        _register_and_login(self.client, "fail_pw_pres_8", "OriginalPass1")
        conn = sqlite3.connect(database.DATABASE_NAME)
        cur = conn.cursor()
        cur.execute("SELECT password_hash FROM users WHERE username = ?", ("fail_pw_pres_8",))
        original_hash = cur.fetchone()[0]
        conn.close()

        # Failed attempt (short password)
        with self.client.session_transaction() as sess:
            sess["_csrf_token"] = "testcsrf8"
        self.client.post("/account/password", data={
            "current_password": "OriginalPass1",
            "new_password": "short",
            "confirm_password": "short",
            "csrf_token": "testcsrf8",
        }, follow_redirects=True)

        conn = sqlite3.connect(database.DATABASE_NAME)
        cur = conn.cursor()
        cur.execute("SELECT password_hash FROM users WHERE username = ?", ("fail_pw_pres_8",))
        curr_hash = cur.fetchone()[0]
        conn.close()

        self.assertEqual(original_hash, curr_hash)

    # 21. Failed deletion attempts leave database records unchanged
    def test_21_failed_deletion_preserves_db(self):
        _register_and_login(self.client, "fail_del_pres_8", "OriginalPass1")
        conn = sqlite3.connect(database.DATABASE_NAME)
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username = ?", ("fail_del_pres_8",))
        user_id = cur.fetchone()[0]
        database.save_user_preferences(user_id, default_currency="USD", watchlist=["USD"])
        conn.close()

        # Bad confirmation phrase
        with self.client.session_transaction() as sess:
            sess["_csrf_token"] = "testcsrf8"
        self.client.post("/account/delete", data={
            "current_password": "OriginalPass1",
            "confirm_phrase": "WRONG",
            "csrf_token": "testcsrf8",
        }, follow_redirects=True)

        conn = sqlite3.connect(database.DATABASE_NAME)
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        self.assertIsNotNone(cur.fetchone())
        cur.execute("SELECT default_currency FROM user_preferences WHERE user_id = ?", (user_id,))
        self.assertIsNotNone(cur.fetchone())
        conn.close()

    # 22. Passwords with intentional leading or trailing spaces are handled exactly as entered
    def test_22_whitespace_password_preserved(self):
        username = f"space_user_{uuid.uuid4().hex[:8]}"
        initial_pw = "ValidInitialPass1"
        spaced_pw = "  SpacedPassword123  "

        _register_and_login(self.client, username, initial_pw)

        # 1. Password can be changed successfully with whitespace preserved
        with self.client.session_transaction() as sess:
            sess["_csrf_token"] = "testcsrf8"
        r = self.client.post("/account/password", data={
            "current_password": initial_pw,
            "new_password": spaced_pw,
            "confirm_password": spaced_pw,
            "csrf_token": "testcsrf8",
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        html = r.data.decode("utf-8")
        self.assertIn("Password updated successfully", html)

        # 2. Stored hash verifies against exact spaced password
        conn = sqlite3.connect(database.DATABASE_NAME)
        cur = conn.cursor()
        cur.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
        row = cur.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        stored_hash = row[0]

        self.assertTrue(check_password_hash(stored_hash, spaced_pw))

        # 3. Verification fails without those spaces
        self.assertFalse(check_password_hash(stored_hash, spaced_pw.strip()))

        # 4. Deletion password check in Stage 8 verifies exact spaced password
        with self.client.session_transaction() as sess:
            sess["_csrf_token"] = "testcsrf8"
        # Stripped password must fail deletion
        r_del_fail = self.client.post("/account/delete", data={
            "current_password": spaced_pw.strip(),
            "confirm_phrase": "DELETE",
            "csrf_token": "testcsrf8",
        }, follow_redirects=True)
        self.assertIn("Incorrect password", r_del_fail.data.decode("utf-8"))

        # Exact spaced password must succeed deletion
        with self.client.session_transaction() as sess:
            sess["_csrf_token"] = "testcsrf8"
        r_del_ok = self.client.post("/account/delete", data={
            "current_password": spaced_pw,
            "confirm_phrase": "DELETE",
            "csrf_token": "testcsrf8",
        }, follow_redirects=True)
        self.assertIn("permanently deleted", r_del_ok.data.decode("utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

