from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_session

SessionDep = Depends(get_session)
