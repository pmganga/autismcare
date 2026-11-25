"""FR 1.2: authentication, 12-character minimum, lockout after 5 failures."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

GOOD_PW = "CorrectHorse-42!"


class RegisterTests(TestCase):
    def setUp(self):
        self.api = APIClient()

    def test_register_creates_user_profile_and_token(self):
        r = self.api.post(reverse("api-register"), {
            "email": "new@example.com", "password": GOOD_PW, "full_name": "New Person", "phone": "0700",
        })
        self.assertEqual(r.status_code, 201, r.data)
        self.assertIn("token", r.data)
        user = get_user_model().objects.get(email="new@example.com")
        self.assertEqual(user.role, "THERAPIST")
        self.assertTrue(hasattr(user, "therapist_profile"))

    def test_password_under_12_characters_rejected(self):
        r = self.api.post(reverse("api-register"), {
            "email": "short@example.com", "password": "Abc-12345!x", "full_name": "S", "phone": "0700",
        })  # 11 characters
        self.assertEqual(r.status_code, 400)
        self.assertIn("password", r.data)
        self.assertFalse(get_user_model().objects.filter(email="short@example.com").exists())

    def test_duplicate_email_rejected(self):
        get_user_model().objects.create_user(email="dup@example.com", password=GOOD_PW)
        r = self.api.post(reverse("api-register"), {
            "email": "DUP@example.com", "password": GOOD_PW, "full_name": "D", "phone": "0700",
        })
        self.assertEqual(r.status_code, 400)


class LockoutTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.user = get_user_model().objects.create_user(email="t@example.com", password=GOOD_PW)

    def login(self, pw):
        return self.api.post(reverse("api-login"), {"email": "t@example.com", "password": pw})

    def test_correct_login_returns_token(self):
        r = self.login(GOOD_PW)
        self.assertEqual(r.status_code, 200)
        self.assertIn("token", r.data)

    def test_locks_after_5_failures_even_with_correct_password(self):
        for _ in range(4):
            self.assertEqual(self.login("wrong-password-x").status_code, 401)
        self.assertEqual(self.login("wrong-password-x").status_code, 423)  # 5th failure locks
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_locked)
        self.assertEqual(self.login(GOOD_PW).status_code, 423)

    def test_success_resets_counter(self):
        for _ in range(4):
            self.login("wrong-password-x")
        self.assertEqual(self.login(GOOD_PW).status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 0)
        self.assertFalse(self.user.is_locked)

    def test_unlock_allows_login(self):
        for _ in range(5):
            self.login("wrong-password-x")
        self.user.refresh_from_db()
        self.user.unlock()
        self.assertEqual(self.login(GOOD_PW).status_code, 200)

    def test_web_login_page_shows_locked_message(self):
        for _ in range(5):
            self.client.post(reverse("login"), {"email": "t@example.com", "password": "wrong-password-x"})
        r = self.client.post(reverse("login"), {"email": "t@example.com", "password": GOOD_PW})
        self.assertContains(r, "locked")

    def test_admin_login_also_respects_lock(self):
        self.user.is_staff = True
        self.user.is_locked = True
        self.user.save()
        self.assertFalse(self.client.login(email="t@example.com", password=GOOD_PW))
