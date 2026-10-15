from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session


class ErrorResponse(BaseModel):
    detail: str


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


DatabaseSession = Annotated[Session, Depends(get_session)]
