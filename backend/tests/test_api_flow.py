"""API 层三口同码 + 配置指纹失效。容器内执行：pytest -q。

用 sqlite 内存库覆盖 get_db，不依赖 Postgres。
"""
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.models import Candidate, Hall, PaperSet


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = TestSession()
    hall = Hall(code="H1", name="一号", rows=3, cols=3, min_manhattan=1,
                blocked_enabled=False, blocked_seats="[]")
    db.add(hall); db.flush()
    p1 = PaperSet(code="A", title="A卷"); p2 = PaperSet(code="B", title="B卷")
    db.add_all([p1, p2]); db.flush()
    for i in range(4):
        db.add(Candidate(hall_id=hall.id, name=f"考{i}", ticket_no=f"T{i}",
                         paper_id=p1.id if i % 2 == 0 else p2.id))
    db.commit()

    def override():
        try:
            yield db
        finally:
            pass
    app.dependency_overrides[get_db] = override
    yield TestClient(app), db, hall.id, p1.id, p2.id
    app.dependency_overrides.clear()


def test_three_endpoints_share_one_list(client):
    c, db, hid, _, _ = client
    plan = c.post(f"/api/seating/run?hall_id={hid}").json()
    assert "issues" in plan and "reason_codes" in plan
    # /stats 必须由同一列表派生
    stats = c.get(f"/api/seating/stats?hall_id={hid}").json()
    assert stats["by_code"] == plan["stats"]["by_code"]
    # /violations 的 issues/unplaced 是同一列表的投影
    v = c.get(f"/api/seating/violations?hall_id={hid}").json()
    assert len(v["issues"]) == len(plan["issues"])
    assert len(v["unplaced"]) == sum(1 for x in plan["issues"] if x["code"] == "unplaced")
    # 只下发统一列表，不再有平行的 violations 旧字段
    assert "violations" not in v


def test_config_change_invalidates_cache_all_three_move(client):
    c, db, hid, p1, p2 = client
    first = c.get(f"/api/seating/latest?hall_id={hid}").json()
    # 改最小距：指纹变化，latest 必须重算而非返回旧缓存
    c.patch(f"/api/halls/{hid}", json={"min_manhattan": 3})
    second = c.get(f"/api/seating/latest?hall_id={hid}").json()
    assert second["config_sig"] != first["config_sig"]
    assert second["stats"]["by_code"] == _count(second["issues"])

    # 启用损坏禁坐：禁坐计数 >0；再关闭必须归 0（冒码则失败）
    c.patch(f"/api/halls/{hid}", json={"blocked_enabled": True, "blocked_seats": [[0, 0]]})
    on = c.get(f"/api/seating/latest?hall_id={hid}").json()
    assert on["stats"]["by_code"]["blocked_seat"] == 1
    c.patch(f"/api/halls/{hid}", json={"blocked_enabled": False})
    off = c.get(f"/api/seating/latest?hall_id={hid}").json()
    assert off["stats"]["by_code"]["blocked_seat"] == 0
    assert not any(i["code"] == "blocked_seat" for i in off["issues"])


def test_paper_change_invalidates_cache(client):
    c, db, hid, p1, p2 = client
    c.post(f"/api/seating/run?hall_id={hid}")
    first = c.get(f"/api/seating/latest?hall_id={hid}").json()
    # 把所有考生套到同一卷
    for cand in db.query(Candidate).all():
        c.patch(f"/api/candidates/{cand.id}", json={"paper_id": p1})
    second = c.get(f"/api/seating/latest?hall_id={hid}").json()
    assert second["config_sig"] != first["config_sig"]
    assert second["stats"]["by_code"] == _count(second["issues"])


def _count(issues):
    out = {}
    for i in issues:
        out[i["code"]] = out.get(i["code"], 0) + 1
    return out
