import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Candidate, Hall, SeatPlan
from app.services.seat_engine import build_plan, EngineError

router = APIRouter(prefix="/seating", tags=["seating"])


def _load_hall(hall_id: int, db: Session) -> Hall:
    hall = db.get(Hall, hall_id)
    if not hall:
        raise HTTPException(404, "考室不存在")
    return hall


def _run(hall: Hall, db: Session) -> dict:
    cands = [
        {"id": c.id, "name": c.name, "ticket_no": c.ticket_no, "paper_id": c.paper_id}
        for c in db.scalars(select(Candidate).where(Candidate.hall_id == hall.id)).all()
    ]
    try:
        result = build_plan(
            hall.rows, hall.cols, hall.min_manhattan, cands,
            blocked_seats=hall.blocked_seats or [],
            blocked_enabled=bool(hall.blocked_enabled),
        )
    except EngineError as exc:  # 三口对不齐 / 冒码 → 整场失败
        raise HTTPException(500, f"排座整场失败：{exc}")
    result["hall"] = {
        "id": hall.id, "name": hall.name, "min_manhattan": hall.min_manhattan,
        "blocked_enabled": bool(hall.blocked_enabled),
    }
    plan = SeatPlan(hall_id=hall.id, created_at=datetime.utcnow(),
                    result_json=json.dumps(result, ensure_ascii=False))
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return {"id": plan.id, **result}


@router.post("/run")
def run_seating(hall_id: int = 1, db: Session = Depends(get_db)):
    return _run(_load_hall(hall_id, db), db)


def _latest_data(hall: Hall, db: Session) -> dict:
    plan = db.scalars(
        select(SeatPlan).where(SeatPlan.hall_id == hall.id).order_by(SeatPlan.id.desc())
    ).first()
    if not plan:
        return _run(hall, db)
    return {"id": plan.id, **json.loads(plan.result_json)}


@router.get("/latest")
def latest(hall_id: int = 1, db: Session = Depends(get_db)):
    return _latest_data(_load_hall(hall_id, db), db)


@router.get("/violations")
def violations(hall_id: int = 1, db: Session = Depends(get_db)):
    # 直接返回唯一真相及其派生视图，端点不另算一套。
    data = _latest_data(_load_hall(hall_id, db), db)
    return {
        "hall_id": hall_id,
        "findings": data.get("findings", []),
        "violations": data.get("violations", []),
        "unplaced": data.get("unplaced", []),
        "reason_codes": data.get("reason_codes", {}),
        "violations_by_code": data.get("stats", {}).get("violations_by_code", {}),
    }


@router.get("/stats")
def stats(hall_id: int = 1, db: Session = Depends(get_db)):
    # 分类计数必须来自 findings 派生结果（build_plan 已自检）。
    data = _latest_data(_load_hall(hall_id, db), db)
    return {"hall_id": hall_id, **data.get("stats", {}),
            "reason_codes": data.get("reason_codes", {})}
