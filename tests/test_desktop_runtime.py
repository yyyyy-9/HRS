"""Explicit DESKTOP-01 real Electron process. No system browser dependency."""
from pathlib import Path
import ctypes
import json
import os
import subprocess
import sys
import time
import unittest
import xml.etree.ElementTree as ET
import zipfile
import shutil
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from project_workspace import ProjectRegistry
from browser_support import artifact_directory


def process_handle(pid):
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD];kernel.WaitForSingleObject.restype=wintypes.DWORD
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.OpenProcess(0x100000,False,pid)
    if not handle:raise ctypes.WinError(ctypes.get_last_error())
    return kernel,handle


class DesktopRuntime(unittest.TestCase):
    def test_native_exe_single_instance_core_update_and_rollback(self):
        """DUAL-RELEASE-01: actual packaged entry and packaged updater, via its own CDP."""
        from playwright.sync_api import sync_playwright
        layout=Path(os.environ['HRS_DESKTOP_LAYOUT']).resolve()
        portable=Path(os.environ['HRS_DESKTOP_PORTABLE']).resolve()
        out=artifact_directory(__file__)/'native-entry';out.mkdir(exist_ok=False)
        state=out/'state';exe=layout/'HRS.exe';events=[]
        managed=layout/'resources/hrs'
        self.assertFalse((managed/'active.json').exists(),'Use a fresh isolated desktop layout for update tests')
        self.assertFalse((managed/'previous.json').exists(),'Use a fresh isolated desktop layout for update tests')
        self.assertFalse((managed/'updates').exists() and any((managed/'updates').iterdir()),'Use a fresh layout without existing update history')
        env={**os.environ,'PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1'};env.pop('ELECTRON_RUN_AS_NODE',None);env.pop('NODE_OPTIONS',None)
        def updater(*args):
            result=subprocess.run([str(layout/'resources/hrs/runtime/python.exe'),'-B',str(layout/'resources/app/update.py'),'--root',str(layout),'--data-dir',str(state),*args],env=env,capture_output=True,encoding='utf8',timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            self.assertEqual(result.returncode,0,result.stderr or result.stdout);return json.loads(result.stdout)
        def start_close(revision,check_second=False):
            active=state/'desktop-profile/DevToolsActivePort';active.unlink(missing_ok=True)
            with (out/('native-'+revision+'.log')).open('wb') as log:
                process=subprocess.Popen([str(exe),'--data-dir='+str(state),'--remote-debugging-port=0','--remote-debugging-address=127.0.0.1'],env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                try:
                    end=time.monotonic()+30
                    while not active.exists() and process.poll() is None and time.monotonic()<end:time.sleep(.1)
                    self.assertTrue(active.is_file(),'Native EXE did not open its own page')
                    port=int(active.read_text().splitlines()[0])
                    with sync_playwright() as playwright:
                        browser=playwright.chromium.connect_over_cdp('http://127.0.0.1:'+str(port))
                        context=browser.contexts[0];page=context.pages[0] if context.pages else context.wait_for_event('page',timeout=30000)
                        page.wait_for_function("window.HRSHost&&document.querySelector('#markdown')?.sourceEditor",timeout=30000)
                        page.wait_for_function("document.querySelector('#release-badge').textContent.includes('R')")
                        health=page.evaluate("fetch('/api/health').then(r=>r.json())");self.assertEqual(health['package_revision'],revision);self.assertTrue(health['desktop'])
                        page.wait_for_function("release=>document.querySelector('#release-badge').textContent===release",arg=health['release'])
                        if check_second:
                            duplicate=subprocess.run([str(exe),'--data-dir='+str(state)],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=12,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                            self.assertEqual(duplicate.returncode,0);self.assertIsNone(process.poll())
                            page.screenshot(path=str(out/'NATIVE_EXE.png'))
                        page.evaluate("document.querySelector('#btn-exit').click()")
                        self.assertEqual(process.wait(timeout=18),0)
                    self.assertFalse((state/'data/.portable-instance.json').exists())
                    events.append({'core_revision':revision,'native_entry':'PASS','single_instance':check_second,'normal_shutdown':'PASS'})
                finally:
                    if process.poll() is None:process.terminate();process.wait(timeout=10)
        start_close('R1',True)
        # A clearly labelled synthetic R2 fixture proves switching core paths;
        # it is not a second product release and never enters delivery packages.
        sys.path.insert(0,str(ROOT/'tools'))
        from build_release import read_zip,validate_manifest,manifest,encoded,write_zip
        from build_desktop import build_update
        target=read_zip(portable);meta=json.loads(target['MANIFEST.json']);identity=json.loads(target['app/release.json']);identity['package_revision']='R2'
        target['app/release.json']=encoded(identity)
        app={n[4:]:raw for n,raw in target.items() if n.startswith('app/') and n!='app/MANIFEST.json'}
        app_meta=manifest(app,'TEST FIXTURE ONLY',meta['generated_utc'],identity);target['app/MANIFEST.json']=encoded(app_meta)
        target.pop('MANIFEST.json');target['MANIFEST.json']=encoded(manifest(target,'TEST FIXTURE ONLY',meta['generated_utc'],identity))
        future=out/'TEST_ONLY_target_portable.zip';write_zip(future,target,'TEST_ONLY',meta['generated_utc'])
        package=out/'TEST_ONLY_core_update.zip';build_update(ROOT,layout,future,package)
        plan=updater('--package',str(package),'--plan');updater('--package',str(package),'--sha256',plan['package_sha256'])
        start_close('R2');updater('--rollback');start_close('R1')
        # Remove only the fixture state created by this case. The delivered base
        # layout must not acquire a synthetic future version or rollback target.
        target_sha=plan['contract']['target_core_sha256'];fixture=managed/'updates'/target_sha
        self.assertTrue(fixture.is_relative_to(managed/'updates'));shutil.rmtree(fixture)
        (managed/'active.json').unlink();(managed/'previous.json').unlink()
        (managed/'.desktop-update.lock').unlink()
        if not any((managed/'updates').iterdir()):(managed/'updates').rmdir()
        (out/'RESULT.json').write_text(json.dumps({'status':'PASS','events':events,'fixture_update_not_a_product_release':True},indent=2)+'\n',encoding='utf8')

    def test_real_host_closing_output_ownership_and_parent_crash(self):
        layout=Path(os.environ.get('HRS_DESKTOP_LAYOUT','__missing__')).resolve()
        electron=Path(os.environ.get('HRS_ELECTRON','__missing__')).resolve()
        if not layout.is_dir() or not electron.is_file():raise RuntimeError('Explicit desktop_runtime needs HRS_DESKTOP_LAYOUT and HRS_ELECTRON')
        out=artifact_directory(__file__);records=[]
        for mode in ['normal','crash']:
            folder=out/mode;folder.mkdir(exist_ok=False)
            project=folder/'工程 中文';(project/'assets').mkdir(parents=True)
            # Reuse shipped icon bytes as a redistributable first-party image fixture.
            (project/'assets/panel.png').write_bytes((ROOT/'app/web/app-icon.png').read_bytes())
            figure={'schema':'report-figure-v1','id':'fig-panel','kind':'image','src':'assets/panel.png','caption':'桌面图片','alt':'HRS 标志'}
            text='# 桌面验收\r\n\r\n## 方法\r\n\r\n正文😀，见 @fig:fig-panel。公式 $\\boldsymbol{k}+\\alpha$，说明[^note]。\r\n\r\n```report-figure\r\n'+json.dumps(figure,ensure_ascii=False)+'\r\n```\r\n\r\n| 内容 | 结果 |\r\n| --- | --- |\r\n| 单核 | 双端 |\r\n\r\n[^note]: 原生脚注。\r\n'
            (project/'report.md').write_bytes(text.encode('utf8'));(project/'meta.json').write_text(json.dumps({'render_profile':'engineering'}))
            state=folder/'state';registry=state/'data/projects';registry.mkdir(parents=True)
            ProjectRegistry(registry).register('e'*32,project)
            config={'layout':str(layout),'state':str(state),'project':str(project),'out':str(folder),'document_id':'e'*32,'mode':mode}
            file=folder/'config.json';file.write_text(json.dumps(config,ensure_ascii=False),encoding='utf8')
            env={**os.environ,'PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1'};env.pop('ELECTRON_RUN_AS_NODE',None);env.pop('NODE_OPTIONS',None)
            with (folder/'electron.log').open('wb') as log:
                process=subprocess.Popen([str(electron),str(ROOT/'tests/desktop_driver.cjs'),'--test-config='+str(file)],env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                peer=None;handle=None
                try:
                    ready=folder/'DESKTOP_READY.json';end=time.monotonic()+50
                    while not ready.exists() and process.poll() is None and time.monotonic()<end:time.sleep(.1)
                    self.assertTrue(ready.is_file(),(folder/'electron.log').read_text('utf8',errors='replace'))
                    start=json.loads(ready.read_text('utf8'));self.assertEqual(start['pid'],process.pid)
                    kernel,handle=process_handle(start['service_pid'])
                    if mode=='crash':
                        ready=folder/'CRASH_READY.json';end=time.monotonic()+50
                        while not ready.exists() and process.poll() is None and time.monotonic()<end:time.sleep(.1)
                        self.assertTrue(ready.is_file(),(folder/'electron.log').read_text('utf8',errors='replace'))
                        process.terminate();process.wait(timeout=10)
                        self.assertEqual(kernel.WaitForSingleObject(handle,25000),0,'Parent crash left an owned process alive')
                        stale=(state/'data/.portable-instance.json').exists()
                        config['mode']='restart';restart=folder/'restart-config.json';restart.write_text(json.dumps(config,ensure_ascii=False),encoding='utf8')
                        with (folder/'restart.log').open('wb') as output:
                            restarted=subprocess.run([str(electron),str(ROOT/'tests/desktop_driver.cjs'),'--test-config='+str(restart)],env=env,stdout=output,stderr=subprocess.STDOUT,timeout=50,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                        self.assertEqual(restarted.returncode,0,(folder/'RESULT.json').read_text('utf8'))
                        self.assertFalse((state/'data/.portable-instance.json').exists())
                        records.append({'mode':mode,'status':'PASS','owned_process_exited':True,'stale_state_after_forced_os_exit':stale,'restart_and_clean_close':True})
                    else:
                        node=os.environ.get('HRS_BRIDGE_NODE') or shutil.which('node')
                        self.assertTrue(node,'Explicit desktop runtime needs Node for a separate protocol peer')
                        peer=subprocess.Popen([node,str(ROOT/'tests/desktop_lease_client.js'),start['url'],str(folder)],env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                        self.assertEqual(process.wait(timeout=240),0,(folder/'RESULT.json').read_text('utf8') if (folder/'RESULT.json').exists() else (folder/'electron.log').read_text('utf8',errors='replace'))
                        result=json.loads((folder/'RESULT.json').read_text('utf8'));self.assertEqual(result['status'],'PASS',result)
                        with urlopen(start['url']+'/api/health',timeout=5) as response:self.assertTrue(json.loads(response.read())['ok'])
                        result['separate_lease_survives_actual_electron_exit']=True
                        (folder/'RELEASE_LEASE.json').write_text('{}');self.assertEqual(peer.wait(timeout=10),0)
                        self.assertEqual(kernel.WaitForSingleObject(handle,25000),0,'Last client left an owned process alive')
                        result['owned_process_exited']=True;result['state_removed']=not (state/'data/.portable-instance.json').exists()
                        self.assertTrue(result['state_removed'])
                        with zipfile.ZipFile(result['word']) as archive:
                            doc=ET.fromstring(archive.read('word/document.xml'));ns={'m':'http://schemas.openxmlformats.org/officeDocument/2006/math','w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                            self.assertTrue(doc.findall('.//m:oMath',ns));self.assertTrue(doc.findall('.//w:footnoteReference',ns))
                            instructions=' '.join(n.text or '' for n in doc.findall('.//w:instrText',ns))+ ' '.join(n.get('{'+ns['w']+'}instr','') for n in doc.findall('.//w:fldSimple',ns))
                            self.assertIn('SEQ',instructions);self.assertIn('REF',instructions)
                        records.append(result)
                finally:
                    if process.poll() is None:process.terminate();process.wait(timeout=10)
                    if peer and peer.poll() is None:
                        (folder/'RELEASE_LEASE.json').write_text('{}')
                        try:peer.wait(timeout=6)
                        except subprocess.TimeoutExpired:peer.terminate();peer.wait(timeout=5)
                    if handle:kernel.CloseHandle(handle)
                    # Failure cleanup is limited to this test's private service;
                    # it does not turn the preceding lifecycle assertion green.
                    runfile=state/'data/.portable-instance.json'
                    if runfile.exists():
                        info=json.loads(runfile.read_text('utf8'))
                        try:
                            request=Request('http://127.0.0.1:'+str(info['port'])+'/api/portable/stop',method='POST',headers={'Content-Type':'application/json'},data=json.dumps({'token':info['token']}).encode())
                            with urlopen(request,timeout=5):pass
                        except OSError:pass
                        end=time.monotonic()+12
                        while runfile.exists() and time.monotonic()<end:time.sleep(.1)
        (out/'RESULT.json').write_text(json.dumps({'status':'PASS','cases':records},ensure_ascii=False,indent=2)+'\n',encoding='utf8')


if __name__=='__main__':unittest.main()
