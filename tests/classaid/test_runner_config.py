# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

from pathlib import Path

import pytest

import classaid
from components.classaid_tasks.runner import RunnerConfigError, score_tests
from components.classaid_tasks.runner.types import TestResult as RunTestResult


def t(test_id: str, status: str) -> RunTestResult:
    return RunTestResult(id=test_id, name=test_id, status=status)  # type: ignore[arg-type]


def test_score_spec_example() -> None:
    """ Spec: weights 1, 1, 2; first two pass, third fails -> 2.5 """
    results = [t('T#a', 'passed'), t('T#b', 'passed'), t('T#c', 'failed')]
    assert score_tests(results, {'T#a': 1, 'T#b': 1, 'T#c': 2}) == 2.5


def test_score_all_and_none() -> None:
    weights = {'T#a': 1.0, 'T#b': 3.0}
    assert score_tests([t('T#a', 'passed'), t('T#b', 'passed')], weights) == 5.0
    assert score_tests([t('T#a', 'error'), t('T#b', 'timeout')], weights) == 0.0


def test_score_missing_results_count_as_failed() -> None:
    assert score_tests(None, {'T#a': 1, 'T#b': 1}) == 0.0
    assert score_tests([t('T#a', 'passed')], {'T#a': 1, 'T#b': 1}) == 2.5


def test_score_unweighted_tests_default_to_one() -> None:
    assert score_tests([t('T#a', 'passed'), t('T#b', 'failed')], {}) == 2.5


def test_score_rounds_half_up_to_one_decimal() -> None:
    # 5 * 1/3 = 1.666... -> 1.7 ; 5 * 1/8 = 0.625 -> 0.6
    assert score_tests([t('T#a', 'passed')], {'T#a': 1, 'T#b': 1, 'T#c': 1}) == 1.7
    assert score_tests([t('T#a', 'passed')], {'T#a': 1, 'T#b': 7}) == 0.6


@pytest.mark.parametrize('allow', [None, '', '0'])
def test_local_runner_refused_outside_dev(tmp_path: Path, allow: str | None) -> None:
    """ Spec: a production configuration with the development runner fails to start. """
    with pytest.raises(RunnerConfigError, match='does not isolate student code'):
        classaid.create_app(
            test_config={'TESTING': False, 'CLASSAID_RUNNER': 'local', 'CLASSAID_ALLOW_LOCAL_RUNNER': allow},
            instance_path=tmp_path,
        )


def test_local_runner_allowed_with_flag(tmp_path: Path) -> None:
    app = classaid.create_app(
        test_config={'TESTING': False, 'CLASSAID_RUNNER': 'local', 'CLASSAID_ALLOW_LOCAL_RUNNER': '1'},
        instance_path=tmp_path,
    )
    assert app.config['CLASSAID_RUNNER'] == 'local'


def test_unknown_runner_refused(tmp_path: Path) -> None:
    with pytest.raises(RunnerConfigError, match='Unknown CLASSAID_RUNNER'):
        classaid.create_app(test_config={'TESTING': True, 'CLASSAID_RUNNER': 'chroot'}, instance_path=tmp_path)
