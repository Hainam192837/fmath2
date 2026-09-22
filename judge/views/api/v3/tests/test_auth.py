import json
import tempfile
from pathlib import Path

import jwt
from django.test import Client, TestCase

from judge.models.tests.util import CommonDataMixin, create_user
from judge.views.api.v3.token import _verify_token

TEST_JWT_PRIVATE_KEY = """-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQCpB/Ye3E5OZ1EG
vNMtohGPu9UbaRGCiHKa5DNgFWHDSYtj3zzgtRHUkupcsolvuU5E6l1bYkOENbPq
lAmkslLQQh3t7O4zh5XTdOdJln6B0p6nocN0l4kDSwY0SyTtGj6llcWBGSsYR+RB
F/yA8WfXDxpb1jDNtwnSpD+DQFydmr47xkqQMKRbPGbmMytCMBjB44mHMtPLyacV
fz60gBXaN/1jNzyr3ZCjgzOgzJFNK9UxQV+rCrFS1M81s9AIlg2HWlhwe/PwT8Ul
ASpw0gD8uTpDL+IY41d0RkOWzq7oBKAF4yf9brbrcI16AeT6CveLG1BmF7PvX3mv
ZdTn436pAgMBAAECggEAAW8b228rCuc9fL0lXYG+fGWvjSf7Cgx2THIbLXmA9tMs
55ABSDbBC/ijHF43ZEdCLrt+R0QyJnD+McNHwanxoeqtrlMQQkeoMb8QJ0OrlxZe
WjW5HsgaVXjReKgajBho56a5ojrAbthNS3AUqFNj+iMaqiTLDTO8VZknIMnu/zdJ
VFq+w5WQ0+AfOWdGciiH6206WK5iceYAwmyLxJcpONvG8xb7BKqPS49XBA/82QNx
Rd3+F+3s9bqLIyux4YzCA4osILUA0FfQFAyssjnuuhANRPhModL/NlrShmOiYfHH
AfB6bODrjz1sHgkX6MwrLH50FVFXReYOS3fdpNORwQKBgQDeGg40KEobaykQ33Kq
QSAFXkKXFuP59GCc0CWZYYKw3IXXS3svoDmXde6np+v3/IirWOayx/QGC+iGXbyS
sSqdcHk6NQoFNzeCT/rOYN86k4GhG3LzJjwOgzs2cOpng7dubds6LY+x3oK6O5lu
RoewEtftFJkQotXdjoCw/e/JtQKBgQDC1FUKSHB5ilfk+o0BQ9YGhEBcYTzWBxbH
xauDplxUaA5S0Nw7QFL0hMUWYHkLCoSko0hGtQleFWzOgBm/h+5mvmQIpb6Vs0fz
s4bv6A/Nx7Ukp+/DnENavIm5tmTYKUrp5Z7IWk1SVE3kEaYv2E+5Wgve0cKCf354
bxgyVDappQKBgEDQT7bOzxmDQx+mZXrjuGl4oWwgBPVraEo6v84r04yzPeefIlq6
ojPd+YA5k7XxnxyJvAEOMtsU3I1hi2cvhmUdbnMbCUqOW4eOuX1CbcJVS23tabUl
Qj9l8oCnoPAGUyBJtMEcjKN2cKXSQKsar/wk85g++5AMROb77/g2kqRFAoGBALDh
Ku+yAoMlqVSWb+ulFatG6FO2aA/70Z+/A077ezmaWt6vBjK43FdoLrJ5FYuDmhcK
srSW6ZFELEtyG246z6Lx2UnMiDHK2VkUNT6bVbXCSN+lo9TYioHXR8aWJAnnuz6M
nFJTQX2sUibsKw+m+AJUERDTKR9m9oAKhFI1CIeNAoGBANcFl+2q/t7qbGpc4UhC
I3xSBuj7Z3BsKsWX9JNNHBfVVciS+Kk3UJPDnJGg0429JA3b5QSm3g0kIW4MpAtU
LB5cau7Z+8teQSGz23VKlwGGOrQEqGFuzIp7URaNYA9cKVFCL7t/SmhQf4N4IgxD
RqopV0kRHqr5y32XNzvnqllo
-----END PRIVATE KEY-----"""

TEST_JWT_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAqQf2HtxOTmdRBrzTLaIR
j7vVG2kRgohymuQzYBVhw0mLY9884LUR1JLqXLKJb7lOROpdW2JDhDWz6pQJpLJS
0EId7ezuM4eV03TnSZZ+gdKep6HDdJeJA0sGNEsk7Ro+pZXFgRkrGEfkQRf8gPFn
1w8aW9YwzbcJ0qQ/g0BcnZq+O8ZKkDCkWzxm5jMrQjAYweOJhzLTy8mnFX8+tIAV
2jf9Yzc8q92Qo4MzoMyRTSvVMUFfqwqxUtTPNbPQCJYNh1pYcHvz8E/FJQEqcNIA
/Lk6Qy/iGONXdEZDls6u6ASgBeMn/W6263CNegHk+gr3ixtQZhez7195r2XU5+N+
qQIDAQAB
-----END PUBLIC KEY-----"""


class APIV3AuthTestCase(CommonDataMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.password = "secret123"
        user = cls.users["normal"]
        user.set_password(cls.password)
        user.save(update_fields=["password"])

        cls.other_password = "secret456"
        cls.other_user = create_user(username="api-v3-other")
        cls.other_user.set_password(cls.other_password)
        cls.other_user.save(update_fields=["password"])

    def setUp(self):
        self.client = Client()

    def _login(self, username="normal", password=None):
        response = self.client.post(
            "/api/v3/auth/login",
            data=json.dumps({"username": username, "password": password or self.password}),
            content_type="application/json",
        )
        return response

    def test_login_returns_token_pair(self):
        response = self._login()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["token_type"], "Bearer")
        self.assertIn("access_token", payload)
        self.assertIn("refresh_token", payload)
        self.assertIn("access_expires_in", payload)
        self.assertIn("refresh_expires_in", payload)
        self.assertIsNotNone(_verify_token(payload["access_token"], expected_type="access"))
        self.assertIsNotNone(_verify_token(payload["refresh_token"], expected_type="refresh"))

    def test_login_signs_token_with_static_public_key_pair(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            private_key_path = Path(temp_dir) / "private.pem"
            public_key_path = Path(temp_dir) / "public.pem"
            private_key_path.write_text(TEST_JWT_PRIVATE_KEY, encoding="utf-8")
            public_key_path.write_text(TEST_JWT_PUBLIC_KEY, encoding="utf-8")

            with self.settings(
                API_JWT_ALGORITHM="RS256",
                API_JWT_PRIVATE_KEY_PATH=str(private_key_path),
                API_JWT_PUBLIC_KEY_PATH=str(public_key_path),
            ):
                response = self._login()

                self.assertEqual(response.status_code, 200)
                access_token = response.json()["access_token"]
                self.assertEqual(jwt.get_unverified_header(access_token)["alg"], "RS256")
                self.assertIsNotNone(_verify_token(access_token, expected_type="access"))
                payload = jwt.decode(access_token, TEST_JWT_PUBLIC_KEY, algorithms=["RS256"])
                self.assertEqual(payload["username"], "normal")

    def test_login_with_invalid_credentials_returns_401(self):
        response = self._login(password="wrong-password")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Invalid credentials"})

    def test_refresh_accepts_body_token(self):
        login_payload = self._login().json()

        response = self.client.post(
            "/api/v3/auth/refresh",
            data=json.dumps({"refresh_token": login_payload["refresh_token"]}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIsNotNone(_verify_token(payload["access_token"], expected_type="access"))
        self.assertIsNotNone(_verify_token(payload["refresh_token"], expected_type="refresh"))

    def test_refresh_accepts_bearer_token(self):
        login_payload = self._login().json()

        response = self.client.post(
            "/api/v3/auth/refresh",
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {login_payload['refresh_token']}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("access_token", response.json())

    def test_refresh_requires_token(self):
        response = self.client.post(
            "/api/v3/auth/refresh",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Refresh token is required"})

    def test_refresh_requires_refresh_token_type(self):
        login_payload = self._login().json()

        response = self.client.post(
            "/api/v3/auth/refresh",
            data=json.dumps({"refresh_token": login_payload["access_token"]}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Invalid or expired refresh token"})

    def test_protected_endpoint_requires_valid_access_token(self):
        response = self.client.get("/api/v3/me")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Invalid or expired access token"})

    def test_me_returns_current_user_for_valid_access_token(self):
        login_payload = self._login().json()

        response = self.client.get(
            "/api/v3/me",
            HTTP_AUTHORIZATION=f"Bearer {login_payload['access_token']}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], "normal")

    def test_logout_blacklists_access_token(self):
        login_payload = self._login().json()
        access_token = login_payload["access_token"]

        response = self.client.post(
            "/api/v3/auth/logout",
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"detail": "Logged out successfully. Provided tokens have been revoked."},
        )
        self.assertIsNone(_verify_token(access_token, expected_type="access"))

    def test_logout_blacklists_refresh_token_when_provided(self):
        login_payload = self._login().json()
        access_token = login_payload["access_token"]
        refresh_token = login_payload["refresh_token"]

        response = self.client.post(
            "/api/v3/auth/logout",
            data=json.dumps({"refresh_token": refresh_token}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {access_token}",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(_verify_token(refresh_token, expected_type="refresh"))

    def test_logout_rejects_refresh_token_from_other_user(self):
        login_payload = self._login().json()
        other_login_payload = self.client.post(
            "/api/v3/auth/login",
            data=json.dumps({"username": self.other_user.username, "password": self.other_password}),
            content_type="application/json",
        ).json()

        response = self.client.post(
            "/api/v3/auth/logout",
            data=json.dumps({"refresh_token": other_login_payload["refresh_token"]}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {login_payload['access_token']}",
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Invalid refresh token"})
