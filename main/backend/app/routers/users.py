from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.weakness_analysis import get_recurring_weaknesses
from app.db.database import get_db
from app.db.models import User

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me/weaknesses")
def recurring_weaknesses(
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
) -> dict:
    return {"items": get_recurring_weaknesses(user.id, db)}
