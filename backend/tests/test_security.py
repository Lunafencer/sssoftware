"""安全相关回归测试：C1 JWT 强制 / C2 路径穿越 / C5 口令重置。"""
import os
import sys
import subprocess
import uuid


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_default_jwt_secret_refuses_to_start(tmp_path):
    """C1：JWT_SECRET 为默认值且未显式放行时，进程必须拒绝启动。"""
    env = dict(os.environ)
    env.update({
        "JWT_SECRET": "change-me-in-prod",
        "ALLOW_INSECURE_JWT": "false",
        "DEBUG": "false",
        "DASHSCOPE_API_KEY": "stub",
        "DB_URL": f"sqlite:///{(tmp_path / 't.db').as_posix()}",
        "CHROMA_DIR": str(tmp_path / "chroma"),
        "UPLOAD_DIR": str(tmp_path / "uploads"),
    })
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env["PYTHONPATH"] = backend_dir
    result = subprocess.run(
        [sys.executable, "-c", "import app.core.config"],
        cwd=backend_dir, env=env, capture_output=True, text=True,
    )
    assert result.returncode != 0, "默认 JWT_SECRET 不应允许启动"
    assert "JWT_SECRET" in result.stderr


def test_upload_sanitizes_path_traversal(client, worker_token):
    """C2：file.filename 含 ../ 或绝对路径时，仅取 basename 落盘。"""
    malicious = "../../etc/evil.txt"
    files = {"file": (malicious, b"hello world", "text/plain")}
    r = client.post("/api/kb/upload", files=files, data={"category": "manual"},
                    headers=_auth(worker_token))
    assert r.status_code == 200, r.text
    doc_id = r.json()["doc_id"]

    from app.core.db import SessionLocal
    from app.core.config import settings
    from app.models import Document
    db = SessionLocal()
    try:
        d = db.query(Document).get(doc_id)
        assert d.file_path is not None
        # 必须落在 UPLOAD_DIR 之下，且不含 ..
        assert ".." not in os.path.relpath(d.file_path, settings.UPLOAD_DIR)
        assert os.path.basename(d.file_path) == "evil.txt"
        assert os.path.exists(d.file_path)
    finally:
        db.close()


def test_reset_password_is_random_one_time(client, admin_token):
    """C5：重置口令为随机一次性值，不再是通用 123456。"""
    uname = f"reset_{uuid.uuid4().hex[:8]}"
    r = client.post("/api/auth/register", json={"username": uname, "password": "pass1234"})
    assert r.status_code == 200

    users = client.get("/api/admin/users", headers=_auth(admin_token)).json()
    uid = next(u["id"] for u in users if u["username"] == uname)

    r = client.put(f"/api/admin/users/{uid}/reset-password", headers=_auth(admin_token))
    assert r.status_code == 200, r.text
    new_pw = r.json()["password"]
    assert new_pw != "123456"
    assert len(new_pw) >= 8

    # 一次性口令应能登录
    login = client.post("/api/auth/login", json={"username": uname, "password": new_pw})
    assert login.status_code == 200
