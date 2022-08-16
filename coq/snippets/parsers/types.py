from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Sequence, Tuple, Union

from std2.itertools import deiter

from ...shared.types import Context


class ParseError(Exception):
    ...


@dataclass(frozen=True)
class Index:
    i: int
    row: int
    col: int


EChar = Tuple[Index, str]


@dataclass(frozen=True)
class ParseInfo:
    visual: str
    clipboard: str
    comment_str: Tuple[str, str]


@dataclass(frozen=False)
class ParserState:
    depth: int


@dataclass(frozen=True)
class ParserCtx(Iterator):
    ctx: Context
    text: str
    info: ParseInfo
    dit: deiter[EChar]
    state: ParserState

    def __iter__(self) -> ParserCtx:
        return self

    def __next__(self) -> EChar:
        return next(self.dit)


@dataclass(frozen=True)
class Unparsed:
    text: str


@dataclass(frozen=True)
class Begin:
    idx: int


@dataclass(frozen=True)
class DummyBegin:
    ...


@dataclass(frozen=True)
class End:
    ...


Token = Union[Unparsed, Begin, DummyBegin, End, str]
TokenStream = Iterator[Token]


@dataclass(frozen=True)
class Region:
    begin: int
    end: int
    text: str


@dataclass(frozen=True)
class Parsed:
    text: str
    cursor: int
    regions: Sequence[Tuple[int, Region]]
