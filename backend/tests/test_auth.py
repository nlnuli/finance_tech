from datetime import datetime
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pymysql.err import IntegrityError

from app import auth
from app.schemas import AuthRequest, LoginRequest
from app.security import hash_password


def make_user(password: str = "correct-password") -> dict:
    now = datetime.now()
    return {
        "id": "user-1",
        "email": "analyst@example.com",
        "display_name": "Analyst",
        "password_hash": hash_password(password),
        "created_at": now,
        "updated_at": now,
    }


class AuthRouteTests(unittest.TestCase):
    def test_register_normalizes_email_and_returns_token(self):
        user = make_user()
        with (
            patch.object(auth.storage, "create_user", return_value=user) as create_user,
            patch.object(auth, "create_access_token", return_value="token"),
        ):
            response = auth.register(
                AuthRequest(
                    email=" Analyst@Example.com ",
                    password="new-password",
                    display_name="Analyst",
                )
            )

        create_user.assert_called_once_with(
            email="analyst@example.com",
            password="new-password",
            display_name="Analyst",
        )
        self.assertEqual(response["access_token"], "token")
        self.assertEqual(response["user"]["email"], "analyst@example.com")

    def test_register_rejects_duplicate_email(self):
        with patch.object(
            auth.storage,
            "create_user",
            side_effect=IntegrityError("duplicate"),
        ):
            with self.assertRaises(HTTPException) as raised:
                auth.register(
                    AuthRequest(
                        email="analyst@example.com",
                        password="new-password",
                    )
                )

        self.assertEqual(raised.exception.status_code, 409)

    def test_login_rejects_wrong_password(self):
        with patch.object(auth.storage, "get_user_by_email", return_value=make_user()):
            with self.assertRaises(HTTPException) as raised:
                auth.login(
                    LoginRequest(
                        email="analyst@example.com",
                        password="wrong-password",
                    )
                )

        self.assertEqual(raised.exception.status_code, 401)

    def test_current_user_loads_user_from_token_subject(self):
        user = make_user()
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="token",
        )
        with (
            patch.object(auth, "decode_access_token", return_value={"sub": "user-1"}),
            patch.object(auth.storage, "get_user", return_value=user),
        ):
            self.assertEqual(auth.current_user(credentials), user)


if __name__ == "__main__":
    unittest.main()
