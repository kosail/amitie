import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app
from auth.passwords import hash_password, verify_password
from config import Settings
from db.local_sqlite import LocalSQLiteDatabase
from db.schema import apply_schema
from db.seed import seed
from providers.base import LLMResult, Usage


class NullProvider:
    name = "null"
    model = "null"

    async def generate(self, messages, tools=None, response_schema=None, temperature=None, max_tokens=None):
        return LLMResult(text="", tool_calls=(), usage=Usage(0, 0, 0), provider="null", model="null")


class PasswordHashingTest(unittest.TestCase):
    def test_verify_accepts_correct_password(self) -> None:
        password_hash, salt = hash_password("demo1234")
        self.assertTrue(verify_password("demo1234", password_hash, salt))

    def test_verify_rejects_wrong_password(self) -> None:
        password_hash, salt = hash_password("demo1234")
        self.assertFalse(verify_password("not-it", password_hash, salt))

    def test_same_password_different_salts_yields_different_hashes(self) -> None:
        hash_a, salt_a = hash_password("demo1234")
        hash_b, salt_b = hash_password("demo1234")
        self.assertNotEqual(salt_a, salt_b)
        self.assertNotEqual(hash_a, hash_b)


def _seed(path: str) -> None:
    import asyncio

    async def run() -> None:
        database = LocalSQLiteDatabase(path)
        await apply_schema(database)
        await seed(database)
        await database.close()

    asyncio.run(run())


class LoginEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self._tmp.name) / "auth.sqlite3")
        _seed(self.db_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _app(self):
        return create_app(provider=NullProvider(), settings=Settings(database_path=self.db_path))

    def test_login_succeeds_with_seeded_demo_credentials(self) -> None:
        with TestClient(self._app()) as client:
            response = client.post("/api/login", json={"username": "demo", "password": "demo1234"})
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["user_id"], "u_ana")
            self.assertEqual(body["username"], "demo")
            self.assertIsNone(body["accessibility_mode"])
            self.assertTrue(body["session_id"].startswith("sess_"))

    def test_login_succeeds_with_seeded_accessible_persona(self) -> None:
        with TestClient(self._app()) as client:
            response = client.post(
                "/api/login", json={"username": "accesible", "password": "demo1234"}
            )
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["user_id"], "u_don")
            self.assertEqual(body["accessibility_mode"], "low_literacy")

    def test_login_rejects_wrong_password(self) -> None:
        with TestClient(self._app()) as client:
            response = client.post("/api/login", json={"username": "demo", "password": "wrong"})
            self.assertEqual(response.status_code, 401)

    def test_login_rejects_unknown_username(self) -> None:
        with TestClient(self._app()) as client:
            response = client.post(
                "/api/login", json={"username": "no-existe", "password": "demo1234"}
            )
            self.assertEqual(response.status_code, 401)

    def test_login_is_case_insensitive_on_username(self) -> None:
        with TestClient(self._app()) as client:
            response = client.post("/api/login", json={"username": "DEMO", "password": "demo1234"})
            self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
