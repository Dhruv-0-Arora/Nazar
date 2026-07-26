"""The JSON turn protocol between the loop and the model (SPEC section 7.1)."""

import json
import re
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, ValidationError

FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class ProtocolError(Exception):
    """str(e) is fed back to the model verbatim as the parse error."""


class SearchAction(BaseModel):
    op: Literal["search"]
    query: str
    k: int = 5


class ExpandAction(BaseModel):
    op: Literal["expand"]
    chunk_ids: list[str]
    hops: int = 1


class GraphAction(BaseModel):
    op: Literal["graph"]
    delta: dict


Action = Annotated[Union[SearchAction, ExpandAction, GraphAction], Field(discriminator="op")]


class Turn(BaseModel):
    thought: str = ""
    actions: list[Action] = Field(default_factory=list)
    conclude: bool = False


def parse_turn(text: str) -> Turn:
    stripped = FENCE_RE.sub("", text.strip()).strip()
    try:
        raw = json.loads(stripped)
    except json.JSONDecodeError as e:
        raise ProtocolError(f"not valid JSON: {e}") from e
    if not isinstance(raw, dict):
        raise ProtocolError("top level must be a JSON object with keys thought/actions/conclude")
    try:
        return Turn.model_validate(raw)
    except ValidationError as e:
        raise ProtocolError(f"schema violation: {e.errors(include_url=False)}") from e
