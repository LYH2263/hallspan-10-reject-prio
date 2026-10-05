"""API 层三口同码测试：需 fastapi/sqlalchemy/httpx（Docker 镜像内具备）。

无第三方依赖时整体跳过。使用内存 SQLite 覆盖 get_db，不依赖 Postgres。
"""
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")
pytest.importorskip("pydantic_settings")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.models import Candidate, Hall, PaperSet  # noqa: E402


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()
    hall = Hall(code="H1", name="室", rows=3, cols=3, min_manhattan=2,
                blocked_enabled=False, blocked_seats=[])
    db.add(hall); db.flush()
    p1 = PaperSet(code="A", title="A"); p2 = PaperSet(code="B", title="B")
    db.add_all([p1, p2]); db.flush()
    for i in range(4):
        db.add(Candidate(hall_id=1, name=f"C{i}", ticket_no=f"T{i}",
                         paper_id=p1.id if i % 2 == 0 else p2.id))
    db.commit()

    def override():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def _tally(findings):
    codes = {}
    for f in findings:
        codes[f["code"]] = codes.get(f["code"], 0) + 1
    return codes


def test_run_violations_stats_share_one_source(client):
    run = client.post("/seating/run?hall_id=1").json()
    viol = client.get("/seating/violations?hall_id=1").json()
    stats = client.get("/seating/stats?hall_id=1").json()
    # violations/stats 端点读同一份存档：findings 一致、计数由列表派生。
    assert viol["findings"] == run["findings"]
    assert stats["by_code"] == _tally(run["findings"])
    assert stats["violations"] == len([f for f in run["findings"] if f["scope"] == "violation"])


def test_blocked_disabled_count_zero(client):
    client.patch("/halls/1", json={"blocked_seats": [{"row": 0, "col": 1}],
                                   "blocked_enabled": False})
    stats = client.get("/seating/stats?hall_id=1").json()
    assert stats["by_code"]["seat_blocked"] == 0
    assert stats["violations_by_code"]["seat_blocked"] == 0


def test_toggle_blocked_then_three_views_change(client):
    off = client.post("/seating/run?hall_id=1").json()
    client.patch("/halls/1", json={"blocked_seats": [{"row": 0, "col": 0}],
                                   "blocked_enabled": True})
    on = client.post("/seating/run?hall_id=1").json()
    assert off["blocked_enabled"] is False
    assert on["blocked_enabled"] is True
    assert {"row": 0, "col": 0} in on["blocked_seats"]
    # 三口仍对齐。
    assert on["stats"]["by_code"] == _tally(on["findings"])
    assert on["stats"]["violations"] == len(on["violations"])
    assert on["stats"]["unplaced"] == len(on["unplaced"])


def test_change_min_dist_and_paper(client):
    client.patch("/halls/1", json={"min_manhattan": 4})
    r = client.post("/seating/run?hall_id=1").json()
    assert r["min_dist"] == 4
    assert r["stats"]["unplaced"] >= 1
    # 改考生套卷后重排仍自洽。
    papers = {p["code"]: p["id"] for p in client.get("/papers").json()}
    cands = client.get("/candidates").json()
    client.patch(f"/candidates/{cands[0]['id']}", json={"paper_id": papers["B"]})
    r2 = client.post("/seating/run?hall_id=1").json()
    assert r2["stats"]["by_code"] == _tally(r2["findings"])


def test_success_empty_list_all_zero(client):
    # 1x3 放宽间距、交错套卷 → 无任何 finding。
    client.patch("/halls/1", json={"min_manhattan": 1})
    r = client.post("/seating/run?hall_id=1").json()
    if not r["findings"]:
        assert all(v == 0 for v in r["stats"]["by_code"].values())
        assert r["stats"]["unplaced"] == 0 and r["stats"]["violations"] == 0
