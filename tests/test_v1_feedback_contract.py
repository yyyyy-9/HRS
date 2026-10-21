
"""V1-FEEDBACK-01: reviewed origin sync, UTF-16 ranges, assets and refusal."""
from pathlib import Path
import json
from test_report_workspace_contract import WorkspaceService
from test_notebook_browser import png

class OriginSync(WorkspaceService):
    def setUp(self):
        super().setUp()
        self.full='# Keep😀\r\n\r\nAlpha\r\n\r\n[^n]: Original note\r\n\r\n[ref]: https://example.org\r\n\r\n# Report\r\n\r\nTarget[^n] [site][ref].\r\n\r\n# Keep2\r\n\r\nOmega\r\n'
        (self.project/'report.md').write_bytes(self.full.encode('utf8'))
        self.a=self.full.index('# Report');self.b=self.full.index('# Keep2')
        def part(kind,key,start,end):return {'kind':kind,'key':key,'start':self.units(self.full[:start]),'end':self.units(self.full[:end])}
        n=self.full.index('[^n]:');l=self.full.index('[ref]:')
        self.deps=[part('footnote','n',n,self.full.index('\r\n\r\n',n)+2),part('link','ref',l,self.full.index('\r\n\r\n',l)+2)]
        self.mapping={'start':self.units(self.full[:self.a]),'end':self.units(self.full[:self.b]),'dependencies':self.deps}
        self.body=self.full[self.a:self.b]
        self.fragment=self.body+'\r\n\r\n'.join(self.chunk(d) for d in self.deps)
        request={**self.request,'revision':self.sha(self.full),'full_markdown':self.full,'source_sha256':self.sha(self.full),
                 'markdown':self.fragment,'sync':self.mapping,'title':'Report'}
        status,result=self.post('/api/report-workspace',request);self.assertEqual(status,200,result)
        self.doc=result['document_id'];self.temp=self.server.project_path(self.doc)
        self.context={'document_id':self.doc,'draft_id':'b'*32,'template':'engineering','revision':self.sha(self.fragment)}
        self.edited=self.fragment.replace('Target','Edited😀').replace('Original note','Changed note')
        self.edits=[{'kind':'body','start':self.mapping['start'],'end':self.mapping['end'],'text':self.body.replace('Target','Edited😀')},
                    {**self.deps[0],'text':self.chunk(self.deps[0]).replace('Original note','Changed note')},
                    {**self.deps[1],'text':self.chunk(self.deps[1])}]
        self.req={**self.context,'markdown':self.edited,'edits':self.edits}

    @staticmethod
    def units(text):return len(text.encode('utf-16-le'))//2

    def chunk(self,part):return self.full.encode('utf-16-le')[part['start']*2:part['end']*2].decode('utf-16-le')

    def plan(self,request=None):
        status,plan=self.post('/api/report-workspace',{**(request or self.req),'action':'sync-plan'})
        self.assertEqual(status,200,plan);return plan

    def apply(self,plan,request=None):
        return self.post('/api/report-workspace',{**(request or self.req),'action':'sync-apply','plan_id':plan['plan_id'],'plan_sha256':plan['plan_sha256']})

    def test_reviewed_sync_preserves_neighbors_and_rebases_for_next_sync(self):
        plan=self.plan();self.assertTrue(plan['original_unchanged']);self.assertIn('Edited😀',plan['diff'])
        self.assertEqual((self.project/'report.md').read_bytes(),self.full.encode('utf8'))
        status,reply=self.apply(plan);self.assertEqual(status,200,reply)
        expected=self.full.replace('Target','Edited😀').replace('Original note','Changed note')
        self.assertEqual((self.project/'report.md').read_bytes(),expected.encode('utf8'))
        self.assertEqual(Path(reply['backup']).read_bytes(),self.full.encode('utf8'))
        self.assertTrue(reply['outside_ranges_unchanged'])
        mapping=reply['report_workspace']['sync'];self.assertEqual(mapping['start'],self.units(expected[:expected.index('# Report')]))
        second={**self.req,'markdown':self.edited.replace('Edited😀','Again😀'),
                'edits':[{'kind':'body','start':mapping['start'],'end':mapping['end'],'text':self.body.replace('Target','Again😀')}]}
        plan2=self.plan(second);status,reply2=self.apply(plan2,second);self.assertEqual(status,200,reply2)
        self.assertEqual((self.project/'report.md').read_bytes(),expected.replace('Edited😀','Again😀').encode('utf8'))

    def test_stale_source_and_changed_review_are_refused(self):
        plan=self.plan();external=self.full+'External change\r\n';(self.project/'report.md').write_bytes(external.encode('utf8'))
        status,reply=self.apply(plan);self.assertNotEqual(status,200,reply);self.assertIn('已变化',reply['error'])
        self.assertEqual((self.project/'report.md').read_bytes(),external.encode('utf8'))

    def test_scope_and_candidate_tampering_are_refused(self):
        wrong={**self.req,'edits':[{**self.edits[0],'start':0}]}
        status,_=self.post('/api/report-workspace',{**wrong,'action':'sync-plan'});self.assertNotEqual(status,200)
        plan=self.plan();altered={**self.req,'markdown':self.edited+'another change','edits':[{**self.edits[0],'text':'Another'}]}
        self.assertNotEqual(self.apply(plan,altered)[0],200)
        path=self.temp/'.sync-plans'/(plan['plan_id']+'.json');path.write_bytes(path.read_bytes()+b' ')
        self.assertNotEqual(self.apply(plan)[0],200)
        self.assertEqual((self.project/'report.md').read_bytes(),self.full.encode('utf8'))

    def test_new_image_asset_is_copied_without_overwriting_origin(self):
        obj={'schema':'report-figure-v1','id':'fig-added','kind':'image','src':'assets/new.png','caption':'New figure','alt':'New figure'}
        fence=chr(96)*3;added='\r\n'+fence+'report-figure\r\n'+json.dumps(obj)+'\r\n'+fence+'\r\n'
        data=png(1);(self.temp/'assets/new.png').write_bytes(data)
        request={**self.req,'markdown':self.edited+added,'edits':[{**self.edits[0],'text':self.edits[0]['text']+added},*self.edits[1:]]}
        plan=self.plan(request);self.assertEqual(self.apply(plan,request)[0],200)
        self.assertEqual((self.project/'assets/new.png').read_bytes(),data)
        self.assertTrue((self.temp/'assets/new.png').is_file())
        self.assertIn('fig-added',(self.project/'report.md').read_text('utf8'))

    def test_pending_origin_draft_refuses_without_source_writes(self):
        status,_=self.post('/api/draft',{'document_id':'legacy','draft_id':'c'*32,'template':'engineering','base_revision':self.sha(self.full),'seq':1,'markdown':self.full+'New draft'})
        self.assertEqual(status,200)
        status,reply=self.post('/api/report-workspace',{**self.req,'action':'sync-plan'});self.assertNotEqual(status,200);self.assertIn('草稿',reply['error'])
        self.assertEqual((self.project/'report.md').read_bytes(),self.full.encode('utf8'))

