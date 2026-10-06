import unittest
from httpx import ASGITransport, AsyncClient
from app.main import app

class TestAdminPanel(unittest.IsolatedAsyncioTestCase):
    
    async def test_admin_login_success(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/admin/login",
                json={"username": "krishna", "password": "krishna04@gmail.com"}
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn("token", response.json())

    async def test_admin_login_failure(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/admin/login",
                json={"username": "wrong", "password": "wrong"}
            )
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json()["detail"], "Invalid admin credentials")

    async def test_admin_users_endpoint(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            login_resp = await client.post(
                "/api/admin/login",
                json={"username": "krishna", "password": "krishna04@gmail.com"}
            )
            token = login_resp.json()["token"]
            
            response = await client.get(
                "/api/admin/users",
                headers={"Authorization": f"Bearer {token}"}
            )
            self.assertEqual(response.status_code, 200)
            self.assertIsInstance(response.json(), list)

    async def test_admin_users_unauthorized(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/admin/users")
            self.assertEqual(response.status_code, 401)
            
            response = await client.get(
                "/api/admin/users",
                headers={"Authorization": "Bearer wrong_token"}
            )
            self.assertEqual(response.status_code, 401)

