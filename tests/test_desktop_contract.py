"""DESKTOP-01: protect update refusal and original user files, without Electron."""
from pathlib import Path
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import threading
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
import host_services
spec=importlib.util.spec_from_file_location('desktop_update',ROOT/'desktop/update.py')
update=importlib.util.module_from_spec(spec);spec.loader.exec_module(update)


def core(version):
    files={'release.json':json.dumps({'version':version,'package_revision':'R1'}).encode(),
           'host_capabilities.json':b'{"schema":"hrs-host-capabilities-v1","desktop_protocol":1}',
           'web/bridge_model.js':b'same native model','note.txt':'中文\r\n😀\n'.encode()}
    manifest={'version':version,'package_revision':'R1','files':[{'path':n,'bytes':len(b),'sha256':update.digest(b)} for n,b in files.items()]}
    files['MANIFEST.json']=(json.dumps(manifest)+'\n').encode()
    return files


class DesktopUpdate(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'install';self.data=Path(self.temp.name)/'user';self.base=core('1.1.0');self.target=core('1.1.1')
        for n,raw in self.base.items():
            file=self.root/'resources/hrs/app'/n;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(raw)
        self.base_sha=update.digest(self.base['MANIFEST.json']);self.target_sha=update.digest(self.target['MANIFEST.json'])
        (self.root/'DESKTOP_MANIFEST.json').write_text(json.dumps({'schema':'hrs-desktop-layout-v1','protocol':1,'core_manifest_sha256':self.base_sha}))
        support=self.root/'resources/hrs/word_support';support.mkdir()
        (support/'MANIFEST.json').write_text(json.dumps({'browser_model_sha256':update.digest(self.base['web/bridge_model.js'])}))
        self.data.mkdir();(self.data/'草稿.md').write_bytes('不能改\r\n😀'.encode())
        self.package=self.pack()

    def pack(self,extra=None,contract=None):
        package=Path(self.temp.name)/('update-'+str(len(list(Path(self.temp.name).glob('*.zip'))))+'.zip')
        meta={'schema':'hrs-core-update-v1','host_protocol':1,'base_core_sha256':self.base_sha,
              'target_core_sha256':self.target_sha,'target_identity':{'version':'1.1.1','package_revision':'R1'}}
        meta.update(contract or {})
        with zipfile.ZipFile(package,'w') as archive:
            for name,raw in self.target.items():archive.writestr('app/'+name,raw)
            archive.writestr('UPDATE.json',json.dumps(meta))
            for name,raw in (extra or {}).items():archive.writestr(name,raw)
        return package

    def test_reviewed_update_and_rollback_keep_base_and_user_bytes(self):
        original={p.relative_to(self.root).as_posix():p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        plan=update.execute(self.root,self.data,package=self.package,plan_only=True)
        self.assertFalse((self.root/'resources/hrs/active.json').exists())
        update.execute(self.root,self.data,package=self.package,expected_sha=plan['package_sha256'])
        self.assertEqual(update.selected(self.root)[0],self.target_sha)
        update.execute(self.root,self.data,rollback=True)
        self.assertEqual(update.selected(self.root)[0],self.base_sha)
        self.assertEqual((self.data/'草稿.md').read_bytes(),'不能改\r\n😀'.encode())
        self.assertTrue(all((self.root/n).read_bytes()==raw for n,raw in original.items()))

    def test_missing_approval_wrong_base_and_host_protocol_are_rejected(self):
        with self.assertRaises(ValueError):update.execute(self.root,self.data,package=self.package)
        for contract in [{'base_core_sha256':'0'*64},{'host_protocol':2}]:
            with self.assertRaises(ValueError):update.package_plan(self.root,self.pack(contract=contract))
        self.assertFalse((self.root/'resources/hrs/active.json').exists())

    def test_path_collision_traversal_unknown_and_corrupt_files_are_rejected(self):
        for extra in [{'app/../outside':b'x'},{'APP/release.json':b'x'},{'unknown':b'x'},{'app/note.txt':b'corrupt'}]:
            with self.assertRaises(ValueError):update.package_plan(self.root,self.pack(extra=extra))
        self.assertFalse((Path(self.temp.name)/'outside').exists())

    def test_running_service_lock_and_pointer_write_failure_keep_current_core(self):
        sha=update.digest(self.package.read_bytes())
        with update.lock(self.data/'data/.portable-instance.lock'):
            with self.assertRaises(RuntimeError):update.execute(self.root,self.data,package=self.package,expected_sha=sha)
        real=update.os.replace
        def fail_pointer(src,dest):
            if Path(dest).name=='active.json':raise PermissionError('occupied pointer')
            return real(src,dest)
        with patch.object(update.os,'replace',side_effect=fail_pointer):
            with self.assertRaises(PermissionError):update.execute(self.root,self.data,package=self.package,expected_sha=sha)
        self.assertEqual(update.selected(self.root)[0],self.base_sha)
        self.assertFalse(list((self.root/'resources/hrs').glob('*.tmp')))

    def test_stale_update_and_modified_version_are_refused(self):
        sha=update.digest(self.package.read_bytes());update.execute(self.root,self.data,package=self.package,expected_sha=sha)
        with self.assertRaises(ValueError):update.execute(self.root,self.data,package=self.package,expected_sha=sha)
        (_,folder,_)=update.selected(self.root);(folder/'note.txt').write_bytes(b'changed')
        with self.assertRaises(ValueError):update.selected(self.root)


class DesktopPrintCapability(unittest.TestCase):
    def test_parent_loss_releases_only_desktop_lease_and_its_pending_launch(self):
        from portable_sessions import WindowSessions
        life=WindowSessions('test');ticket=life.reserve_launch();desktop=life.join(ticket);browser=life.join()
        server=SimpleNamespace(portable_lifecycle=life,desktop_launch=ticket,desktop_windows={desktop['window']:desktop},desktop_parent_gone=threading.Event())
        host_services.release_desktop_windows(server)
        self.assertTrue(server.desktop_parent_gone.is_set());self.assertEqual(life.summary()['windows'],1)
        life.authenticate(browser)
        with self.assertRaises(ValueError):life.authenticate(desktop)

    def test_browser_path_has_no_desktop_dependency_and_invalid_capability_fails_closed(self):
        with patch.dict(os.environ,{},clear=True):self.assertIsNone(host_services.desktop_bridge())
        for url in ['https://127.0.0.1:1','http://example.com:3','http://127.0.0.1:3/path','http://x@127.0.0.1:3']:
            with patch.dict(os.environ,{'HRS_DESKTOP_BRIDGE':json.dumps({'protocol':1,'url':url,'token':'x'*32})}):
                with self.assertRaises(RuntimeError):host_services.desktop_bridge()


if __name__=='__main__':unittest.main()
