import hashlib
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Candidate, Hall, SeatPlan
from app.services.seat_engine import plan_seating
router = APIRouter(prefix="/seating", tags=["seating"])


def _candidates(db: Session, hall_id: int) -> list[dict]:
    return [{"id": c.id, "name": c.name, "ticket_no": c.ticket_no, "paper_id": c.paper_id}
            for c in db.scalars(
                select(Candidate).where(Candidate.hall_id == hall_id).order_by(Candidate.id)).all()]


def _config_sig(hall: Hall, cands: list[dict]) -> str:
    """对影响三口结果的全部输入取指纹：网格/最小距/禁坐开关/损坏格/考生套卷。"""
    payload = json.dumps({
        "rows": hall.rows, "cols": hall.cols, "min": hall.min_manhattan,
        "blocked_enabled": hall.blocked_enabled,
        "blocked_seats": json.loads(hall.blocked_seats or "[]"),
        "cands": sorted((c["id"], c["paper_id"]) for c in cands),
    }, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _compute(db: Session, hall: Hall) -> dict:
    cands = _candidates(db, hall.id)
    blocked = [tuple(x) for x in json.loads(hall.blocked_seats or "[]")]
    result = plan_seating(hall.rows, hall.cols, hall.min_manhattan, cands,
                          blocked_seats=blocked, blocked_enabled=bool(hall.blocked_enabled))
    result["hall"] = {"id": hall.id, "name": hall.name, "min_manhattan": hall.min_manhattan}
    result["config_sig"] = _config_sig(hall, cands)
    return result


def run_seating(hall_id: int, db: Session) -> dict:
    hall = db.get(Hall, hall_id)
    if not hall:
        raise HTTPException(404, "考室不存在")
    result = _compute(db, hall)
    plan = SeatPlan(hall_id=hall_id, created_at=datetime.utcnow(),
                    result_json=json.dumps(result, ensure_ascii=False),
                    config_sig=result["config_sig"])
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return {"id": plan.id, **result}


@router.post("/run")
def run(hall_id: int = 1, db: Session = Depends(get_db)):
    return run_seating(hall_id=hall_id, db=db)


@router.get("/latest")
def latest(hall_id: int = 1, db: Session = Depends(get_db)):
    hall = db.get(Hall, hall_id)
    if not hall:
        raise HTTPException(404, "考室不存在")
    plan = db.scalars(
        select(SeatPlan).where(SeatPlan.hall_id == hall_id).order_by(SeatPlan.id.desc())).first()
    # 配置（损坏格/套卷/最小距/考生）变更 → 指纹不匹配 → 三口一起重算，禁止读到陈旧口径。
    cands = _candidates(db, hall_id)
    sig = _config_sig(hall, cands)
    if not plan or plan.config_sig != sig:
        return run_seating(hall_id=hall_id, db=db)
    data = json.loads(plan.result_json)
    return {"id": plan.id, **data}


@router.get("/violations")
def violations(hall_id: int = 1, db: Session = Depends(get_db)):
    data = latest(hall_id=hall_id, db=db)
    return {
        "hall_id": hall_id,
        "reason_codes": data.get("reason_codes", {}),
        "issues": data.get("issues", []),
        "unplaced": data.get("unplaced", []),
    }


@router.get("/stats")
def stats(hall_id: int = 1, db: Session = Depends(get_db)):
    data = latest(hall_id=hall_id, db=db)
    return {"hall_id": hall_id, **data.get("stats", {})}
