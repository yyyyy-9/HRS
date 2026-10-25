"""TOPIC-LINKS-01: real input, caption, focus numbering and path click flows."""
from pathlib import Path
from unittest.mock import patch
import json,os,unittest
from browser_support import ManualService,source,value


def figure(key):
    return '```report-figure\n'+json.dumps({'schema':'report-figure-v1','id':'fig-'+key,'caption':key,'kind':'mermaid','source':'flowchart LR\n A-->B'})+'\n```\n'


class TopicLinks(ManualService):
    def test_heading_number_stays_outside_title_editing(self):
        p=self.page;source(p,'# Report\n\n## Original **title**\n')
        p.locator('#render-profile').select_option('engineering')
        p.wait_for_function("document.querySelector('#preview-content .hrs-heading-number')?.textContent==='1 '")
        heading=p.locator('#preview-content h2');heading.dblclick(position={'x':60,'y':12})
        p.wait_for_function("document.querySelector('#preview-content [contenteditable=true]')")
        p.keyboard.press('Control+a');p.keyboard.press('Backspace')
        self.assertEqual(heading.locator('.hrs-heading-number').inner_text(),'1')
        p.keyboard.type('Renamed')
        p.locator('#preview-content h1').click()
        p.wait_for_function("document.querySelector('#preview-content h2')?.textContent==='1 Renamed'")
        self.assertEqual(value(p),'# Report\n\n## Renamed\n')
        # Removing the old title and typing its replacement are separate native
        # input operations. Follow the existing history until both are undone.
        p.evaluate("document.querySelector('#markdown').sourceEditor.focus()")
        for _ in range(2):
            if 'Original **title**' in value(p):break
            p.keyboard.press('Control+z')
        self.assertIn('Original **title**',value(p),p.locator('#preview-content').inner_text())
        p.wait_for_function("document.querySelector('#preview-content h2')?.textContent.includes('Original')")
        self.assertIn('## Original **title**',value(p))

    def test_plain_mermaid_caption_materializes_one_existing_figure(self):
        p=self.page;diagram='sequenceDiagram\r\n participant A\r\n A->>B: ping'
        original='# Diagram\r\n\r\n```mermaid\r\n'+diagram+'\r\n```\r\n';source(p,original)
        p.locator('#preview-content .mermaid-card').dblclick()
        field=p.locator('#modal-body .table-caption-input')
        self.assertEqual(field.count(),1,'Ordinary Mermaid has no caption control')
        field.fill('Exchange');p.locator('#modal-ok').click()
        p.wait_for_function("document.querySelector('#preview-content .report-figure-caption')?.textContent.includes('Exchange')")
        changed=value(p);obj=json.loads(changed.split('```report-figure\r\n')[1].split('\r\n```')[0])
        self.assertEqual(obj['source'],diagram);self.assertEqual(obj['caption'],'Exchange')
        self.assertEqual(changed.count('report-figure-v1'),1)
        p.keyboard.press('Control+z');self.assertEqual(value(p),original)
        p.keyboard.press('Control+y');self.assertEqual(value(p),changed)
        p.locator('#preview-content .report-figure-wrap').dblclick()
        p.locator('#modal-body .table-caption-input').fill('Changed caption');p.locator('#modal-ok').click()
        p.wait_for_function("document.querySelector('#preview-content figcaption')?.textContent.includes('Changed caption')")
        self.assertIn(obj['id'],value(p));self.assertEqual(value(p).count('report-figure-v1'),1)

    def test_topic_toc_and_numbers_are_local_with_global_identity(self):
        p=self.page
        part=lambda key: '# '+key+' {#sec-'+key+'}\n\n## Chapter\n\n### Detail\n\n'+figure(key)+'\n| Value |\n| --- |\n| 1 |\n: Data {#tbl-'+key+'}\n\n<!-- hrs:eq id=eq-'+key+' -->\n$$x=1$$\n\n'
        raw=part('Alpha')+part('Beta')+'See @fig:fig-Beta, @tbl:tbl-Beta, @eq:eq-Beta, @fig:fig-Alpha.\n'
        source(p,raw)
        for name in ('heading','object','equation'):p.locator('#show-'+name+'-numbers').check()
        p.wait_for_function("document.querySelectorAll('#toc a').length===6")
        p.locator('#topic-select').select_option(label='2 · Beta')
        p.wait_for_function("document.querySelectorAll('#preview-content h1').length===1")
        self.assertEqual(p.locator('#toc a').count(),3)
        self.assertEqual(p.locator('#preview-content h2').inner_text(),'1 Chapter')
        self.assertEqual(p.locator('#preview-content h3').inner_text(),'1.1 Detail')
        self.assertTrue(p.locator('#preview-content figcaption').inner_text().startswith('图 1'))
        self.assertEqual(p.locator('#preview-content .equation-number').inner_text(),'(1)')
        self.assertEqual(p.locator('#preview-content .object-xref').all_text_contents(),['图 1','表 1','式 (1)','“Alpha” · 图 1'])
        p.locator('#preview-content .object-xref').last.click()
        p.wait_for_function("document.querySelector('#preview-content h1').textContent==='Alpha'")
        self.assertEqual(p.locator('#toc a').count(),3)
        p.locator('#topic-select').select_option('')
        p.wait_for_function("document.querySelectorAll('#preview-content h1').length===2")
        self.assertTrue(p.locator('#preview-content figcaption').last.inner_text().startswith('图 2'))
        self.assertEqual(p.locator('#toc a').count(),6)
        self.assertEqual(value(p),raw)
        self.assertFalse(self.document.errors,self.document.errors)

    def test_local_files_and_folders_dispatch_without_navigating_editor(self):
        p=self.page;folder=self.project/'linked folder';folder.mkdir();file=folder/'结果.txt';file.write_text('test',encoding='utf8')
        absolute=file.as_posix() if os.name=='nt' else file.as_uri()
        raw='# Links\n\n[Folder](<./linked folder>)\n\n[File](<'+absolute+'>)\n\n[URI](<'+file.as_uri()+'>)\n\n[Web](https://example.invalid/docs)\n'
        source(p,raw);before=p.url;opened=[]
        links=p.locator('#preview-content a')
        self.assertNotEqual(links.first.get_attribute('href'),'#')
        with patch('local_links.open_target',side_effect=lambda path:opened.append(str(path))), \
             patch('studio.os.startfile',side_effect=lambda path:opened.append(str(path)),create=True), \
             patch('studio.webbrowser.open',side_effect=lambda url,**kw:(opened.append(url),True)[1]):
            for n in range(3):
                with p.expect_response(lambda r:r.url.endswith('/api/local-link/open')) as response:links.nth(n).click()
                self.assertTrue(response.value.json()['ok'],response.value.text())
            with p.expect_response(lambda r:r.url.endswith('/api/external/open')) as response:links.nth(3).click()
            self.assertTrue(response.value.json()['ok'])
        self.assertEqual([Path(x).resolve() for x in opened[:3]],[folder.resolve(),file.resolve(),file.resolve()])
        self.assertEqual(opened[3],'https://example.invalid/docs')
        self.assertEqual(p.url,before);self.assertEqual(value(p),raw)
        self.assertIn('file:///',self.document.export())


if __name__=='__main__':unittest.main(verbosity=2)
