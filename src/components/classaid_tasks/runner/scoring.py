# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

from collections.abc import Iterable, Mapping
from decimal import ROUND_HALF_UP, Decimal

from .types import TestResult

MAX_SCORE = 5
DEFAULT_WEIGHT = 1.0


def score_tests(results: Iterable[TestResult] | None, weights: Mapping[str, float]) -> float:
    """ Weighted score on a 0-5 scale, rounded half-up to one decimal place.

    `weights` maps test ids ("TestClass#method") to weights.  The scored tests are
    the union of reported tests and weighted tests: a reported test without a
    configured weight counts with DEFAULT_WEIGHT, and a weighted test missing from
    `results` (e.g., because the code did not compile) counts as not passed.
    """
    results = list(results or [])
    test_ids = {r.id for r in results} | set(weights)
    total = sum(weights.get(test_id, DEFAULT_WEIGHT) for test_id in test_ids)
    if total <= 0:
        return 0.0
    passed_ids = {r.id for r in results if r.status == 'passed'}
    earned = sum(weights.get(test_id, DEFAULT_WEIGHT) for test_id in passed_ids)
    score = Decimal(str(MAX_SCORE * earned / total)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
    return float(score)
