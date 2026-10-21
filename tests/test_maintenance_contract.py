"""V1-MAINTENANCE-01: real API lifetime, bounded jobs and installed read boundaries."""
from pathlib import Path
import hashlib
import json
import sys
import tempfile
import threading
import time
import unittest
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from unittest.mock import patch
from test_report_workspace_contract import WorkspaceService
from report_workspace import CopyAsset, WorkspaceJobs
import agent_readonly
from asset_housekeeping import AssetHousekeeper


class MaintenanceTransactions(WorkspaceService):
    def test_source_contract_never_claims_complete_footnote_preflight(self):
        text='# Report\n\nText[^a]\n\n[^a]: One\n[^a]: Two\n'
        status,result=self.post('/api/validate',{'markdown':text,'render_profile':'engineering'})
        self.assertEqual(status,200,result)
        self.assertTrue(result['source_contract_valid']);self.assertFalse(result['valid'])
        self.assertFalse(result['preflight']['complete'])
        projection=agent_readonly.project(agent_readonly.analyze(text))
        self.assertTrue(projection['sourceContractValid'])
        self.assertFalse(projection['safeToCompile']);self.assertFalse(projection['preflight']['complete'])

    def test_all_reports_paginate_and_reversible_lifecycle_keeps_assets_and_drafts(self):
        ids=[]
        for n in range(33):
            status,result=self.post('/api/report-workspace',{**self.request,'title':'topic '+str(n)})
            self.assertEqual(status,200,result);ids.append(result['document_id'])
        query={**self.request,'action':'list','source_sha256':self.sha(self.full)}
        _,page=self.post('/api/report-workspace',query)
        self.assertEqual(page['total'],33);self.assertEqual(len(page['reports']),30)
        _,second=self.post('/api/report-workspace',{**query,'offset':page['next_offset']})
        self.assertEqual(len(second['reports']),3);self.assertIsNone(second['next_offset'])
        self.assertTrue(all(r['source_current'] for r in page['reports']))
        doc_id=ids[0];project=self.server.project_path(doc_id);original=(project/'report.md').read_bytes()
        draft={'document_id':doc_id,'draft_id':'b'*32,'template':'engineering','seq':1,
               'base_revision':hashlib.sha256(original).hexdigest(),'markdown':'# Changed in draft\n'}
        self.assertEqual(self.post('/api/draft',draft)[0],200)
        action={**self.request,'target_document_id':doc_id,'target_revision':hashlib.sha256(original).hexdigest()}
        self.assertEqual(self.post('/api/report-workspace',{**action,'action':'trash','target_revision':'0'*64})[0],409)
        for name in ('archive','unarchive','trash','restore'):
            status,result=self.post('/api/report-workspace',{**action,'action':name})
            self.assertEqual(status,200,result)
            self.assertTrue(self.server.draft_path('b'*32).is_dir())
        self.assertEqual((project/'report.md').read_bytes(),original)
        _,stale=self.post('/api/report-workspace',{**query,'source_sha256':'0'*64})
        self.assertTrue(all(not r['source_current'] for r in stale['reports']))
        self.assertEqual((self.project/'report.md').read_bytes(),self.full.encode('utf8'))

    def test_slow_copy_does_not_block_other_window_draft_and_cancel_rolls_back(self):
        # An explicit barrier simulates slow disk I/O. Source/snapshot/copy/API
        # and cancellation are genuine; no document API response is mocked.
        raw=b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg>'
        (self.project/'assets').mkdir(exist_ok=True);(self.project/'assets/a.svg').write_bytes(raw)
        text='# Full\n\n![A](assets/a.svg)\n';(self.project/'report.md').write_bytes(text.encode())
        request={**self.request,'full_markdown':text,'source_sha256':self.sha(text),'revision':self.sha(text),'markdown':text,'action':'start'}
        entered=threading.Event();release=threading.Event();copy=CopyAsset.copy_to
        def slow(asset,target):
            entered.set()
            if not release.wait(5):raise RuntimeError('test copy barrier timeout')
            return copy(asset,target)
        with patch.object(CopyAsset,'copy_to',slow):
            status,started=self.post('/api/report-workspace',request);self.assertEqual(status,200,started)
            self.assertTrue(entered.wait(3))
            try:
                before=time.monotonic()
                status,result=self.post('/api/draft',{'document_id':'legacy','draft_id':'c'*32,'template':'engineering','seq':1,
                                                     'base_revision':self.sha(text),'markdown':text+'Another window\n'})
                self.assertEqual(status,200,result);self.assertLess(time.monotonic()-before,2)
                command={**self.request,'action':'cancel','job_token':started['job_token']}
                self.assertEqual(self.post('/api/report-workspace',command)[0],200)
            finally:release.set()
            deadline=time.monotonic()+4
            while time.monotonic()<deadline:
                _,state=self.post('/api/report-workspace',{**command,'action':'status'})
                if state['state']!='running':break
                time.sleep(.02)
            self.assertEqual(state['state'],'cancelled',state)
        self.assertEqual([p.name for p in self.server.workspace.iterdir() if p.is_dir() and len(p.name)==32],[])
        self.assertEqual((self.project/'assets/a.svg').read_bytes(),raw)
        self.assertEqual((self.project/'report.md').read_bytes(),text.encode())
        self.assertTrue(self.server.draft_path('c'*32).is_dir())

    def test_independent_save_is_new_project_and_does_not_rebind_temporary_identity(self):
        _,created=self.post('/api/report-workspace',self.request)
        doc_id=created['document_id'];temporary=self.server.project_path(doc_id)
        target_root=tempfile.TemporaryDirectory();self.addCleanup(target_root.cleanup)
        target_parent=Path(target_root.name)
        selection=self.server.registry.new_selection('create','new',target_parent,'Independent')
        markdown='# Independent\n\nEdited text\n'
        request={'document_id':doc_id,'draft_id':'d'*32,'template':'engineering','revision':self.sha(self.request['markdown']),
                 'markdown':markdown,'action':'save-independent','selection_token':selection['selection_token']}
        status,result=self.post('/api/report-workspace',request);self.assertEqual(status,200,result)
        self.assertNotEqual(result['document_id'],doc_id)
        self.assertEqual(self.server.project_path(doc_id),temporary)
        self.assertEqual((Path(result['project_path'])/'report.md').read_text('utf8'),markdown)
        self.assertNotIn('report_workspace',json.loads((Path(result['project_path'])/'meta.json').read_text('utf8')))
        self.assertEqual((temporary/'report.md').read_bytes(),self.request['markdown'].encode('utf8'))
        self.assertEqual((self.project/'report.md').read_bytes(),self.full.encode('utf8'))


class AssetCleanup(WorkspaceService):
    """ASSET-PURGE-01/EXPORT-FOLDER-01: explicit actions, bounded paths and failure."""
    def setUp(self):
        super().setUp()
        (self.project/'assets').mkdir(exist_ok=True)
        self.doc_id='e'*32;self.server.registry.register(self.doc_id,self.project)
        self.helper=AssetHousekeeper(self.project,self.server.drafts,self.doc_id)
        self.context={'document_id':self.doc_id,'revision':self.sha(self.full)}

    def action(self,endpoint,request,authorized=True):
        headers={'Content-Type':'application/json','Origin':self.url}
        if authorized:headers.update({'X-HRS-Asset-Action':'user-action','X-HRS-Project-Action':'user-action'})
        req=Request(self.url+endpoint,json.dumps(request).encode(),headers,method='POST')
        try:
            with urlopen(req,timeout=5) as response:return response.status,json.load(response)
        except HTTPError as error:return error.code,json.load(error)

    def batch(self,name):
        (self.project/'assets'/name).write_bytes(b'test-owned discarded asset')
        group=next(g for g in self.helper.scan()['groups'] if g['id']==Path(name).stem)
        return self.helper.move_to_trash({group['id']:{f['name']:f['sha256'] for f in group['files']}})['batch_id']

    def scan(self):
        status,result=self.action('/api/project/assets/scan',self.context)
        self.assertEqual(status,200,result);return result

    def purge(self,snapshot,**overrides):
        return self.action('/api/project/assets/purge',{**self.context,'confirmed':True,'trash_revision':snapshot['trash']['revision'],**overrides})

    def test_clear_all_batches_including_beyond_display_limit_preserves_live_files(self):
        for n in range(27):self.batch(f'discard{n}.png')
        restored=self.batch('restored.png');self.helper.restore(restored)
        kept=b'live attachment';(self.project/'assets/keep.png').write_bytes(kept)
        draft=self.server.drafts/('b'*32);draft.mkdir();(draft/'state.json').write_text(json.dumps({'document_id':self.doc_id,'markdown':self.full}),encoding='utf8')
        history=self.project/'.history';history.mkdir();(history/'old.md').write_bytes(b'history')
        snapshot=self.scan();self.assertEqual(len(snapshot['batches']),25)
        self.assertEqual(snapshot['trash']['batch_count'],28);self.assertEqual(snapshot['trash']['file_count'],27)
        status,result=self.purge(snapshot);self.assertEqual(status,200,result);self.assertEqual(result['removed_files'],27)
        self.assertEqual(list((self.project/'.asset-trash').iterdir()),[])
        self.assertEqual((self.project/'assets/keep.png').read_bytes(),kept)
        self.assertTrue((self.project/'assets/restored.png').is_file());self.assertTrue((draft/'state.json').is_file())
        self.assertEqual((history/'old.md').read_bytes(),b'history');self.assertEqual((self.project/'report.md').read_bytes(),self.full.encode('utf8'))

    def test_stale_confirmation_missing_action_and_unknown_paths_are_rejected(self):
        batch=self.batch('discard.png');snapshot=self.scan()
        self.assertEqual(self.purge(snapshot,confirmed=False)[0],400)
        self.assertEqual(self.purge(snapshot,revision='0'*64)[0],409)
        self.assertEqual(self.action('/api/project/assets/purge',{**self.context,'confirmed':True,'trash_revision':snapshot['trash']['revision']},authorized=False)[0],403)
        self.batch('later.png');self.assertEqual(self.purge(snapshot)[0],400)
        fresh=self.scan();unknown=self.project/'.asset-trash'/batch/'assets/unexpected.txt';unknown.write_bytes(b'keep')
        self.assertEqual(self.purge(fresh)[0],400);self.assertTrue(unknown.is_file())
        unknown.unlink();fresh=self.scan()
        path=self.project/'.asset-trash'/batch/'assets/discard.png';path.write_bytes(b'tampered')
        self.assertEqual(self.purge(fresh)[0],400);self.assertTrue(path.exists())

    def test_occupied_file_reports_partial_progress_and_explicit_retry_clears_remainder(self):
        self.batch('first.png');self.batch('discard.png');snapshot=self.scan();unlink=Path.unlink
        # Sorted batch order is intentionally made deterministic for this
        # refusal check: the second file is occupied, the first is removed.
        batches=sorted((self.project/'.asset-trash').iterdir())
        busy=next((batches[1]/'assets').iterdir()).name
        def occupied(path,*args,**kwargs):
            if path.name==busy:raise PermissionError('test occupied file')
            return unlink(path,*args,**kwargs)
        with patch.object(Path,'unlink',occupied):
            status,result=self.purge(snapshot)
        self.assertEqual(status,409,result);self.assertIn('清理未完成',result['error'])
        self.assertIn('已删除 1 个附件',result['error'])
        snapshot=self.scan();self.assertEqual(snapshot['trash']['file_count'],1)
        self.assertEqual(self.purge(snapshot)[0],200)
        self.assertEqual(list((self.project/'.asset-trash').iterdir()),[])

    def test_new_note_or_draft_reference_protects_trashed_assets(self):
        self.batch('discard.png');snapshot=self.scan()
        note=self.project/'notes.md';note.write_text('![Keep](assets/discard.png)',encoding='utf8')
        self.assertEqual(self.purge(snapshot)[0],400);note.unlink()
        draft=self.server.drafts/('b'*32);draft.mkdir();state=draft/'state.json'
        state.write_text(json.dumps({'document_id':self.doc_id,'markdown':'![Keep](assets/discard.png)'}),encoding='utf8')
        self.assertEqual(self.purge(snapshot)[0],400);state.unlink();draft.rmdir()
        self.assertEqual(self.purge(snapshot)[0],200)

    def test_open_folder_uses_only_live_result_token_and_explicit_origin(self):
        output=self.project/'output';output.mkdir(exist_ok=True);target=output/'result.html';target.write_text('test',encoding='utf8')
        token=self.server.word_export.result(target)
        with patch('os.startfile',create=True) as opened:
            self.assertEqual(self.action('/api/export/open-folder',{'result_token':token},authorized=False)[0],403)
            self.assertEqual(self.action('/api/export/open-folder',{'path':str(target),'result_token':'invalid'})[0],400)
            self.assertEqual(self.action('/api/export/open-folder',{'result_token':token})[0],200)
            opened.assert_called_once_with(str(output))
            target.unlink();self.assertEqual(self.action('/api/export/open-folder',{'result_token':token})[0],400)


if __name__=='__main__':unittest.main()
