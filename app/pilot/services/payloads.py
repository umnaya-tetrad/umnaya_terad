"""Validate raw HTTP bodies with the frozen wire schema before FastAPI coerces them."""
from typing import Annotated

from pydantic import BeforeValidator

from pilot.contracts import Login, PhotoOrder, ReviewWrite, Title, VersionCreate
from pilot.domain.schema import validate


def _validate(name: str):
    return BeforeValidator(lambda payload: validate(payload, name))


LoginBody = Annotated[Login, _validate("Login")]
TitleBody = Annotated[Title, _validate("Title")]
PhotoOrderBody = Annotated[PhotoOrder, _validate("PhotoOrder")]
VersionCreateBody = Annotated[VersionCreate, _validate("VersionCreate")]
ReviewBody = Annotated[ReviewWrite, _validate("ReviewWrite")]
