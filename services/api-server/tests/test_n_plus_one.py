import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.n_plus_one_detector import NPlusOneDetector, allow_multi_query


def test_n_plus_one_detector_fails_above_select_threshold(db_session: Session) -> None:
    engine = db_session.get_bind()

    with pytest.raises(AssertionError, match="N\\+1 detector observed"):
        with NPlusOneDetector(engine, threshold=2) as detector:
            for _ in range(3):
                db_session.execute(text("SELECT 1")).scalar_one()
            detector.assert_within_limit()


def test_n_plus_one_detector_allows_declared_multi_query(db_session: Session) -> None:
    engine = db_session.get_bind()

    with NPlusOneDetector(engine, threshold=2) as detector:
        with allow_multi_query(2):
            for _ in range(4):
                db_session.execute(text("SELECT 1")).scalar_one()
        detector.assert_within_limit()
