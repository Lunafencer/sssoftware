"""认证相关回归测试：登录、注册角色锁定、token_version 单点登录。"""
import uuid


def test_login_default_admin(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "123456"})
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_wrong_password_rejected(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "wrongpw"})
    assert r.status_code == 401


def test_register_locks_role_to_worker(client):
    """FIX5：注册一律创建员工账户，忽略前端传入的 role 字段。"""
    uname = f"reg_{uuid.uuid4().hex[:8]}"
    r = client.post("/api/auth/register",
                    json={"username": uname, "password": "pass1234", "role": "admin"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["role"] == "worker"  # role 被忽略，强制 worker


def test_token_version_single_sign_on(client):
    """FIX6 第 10 项：第二次登录使第一次的 token 立即失效。"""
    uname = f"sso_{uuid.uuid4().hex[:8]}"
    client.post("/api/auth/register", json={"username": uname, "password": "pass1234"})

    r1 = client.post("/api/auth/login", json={"username": uname, "password": "pass1234"})
    token1 = r1.json()["access_token"]
    assert client.get("/api/auth/me",
                      headers={"Authorization": f"Bearer {token1}"}).status_code == 200

    # 第二次登录 → token_version 递增
    client.post("/api/auth/login", json={"username": uname, "password": "pass1234"})

    # 旧 token 应被拒
    me2 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token1}"})
    assert me2.status_code == 401
