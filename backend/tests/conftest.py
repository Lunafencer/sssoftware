"""pytest 公共夹具。

关键：在 `import app.*` 之前注入测试环境变量，避免
- JWT_SECRET 默认值触发 SystemExit（C1）
- 污染本机 loongchip.db / chroma_db / uploads
DashScope 用 stub key——不发起真实计费调用；触达 LLM 的路径由各测试自行 mock 或跳过。
"""
import os
import pathlib
import tempfile

_TMP = pathlib.Path(tempfile.gettempdir()) / "loongchip_pytest"
_TMP.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("ALLOW_INSECURE_JWT", "true")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("DASHSCOPE_API_KEY", "stub-test-key")
os.environ.setdefault("DB_URL", f"sqlite:///{(_TMP / 'test.db').as_posix()}")
os.environ.setdefault("CHROMA_DIR", str(_TMP / "chroma"))
os.environ.setdefault("UPLOAD_DIR", str(_TMP / "uploads"))

# 清掉旧测试库，保证 create_all 重建干净 schema
_db_file = _TMP / "test.db"
if _db_file.exists():
    _db_file.unlink()

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


def _login(client, username: str = "admin", password: str = "123456") -> str:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture()
def admin_token(client) -> str:
    return _login(client)


@pytest.fixture()
def worker_token(client) -> str:
    """注册一个新员工并返回其 token（worker 上传落 pending，不会触发 DashScope 入库）。"""
    import uuid
    uname = f"worker_{uuid.uuid4().hex[:8]}"
    r = client.post("/api/auth/register", json={"username": uname, "password": "pass1234"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
