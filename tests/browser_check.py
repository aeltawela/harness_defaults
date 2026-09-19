"""Exercise the UI against isolated skills."""
from pathlib import Path
import sys
import tempfile
import threading
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright,expect
from harness_defaults.engine import Manager
from harness_defaults.server import create_server

def start(manager):
    server=create_server(manager,0,'browser-test-secret')
    t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
    return server,t,f'http://127.0.0.1:{server.server_port}/#token=browser-test-secret'


def main():
    with tempfile.TemporaryDirectory() as temp,sync_playwright() as pw:
        root=Path(temp);m=Manager(root/'state',root/'home',settle_seconds=0)
        for host,name in [('codex','research-helper'),('qwen','review-helper'),('claude','deploy-helper')]:
            p=m.home/f'.{host}/skills/{name}/SKILL.md';p.parent.mkdir(parents=True);p.write_text(f'---\nname: {name}\ndescription: Helpful workflow\n---\nOriginal body.\n')
        server,t,url=start(m)
        browser=pw.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1280,'height':900});errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(url);page.wait_for_load_state('networkidle')
        expect(page.get_by_role('heading',name='Choose what runs on its own.')).to_be_visible()
        choice=page.get_by_role('checkbox',name='Require explicit invocation for deploy-helper',exact=True)
        expect(choice).to_be_checked();choice.uncheck()
        expect(page.get_by_role('button',name='Save & apply',exact=True)).to_be_enabled()
        page.reload();page.wait_for_load_state('networkidle');expect(choice).not_to_be_checked()
        page.evaluate("window.originalFetch = window.fetch; window.fetch = (...a) => new Promise(resolve => setTimeout(resolve, 500)).then(() => window.originalFetch(...a));")
        page.get_by_role('button',name='Save & apply',exact=True).click()
        expect(choice).to_be_disabled()
        expect(page.get_by_role('button',name='Save & apply',exact=True)).to_be_disabled()
        assert 'disable-model-invocation: false' in (m.home/'.claude/skills/deploy-helper/SKILL.md').read_text()
        page.get_by_role('searchbox').fill('deploy-helper');expect(page.locator('article.skill')).to_have_count(1)
        page.get_by_role('searchbox').fill('nothing matches');expect(page.get_by_role('heading',name='No matching skills')).to_be_visible()
        page.get_by_role('searchbox').fill('')
        page.get_by_role('button',name='Qwen Code 1',exact=True).click();expect(page.locator('article.skill')).to_have_count(1)
        group=page.get_by_role('checkbox',name='Require explicit invocation for Personal skills in Qwen Code',exact=True)
        group.uncheck();expect(page.get_by_role('checkbox',name='Require explicit invocation for review-helper',exact=True)).not_to_be_checked()
        page.get_by_role('button',name='Discard',exact=True).click();expect(page.get_by_role('checkbox',name='Require explicit invocation for review-helper',exact=True)).to_be_checked()
        page.get_by_role('button',name='Export',exact=True).click()
        expect(page.get_by_role('textbox',name='Exported invocation policy')).to_have_value(__import__('re').compile('"schema": 1'))
        page.get_by_role('button',name='Close',exact=True).click()
        page.get_by_role('button',name='Project folders',exact=True).click()
        project=root/'project';project.mkdir()
        page.get_by_role('textbox',name='Project folder path').fill(str(project));page.get_by_role('button',name='Add folder',exact=True).click()
        page.get_by_role('button',name='Done',exact=True).click();page.get_by_role('button',name='Save & apply',exact=True).click()
        expect(page.get_by_role('button',name='Save & apply',exact=True)).to_be_disabled();assert str(project.resolve()) in m.initialize()['projects']
        page.get_by_role('button',name='All environments 3',exact=True).click()
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not errors,errors
        browser.close();server.shutdown();server.server_close();t.join()
        print('Browser checks passed: save, reload recovery, search, filters, group policy, discard, export, project registration, mobile layout, and no page errors.')

if __name__=='__main__':main()
