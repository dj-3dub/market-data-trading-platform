"""Ensure isolated experiments report and clean up only their own resources."""
import importlib.util
import json
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('correctness_suite', ROOT / 'scripts/correctness-suite.py')
suite = importlib.util.module_from_spec(spec)
spec.loader.exec_module(suite)

@pytest.mark.parametrize('fail', [False, True])
def test_cleanup_and_report_after_success_or_failure(monkeypatch, fail):
    calls, reports = [], []
    token = 'a' * 12
    expected = json.loads((ROOT / 'fixtures/replay-v1.expected.json').read_text())
    state = dict(expected, Offsets={'correctness-' + token + ':0': 12})
    def command(args, input=None):
        calls.append(args)
        if 'kafka-console-producer' in args and fail:
            raise RuntimeError('publish failed')
        if 'curl' in args:
            return json.dumps({key[:1].lower() + key[1:]: value for key, value in state.items()})
        if 'inspect' in args:
            return '1'
        return ''
    monkeypatch.setattr(sys, 'argv', ['correctness-suite.py', '--boundary', 'before'])
    monkeypatch.setattr(suite, 'command', command)
    monkeypatch.setattr(suite, 'new_report', lambda *args: {'run_id': token, 'passed': False})
    monkeypatch.setattr(suite, 'compose_workload', lambda *args: {})
    monkeypatch.setattr(suite, 'save_report', lambda root, report, name: reports.append((report.copy(), name)))
    if fail:
        with pytest.raises(RuntimeError, match='publish failed'):
            suite.main()
    else:
        suite.main()
    assert reports[0][1] == 'correctness-before'
    assert reports[0][0]['passed'] is (not fail)
    assert ['docker', 'rm', '-f', 'correctness-' + token] in calls
    assert ['docker', 'volume', 'rm', 'correctness-' + token] in calls
    assert any('--delete' in args and args[-1] == 'correctness-' + token for args in calls)
    assert not any('down' in args or 'prune' in args for args in calls)
