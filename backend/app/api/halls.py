import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Hall
router = APIRouter(prefix="/halls", tags=["halls"])


def _serialize(r: Hall) -> dict:
    return {
        "id": r.id, "code": r.code, "name": r.name,
        "rows": r.rows, "cols": r.cols, "min_manhattan": r.min_manhattan,
        "blocked_enabled": r.blocked_enabled,
        "blocked_seats": json.loads(r.blocked_seats or "[]"),
    }


@router.get("")
def list_halls(db: Session = Depends(get_db)):
    return [_serialize(r) for r in db.scalars(select(Hall).order_by(Hall.id)).all()]


class HallUpdate(BaseModel):
    min_manhattan: int | None = None
    blocked_enabled: bool | None = None
    blocked_seats: list[list[int]] | None = None


@router.patch("/{hall_id}")
def update_hall(hall_id: int, body: HallUpdate, db: Session = Depends(get_db)):
    hall = db.get(Hall, hall_id)
    if not hall:
        raise HTTPException(404, "考室不存在")
    if body.min_manhattan is not None:
        if body.min_manhattan < 1:
            raise HTTPException(422, "最小间距必须 ≥ 1")
        hall.min_manhattan = body.min_manhattan
    if body.blocked_enabled is not None:
        hall.blocked_enabled = body.blocked_enabled
    if body.blocked_seats is not None:
        for rc in body.blocked_seats:
            if len(rc) != 2 or not (0 <= rc[0] < hall.rows) or not (0 <= rc[1] < hall.cols):
                raise HTTPException(422, f"损坏格坐标越界: {rc}")
        hall.blocked_seats = json.dumps(body.blocked_seats)
    db.commit()
    db.refresh(hall)
    return _serialize(hall)
