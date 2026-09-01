"""A string wrapper that cannot leak through repr, str, or f-strings.

Non-leakage is structural, not a convention: the raw value is reachable only
through the explicit ``reveal()`` accessor, which is called in exactly one
place - the engine's decrypt/encrypt calls. The logging layer additionally
scrubs registered secret values from every record as defense in depth.
"""

from __future__ import annotations


class Secret:
    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "***"

    def __str__(self) -> str:
        return "***"

    def __bool__(self) -> bool:
        return bool(self._value)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Secret) and other._value == self._value

    def __hash__(self) -> int:
        return hash(self._value)
