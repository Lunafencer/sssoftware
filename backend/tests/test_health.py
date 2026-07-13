"""H3：/api/health 深度健康检查——逐项探活 DB / Chroma / DashScope。"""


def test_health_reports_dependencies(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["db"] == "ok"
    assert body["chroma"] == "ok"
    assert body["dashscope"] == "ok"  # stub key 已配置
    assert body["ok"] is True
