"""Regression coverage for failures found in the October telemetry review."""
from dataclasses import replace
import json
from pathlib import Path
import time
import urllib.error

import pytest

from jev.adapters import AntigravityAdapter, CodexAdapter, OpenCodeAdapter
from jev.contracts import Event, EventKind, Harness, Operation, Outcome
from jev.core import knowledge, skills, speculative, loop_guard
from jev.install.render import codex_hooks, antigravity_hooks
from jev.runtime import Runtime
from jev.services.client import failure_details
from jev.services.paths import Settings
from jev.services.storage import Storage


class Offline:
    def evaluate(self, *args):
        raise urllib.error.URLError(TimeoutError('handshake timed out token=private'))


def settings(tmp_path):
    return Settings(tmp_path, tmp_path, tmp_path, tmp_path, tmp_path,
                    tmp_path / 'audit.sqlite3', (), ())


def test_global_skill_roots_survive_project_config(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    config = tmp_path / 'config/jev'
    config.mkdir(parents=True)
    (config / 'config.json').write_text(json.dumps({'skill_roots': ['skills']}))
    (tmp_path / '.git').mkdir()
    (tmp_path / 'jev.json').write_text(json.dumps({'skill_roots': ['.agents/skills']}))
    monkeypatch.delenv('JEV_SKILL_ROOTS', raising=False)
    cfg = Settings.load(tmp_path)
    assert cfg.skill_roots == (tmp_path / '.agents/skills', config / 'skills')
    monkeypatch.setenv('JEV_SKILL_ROOTS', str(tmp_path / 'override'))
    assert Settings.load(tmp_path).skill_roots == (tmp_path / 'override',)


@pytest.mark.parametrize('feature', [skills.suggest, knowledge.search])
def test_empty_catalog_is_explicit(feature, tmp_path):
    result = feature('review security', (tmp_path,), Offline(), 0.1)
    assert result.reason_code == 'empty_catalog'
    assert result.data == {'catalog_count': 0, 'provider_status': 'not_called'}


def test_provider_failure_is_visible_without_secrets(tmp_path):
    skill = tmp_path / 'security/SKILL.md'
    skill.parent.mkdir()
    skill.write_text('---\nname: security\ndescription: review security\n---\nReview security.')
    item = tmp_path / 'item/metadata.json'
    item.parent.mkdir()
    item.write_text(json.dumps({'id': 'item', 'summary': 'review security'}))
    results = [skills.suggest('review security', (tmp_path,), Offline(), .1),
               knowledge.search('review security', (tmp_path,), Offline(), .1),
               speculative.evaluate('review security', tmp_path, '', Offline(), .1)]
    for result in results:
        assert result.error == 'URLError'
        assert result.timed_out
        assert result.data['error_category'] == 'timeout'
        assert 'private' not in json.dumps(result.to_dict())
        assert result.outcome == Outcome.ABSTAIN


@pytest.mark.parametrize('adapter,raw', [
    (CodexAdapter(), {'hook_event_name': 'PostToolUse', 'tool_name': 'Bash',
                     'tool_input': {'command': 'python fail.py'}}),
    (AntigravityAdapter(), {'hookEventName': 'PostToolUse',
                           'toolCall': {'name': 'run_command', 'args': {'CommandLine': 'python fail.py'}}}),
    (OpenCodeAdapter(), {'opencode_event': 'tool.execute.after', 'tool': 'bash',
                        'args': {'command': 'python fail.py'}}),
])
def test_native_post_tool_result_reaches_loop_guard(adapter, raw, tmp_path):
    raw = {**raw, 'cwd': str(tmp_path), 'workspacePaths': [str(tmp_path)],
           'session_id': 'session', 'conversationId': 'session',
           'tool_response': {'exit_code': 1}}
    event, operation = adapter.decode(raw)
    cfg = settings(tmp_path)
    runtime = Runtime(cfg, client=Offline())
    for _ in range(3):
        runtime.dispatch(event, operation)
    before = replace(event, kind=EventKind.TOOL_BEFORE)
    assert loop_guard.evaluate_before(before, operation, runtime.storage).outcome == Outcome.DENY
    with runtime.storage.connect() as connection:
        assert connection.execute('select count(*) from tool_invocations').fetchone()[0] == 3
        assert connection.execute("select count(*) from events where reason_code='tool_result_recorded'").fetchone()[0] == 3
    # A different workspace or harness cannot inherit the failures.
    assert loop_guard.evaluate_before(replace(before, workspace_id='elsewhere'), operation, runtime.storage).outcome == Outcome.ABSTAIN
    other = Harness.OPENCODE if event.harness != Harness.OPENCODE else Harness.CODEX
    assert loop_guard.evaluate_before(replace(before, harness=other), operation, runtime.storage).outcome == Outcome.ABSTAIN
    # Explicit success clears the streak, including an exit code of zero.
    runtime.dispatch(replace(event, payload={'exit_code': 0}), operation)
    assert loop_guard.evaluate_before(before, operation, runtime.storage).outcome == Outcome.ABSTAIN


def test_unknown_tool_result_is_not_success(tmp_path):
    event = Event(EventKind.TOOL_AFTER, Harness.CODEX, 'e', 'w', 's', str(tmp_path))
    store = Storage(tmp_path / 'audit.sqlite3')
    result = loop_guard.record_after(event, Operation('shell', 'Bash', 'python fail.py'), store)
    assert result.data['tool_status'] == 'unknown'


def test_injection_counts_survive_context_telemetry(tmp_path):
    cfg = settings(tmp_path)
    skill = tmp_path / 'skills/security/SKILL.md'
    skill.parent.mkdir(parents=True)
    skill.write_text('---\nname: security\ndescription: security review\n---\nReview security.')
    cfg = replace(cfg, skill_roots=(tmp_path / 'skills',), context_budget=20)
    class Client:
        def evaluate(self, state, questions, timeout):
            if 'skill' in questions:
                return {'skill': {'choice': 'security', 'confidence': .95}, 'requires_skill': {'noul': .9}}
            return {}
    event = Event(EventKind.TURN_BEFORE, Harness.ANTIGRAVITY, 'e', 'w', 's', str(tmp_path), {'prompt': 'security review'})
    runtime = Runtime(cfg, client=Client())
    runtime.dispatch(event)
    with runtime.storage.connect() as c:
        data = json.loads(c.execute("select details from events where feature='skills'").fetchone()[0])
    assert data['context_items_proposed'] == 1
    assert data['context_items_injected'] == 1
    assert data['context_chars_injected'] == 20
    assert data['provider_status'] == 'ok'


def test_expired_deadline_is_visible_without_provider_call(tmp_path):
    event = Event(EventKind.TURN_BEFORE, Harness.CODEX, 'e', 'w', 's', str(tmp_path),
                  {'prompt': 'review'}, deadline_monotonic=time.monotonic() - 1)
    runtime = Runtime(settings(tmp_path), client=Offline())
    result = runtime.dispatch(event)
    assert result.timed_out
    with runtime.storage.connect() as c:
        assert {r[0] for r in c.execute('select reason_code from events')} == {'dispatch_deadline_exceeded'}


def test_existing_v4_store_migrates_without_losing_results(tmp_path):
    cfg = settings(tmp_path)
    store = Storage(cfg.db_path)
    store.record_tool_invocation(session_id='existing', workspace_id='workspace',
                                 tool_name='Bash', command='python fail.py', status='failure', exit_code=1)
    with store.connect() as c:
        c.execute('alter table tool_invocations drop column harness')
        c.execute('delete from schema_migrations where version=5')
    store.initialize()
    store.initialize()
    with store.connect() as c:
        assert 'harness' in {r[1] for r in c.execute('pragma table_info(tool_invocations)')}
        assert c.execute('select count(*) from schema_migrations where version=5').fetchone()[0] == 1
        assert c.execute('select status from tool_invocations').fetchone()[0] == 'failure'


def test_generated_and_checked_in_hooks_register_post_tool():
    root = Path(__file__).resolve().parents[1]
    configs = [codex_hooks()['hooks'], antigravity_hooks()['jev-runtime'],
               json.loads((root / '.codex/hooks.json').read_text())['hooks'],
               json.loads((root / '.agents/hooks.json').read_text())['jev-runtime']]
    assert all('PostToolUse' in config for config in configs)


def test_project_skill_shadows_same_named_global_skill(tmp_path):
    for root, description in [('local', 'Project workflow'), ('global', 'Global workflow')]:
        path = tmp_path / root / 'review/SKILL.md'
        path.parent.mkdir(parents=True)
        path.write_text(f'---\nname: review\ndescription: {description}\n---\nInstructions')
    catalog = skills.load_catalog((tmp_path / 'local', tmp_path / 'global'))
    assert len(catalog) == 1
    assert catalog[0].description == 'Project workflow'


def test_opencode_metadata_exit_is_normalized(tmp_path):
    event, _ = OpenCodeAdapter().decode({
        'opencode_event': 'tool.execute.after', 'cwd': str(tmp_path),
        'tool': 'bash', 'args': {'command': 'python fail.py'},
        'tool_response': {'exit': 2},
    })
    assert event.payload['exit_code'] == 2


def test_malformed_provider_response_is_not_reported_as_success(monkeypatch):
    from io import BytesIO
    from jev.services.client import HttpDecisionClient
    monkeypatch.setattr('urllib.request.urlopen', lambda *a, **kw: BytesIO(b'{"answers": {}}'))
    with pytest.raises(ValueError, match='omitted'):
        HttpDecisionClient('private', 'https://example.invalid', 'model').evaluate({}, {'safe': {}}, .1)


def test_http_status_is_safe_to_record():
    error = urllib.error.HTTPError('https://example.invalid?token=private', 429, 'private', {}, None)
    details = failure_details(error)
    assert details['http_status'] == 429
    assert details['error_category'] == 'http'
    assert 'private' not in json.dumps(details)


def test_opencode_plugin_forwards_after_metadata(tmp_path):
    import os
    import shutil
    import subprocess
    if not shutil.which('node'):
        pytest.skip('Node is required for the OpenCode plugin smoke test')
    root = Path(__file__).resolve().parents[1]
    fake = tmp_path / 'jev'
    capture = tmp_path / 'calls.jsonl'
    fake.write_text('#!/usr/bin/python3\nimport json,sys,os\np=json.load(sys.stdin)\nwith open(os.environ["CAPTURE"],"a") as f: f.write(json.dumps(p)+"\\n")\nprint("{}")\n')
    fake.chmod(0o700)
    script = '''
const {default: plugin} = await import(process.env.PLUGIN);
const hooks = await plugin({directory: process.env.WORKSPACE, client: {}});
await hooks['tool.execute.after'](
  {tool: 'bash', sessionID: 's', callID: 'c', args: {command: 'python fail.py'}},
  {title: 'failure', output: 'failed', metadata: {exit: 2}});
'''
    subprocess.run(['node', '--input-type=module', '-e', script], check=True, capture_output=True,
                   env={**os.environ, 'JEV_BIN': str(fake), 'CAPTURE': str(capture),
                        'PLUGIN': str(root / '.agents/opencode/jev-plugin.js'), 'WORKSPACE': str(tmp_path)})
    payload = json.loads(capture.read_text())
    assert payload['opencode_event'] == 'tool.execute.after'
    assert payload['args']['command'] == 'python fail.py'
    assert payload['tool_response']['exit'] == 2


def test_expired_deadline_cannot_skip_deterministic_safety(tmp_path):
    event = Event(EventKind.TOOL_BEFORE, Harness.CODEX, 'e', 'w', 's', str(tmp_path),
                  deadline_monotonic=time.monotonic() - 1)
    operation = Operation('shell', 'Bash', 'git reset --hard HEAD~1')
    result = Runtime(settings(tmp_path), client=Offline()).dispatch(event, operation)
    assert result.outcome == Outcome.DENY
    assert result.reason_code == 'git_hard_reset'


def test_independent_enrichers_do_not_starve_behind_other_requests(tmp_path):
    from threading import Barrier, BrokenBarrierError
    gate = Barrier(3)
    class ConcurrentClient:
        def evaluate(self, state, questions, timeout):
            try:
                gate.wait(timeout=2)
            except BrokenBarrierError:
                pytest.fail('Turn enrichers must reach the provider independently')
            return {}
    skill = tmp_path / 'skills/review/SKILL.md'
    skill.parent.mkdir(parents=True)
    skill.write_text('---\nname: review\ndescription: review code\n---\nReview')
    item = tmp_path / 'knowledge/item/metadata.json'
    item.parent.mkdir(parents=True)
    item.write_text(json.dumps({'id': 'item', 'summary': 'review code'}))
    cfg = replace(settings(tmp_path), skill_roots=(tmp_path / 'skills',),
                  knowledge_roots=(tmp_path / 'knowledge',))
    event = Event(EventKind.TURN_BEFORE, Harness.ANTIGRAVITY, 'e', 'w', 's', str(tmp_path), {'prompt': 'review code'})
    result = Runtime(cfg, client=ConcurrentClient()).dispatch(event)
    assert not result.error
    for feature in ['speculative', 'skills', 'knowledge']:
        assert result.data[feature]['provider_status'] == 'ok'
