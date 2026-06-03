from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from sqlalchemy import event

logger = logging.getLogger(__name__)
_allowance: ContextVar[int] = ContextVar("n_plus_one_allowance", default=0)


@dataclass
class QueryCount:
    total: int = 0
    selects: int = 0


class NPlusOneDetector:
    def __init__(self, engine, *, threshold: int = 20) -> None:
        self.engine = engine
        self.threshold = threshold
        self.count = QueryCount()
        self.violations: list[str] = []
        self._installed = False

    def __enter__(self) -> NPlusOneDetector:
        event.listen(self.engine, "before_cursor_execute", self._before_cursor_execute)
        self._installed = True
        return self

    def __exit__(self, *_exc) -> None:
        if self._installed:
            event.remove(self.engine, "before_cursor_execute", self._before_cursor_execute)
        self._installed = False

    def assert_within_limit(self) -> None:
        if self.violations:
            raise AssertionError("; ".join(self.violations))

    def _before_cursor_execute(
        self,
        _conn,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ):
        self.count.total += 1
        if not str(statement).lstrip().upper().startswith("SELECT"):
            return
        self.count.selects += 1
        allowed = _allowance.get()
        effective_threshold = self.threshold + allowed
        if self.count.selects == effective_threshold + 1:
            message = (
                f"N+1 detector observed {self.count.selects} SELECT statements "
                f"above threshold {effective_threshold}"
            )
            self.violations.append(message)
            logger.warning(message)


@contextmanager
def allow_multi_query(extra_selects: int):
    token = _allowance.set(_allowance.get() + max(0, extra_selects))
    try:
        yield
    finally:
        _allowance.reset(token)
