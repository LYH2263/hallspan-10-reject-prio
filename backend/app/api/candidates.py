from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Candidate, PaperSet
router = APIRouter(prefix="/candidates", tags=["candidates"])


def _serialize(r: Candidate) -> dict:
    return {"id": r.id, "hall_id": r.hall_id, "name": r.name,
            "ticket_no": r.ticket_no, "paper_id": r.paper_id}


@router.get("")
def list_candidates(db: Session = Depends(get_db)):
    return [_serialize(r) for r in db.scalars(select(Candidate).order_by(Candidate.id)).all()]


class CandidateUpdate(BaseModel):
    paper_id: int | None = None


@router.patch("/{candidate_id}")
def update_candidate(candidate_id: int, body: CandidateUpdate, db: Session = Depends(get_db)):
    cand = db.get(Candidate, candidate_id)
    if not cand:
        raise HTTPException(404, "考生不存在")
    if body.paper_id is not None:
        if not db.get(PaperSet, body.paper_id):
            raise HTTPException(422, "试卷套不存在")
        cand.paper_id = body.paper_id
    db.commit()
    db.refresh(cand)
    return _serialize(cand)
