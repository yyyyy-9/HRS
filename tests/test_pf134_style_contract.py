"""PF13.4: one UI component/token authority, semantic integrity and Agent GFM caption."""
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from report_contract import analyze
from agent_readonly import project


class PF134StyleContract(unittest.TestCase):
    def test_shared_theme_styles_are_single_source(self):
        web=ROOT/'app/web'
        # V060 splits palette values from structural dimensions; consumers still
        # share one definition of each selected palette/property.
        dimensions=(web/'design_tokens.css').read_text('utf8')
        palette=(web/'theme.css').read_text('utf8')
        help_theme=(ROOT/'app/tools/readable_docs_theme.css').read_text('utf8')
        theme=dimensions+palette+help_theme
        surfaces=(web/'surface_components.css').read_text('utf8')
        selectors=(web/'style.css').read_text('utf8')+(web/'print.css').read_text('utf8')+(web/'report_reader.css').read_text('utf8')
        for var in ('table-toolbar','table-heading','table-row-alt','table-grid',
                    'table-outline','table-radius','table-cell-padx','code-ink',
                    'code-head','code-padding-x','doc-muted'):
            self.assertIn('--hrs-'+var+':',theme)
        for prop in ('table-toolbar','table-heading','table-row-alt','table-grid',
                     'table-radius','code-ink','code-padding-x'):
            self.assertIn('var(--hrs-'+prop+')',surfaces)
        # No obsolete hardcoded partial toolbar/caption overrides may reappear.
        for old in (r'\.hrs-table-tools\s*\{',
                    r'\.report-table-wrap\s+\.hrs-table-rendered\s+caption\s*\{',
                    r'\.report-table-wrap\s+\.hrs-table-rendered\s+th\s*,\s*\s*\.report-table-wrap\s+\.hrs-table-rendered\s+td\s*\{'):
            self.assertIsNone(re.search(old,selectors),f'duplicate component CSS: {old}')
        # The selected palette must not drift across CSS files.
        for filename in ('theme.css','theme-celadon.css','theme-violet.css','theme-azure.css','theme-navy.css','theme-warm.css'):
            values=(web/filename).read_text('utf8')
            for key in ('brand','table-heading','table-grid','danger-soft'):
                self.assertEqual(len(re.findall(r'--hrs-'+key+r'\s*:',values)),1,(filename,key))
            self.assertEqual(values.count('{'),values.count('}'))
        help_theme=(ROOT/'app/tools/readable_docs_theme.css').read_text('utf8')
        self.assertNotIn('Embedded into every exported report',help_theme)
        self.assertNotIn('same numbering semantics as the editable preview',help_theme)
        self.assertIn('--hrs-doc-ink',help_theme)
        self.assertIn('.docs-paper .hrs-code-panel pre',surfaces)

    def test_all_three_delivery_paths_use_one_theme(self):
        web=ROOT/'app/web'
        index=(web/'index.html').read_text('utf8')
        app=(web/'app.js').read_text('utf8')
        docs=(ROOT/'app/tools/build_readable_docs.js').read_text('utf8')
        for p in ('design_tokens.css','surface_components.css'):
            self.assertIn('/web/'+p,index)
            self.assertIn(p,app)
            self.assertIn(p,docs)
        self.assertIn('designTokens',docs)
        self.assertIn('surfaces',docs)
        self.assertIn('table-grid', (web/'design_tokens.css').read_text('utf8'))
        # All 9 generated docs must carry same token CSS byte string.
        tokens=(web/'design_tokens.css').read_text('utf8')
        for doc in ('web/help.html','web/CHANGELOG_READABLE.html','web/WORD_COMPILER_HANDOFF.html',
                    'docs/USER_GUIDE.html','docs/CHANGELOG_READABLE.html','docs/WORD_COMPILER_HANDOFF.html',
                    'docs/CURRENT_STATUS.html','docs/SHORT_TERM_PLAN.html','docs/LONG_TERM_ROADMAP.html'):
            body=(ROOT/'app'/doc).read_text('utf8')
            self.assertIn(tokens,body,doc)
            self.assertEqual(body.count('/* PF13.4 · canonical table & source-card components.'),1,doc)

    def test_gfm_caption_stays_one_object_without_becoming_numbered(self):
        caption=': h {#tbl-1b3d909e5406}'
        table='| FSR | 相邻峰位置处的输入相对谱密度 |\r\n| ---: | ---: |\r\n| 250 pm | 0.5 |\r\n| 500 pm | 0.0625 |\r\n\r\n'+caption+'\r\n'
        src=table+'\r\n继续正文\r\n'
        ir=analyze(src)
        self.assertTrue(ir['ok'],ir['diagnostics'])
        tables=[b for b in ir['blocks'] if b['type']=='table']
        self.assertEqual(len(tables),1)
        b=tables[0]
        self.assertEqual(b['source'],table)
        self.assertEqual(b['data']['caption'],'h')
        self.assertEqual(b['data']['id'],'tbl-1b3d909e5406')
        self.assertEqual(b['sourceKind'],'gfm-pipe')
        self.assertFalse(b['numbered'])
        self.assertEqual(b['end'],len(table.encode('utf-16-le'))//2)
        obj=project(ir,'get','tbl-1b3d909e5406')
        self.assertTrue(obj['found'])
        self.assertEqual(obj['block']['source'],table)
        self.assertEqual(obj['object']['sourceKind'],'gfm-pipe')
        self.assertFalse(obj['object']['numbered'])
        self.assertEqual(len(project(ir,'objects')['objects']),1)
        self.assertEqual(obj['snapshot']['text_utf8_sha256'],__import__('hashlib').sha256(src.encode()).hexdigest())
        self.assertEqual(src,table+'\r\n继续正文\r\n')

if __name__=='__main__':
    unittest.main(verbosity=2)
