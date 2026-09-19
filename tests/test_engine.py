from pathlib import Path
import json
import pytest
from harness_defaults.engine import Manager


def skill(root, host='codex', name='example', text=None):
    base = root / {'codex':'.codex','qwen':'.qwen','claude':'.claude'}[host] / 'skills' / name
    base.mkdir(parents=True, exist_ok=True)
    p=base/'SKILL.md'
    p.write_text(text or f'---\nname: {name}\ndescription: A useful task\n---\n\nKeep this body exactly.\n')
    return p

@pytest.fixture
def mgr(tmp_path):
    return Manager(tmp_path/'state', tmp_path/'home', settle_seconds=0)


def test_explicit_default_preserves_codex_metadata_and_is_idempotent(mgr):
    p=skill(mgr.home)
    target=p.parent/'agents/openai.yaml';target.parent.mkdir()
    target.write_text('# keep comment\ninterface:\n  display_name: "My name"\npolicy:\n  products: [codex]\n')
    out=mgr.reconcile(); assert out['changed']==1
    assert 'allow_implicit_invocation: false' in target.read_text()
    assert '# keep comment' in target.read_text() and 'products: [codex]' in target.read_text()
    before=target.stat().st_mtime_ns
    assert mgr.reconcile()['changed']==0
    assert target.stat().st_mtime_ns==before

@pytest.mark.parametrize('host',['qwen','claude'])
def test_frontmatter_and_body_preserved(mgr,host):
    p=skill(mgr.home,host,text='---\nname: example\ndescription: "Quoted" # keep\n---\n\nBody\n---\nStill body.\n')
    mgr.reconcile()
    assert 'disable-model-invocation: true' in p.read_text()
    assert p.read_text().endswith('\n\nBody\n---\nStill body.\n')
    assert '# keep' in p.read_text()


def test_core_snapshot_does_not_allow_future_system_skills(mgr):
    p=skill(mgr.home,name='.system/core')
    mgr.initialize()
    other=skill(mgr.home,name='.system/new')
    mgr.reconcile()
    assert 'allow_implicit_invocation: true' in (p.parent/'agents/openai.yaml').read_text()
    assert 'allow_implicit_invocation: false' in (other.parent/'agents/openai.yaml').read_text()


def test_policy_precedence_and_stale_revision(mgr):
    skill(mgr.home)
    s=mgr.snapshot(); row=s['skills'][0]
    s=mgr.update(s['policy']['revision'],groups={row['group']:False})
    assert mgr.snapshot()['skills'][0]['explicit'] is False
    mgr.update(s['revision'],skills={row['id']:True})
    assert mgr.snapshot()['skills'][0]['explicit'] is True
    with pytest.raises(ValueError,match='changed'):mgr.update(0,skills={row['id']:False})


def test_restore_original_and_do_not_clobber_external_changes(mgr):
    p=skill(mgr.home,'qwen'); original=p.read_bytes()
    mgr.reconcile(); assert mgr.restore()['restored']==1
    assert p.read_bytes()==original
    mgr.update(mgr.snapshot()['policy']['revision'],paused=False)
    mgr.reconcile();p.write_text(p.read_text()+'Vendor change\n')
    result=mgr.restore()
    assert result['conflicts'] and p.read_text().endswith('Vendor change\n')


def test_restore_removed_new_metadata_file(mgr):
    p=skill(mgr.home);mgr.reconcile()
    assert mgr.restore()['restored']==1
    assert not (p.parent/'agents/openai.yaml').exists()


def test_vendor_update_becomes_new_restore_baseline(mgr):
    p=skill(mgr.home,'claude');mgr.reconcile()
    vendor='---\nname: example\ndescription: Updated\n---\nVendor body\n'
    p.write_text(vendor);mgr.reconcile();mgr.restore()
    assert p.read_text()==vendor


def test_invalid_yaml_is_visible_and_untouched(mgr):
    p=skill(mgr.home,'qwen',text='---\nname: [broken\n---\nbody\n')
    original=p.read_bytes();r=mgr.reconcile()
    assert r['errors'] and p.read_bytes()==original


def test_user_hidden_skill_is_reported_not_silently_reenabled(mgr):
    p=skill(mgr.home,'claude',text='---\nname: example\nuser-invocable: false\n---\nbody\n')
    mgr.reconcile()
    assert 'user-invocable: false' in p.read_text()
    assert any('user-invocable' in x for x in mgr.snapshot()['skills'][0]['warnings'])


def test_shared_frontmatter_conflict_is_not_written(mgr):
    p=skill(mgr.home,'qwen');link=mgr.home/'.claude/skills/example'
    link.parent.mkdir(parents=True);link.symlink_to(p.parent,target_is_directory=True)
    rows=mgr.snapshot()['skills']; claude=next(r for r in rows if r['host']=='claude')
    mgr.update(0,skills={claude['id']:False})
    original=p.read_bytes();r=mgr.reconcile()
    assert r['errors'] and p.read_bytes()==original


def test_versions_share_identity_and_ignore_compatibility_subtree(mgr):
    for version in ['1.0','2.0']:
        root=mgr.home/'.codex/plugins/cache/store/plugin'/version
        (root/'.codex-plugin').mkdir(parents=True)
        (root/'.codex-plugin/plugin.json').write_text(json.dumps({'name':'plugin','skills':'./skills/'}))
        for folder in ['skills/a','.cursor/skills/a']:
            p=root/folder/'SKILL.md';p.parent.mkdir(parents=True);p.write_text('---\nname: a\n---\nBody\n')
    rows=mgr.snapshot()['skills'];assert len(rows)==1 and len(rows[0]['files'])==2
    mgr.update(0,skills={rows[0]['id']:False});assert mgr.reconcile()['changed']==2


def test_directly_installed_codex_marketplace_plugin_is_explicit_by_default(mgr):
    root=mgr.home/'.codex/plugins/marketplace-plugin/skills/review'
    root.mkdir(parents=True)
    skill_file=root/'SKILL.md';skill_file.write_text('---\nname: review\n---\nBody\n')
    snapshot=mgr.snapshot();row=next(r for r in snapshot['skills'] if r['name']=='review')
    assert row['group'].endswith('marketplace-plugin') and row['explicit'] is True
    assert mgr.reconcile()['changed']==1
    assert 'allow_implicit_invocation: false' in (root/'agents/openai.yaml').read_text()


def test_policy_validation_rejects_non_boolean(mgr):
    skill(mgr.home);s=mgr.snapshot()
    with pytest.raises(ValueError):mgr.update(0,skills={s['skills'][0]['id']:'false'})


def test_project_roots_register_all_three_hosts(mgr,tmp_path):
    project=tmp_path/'project';project.mkdir()
    for host in ['codex','qwen','claude']:skill(project,host)
    mgr.update(0,projects=[str(project)])
    assert {s['host'] for s in mgr.snapshot()['skills']}=={'codex','qwen','claude'}


def test_claude_declared_commands_replace_default_and_allow_files(mgr):
    root=mgr.home/'.claude/plugins/cache/store/toolkit/1.0'
    (root/'.claude-plugin').mkdir(parents=True)
    (root/'.claude-plugin/plugin.json').write_text(json.dumps({'name':'toolkit','commands':['./custom/review.md','./other']}))
    for name in ['custom/review.md','other/deploy.md','commands/ignored.md']:
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('A command with no frontmatter.\n')
    rows=mgr.snapshot()['skills']
    assert {r['name'] for r in rows}=={'review','deploy'}
    assert mgr.reconcile()['changed']==2
    assert 'disable-model-invocation: true' in (root/'custom/review.md').read_text()
    assert (root/'commands/ignored.md').read_text()=='A command with no frontmatter.\n'


def test_claude_single_root_skill_fallback(mgr):
    root=mgr.home/'.claude/plugins/cache/store/single/1.0'
    (root/'.claude-plugin').mkdir(parents=True)
    (root/'.claude-plugin/plugin.json').write_text('{"name":"single"}')
    (root/'SKILL.md').write_text('---\nname: root-skill\n---\nbody\n')
    assert len(mgr.snapshot()['skills'])==1
    assert mgr.reconcile()['changed']==1


def test_can_clear_persisted_override_for_temporarily_missing_skill(mgr):
    p=skill(mgr.home,'qwen');s=mgr.snapshot();sid=s['skills'][0]['id']
    mgr.update(0,skills={sid:False});p.unlink()
    mgr.update(1,skills={sid:None})
    skill(mgr.home,'qwen')
    assert mgr.snapshot()['skills'][0]['explicit'] is True
