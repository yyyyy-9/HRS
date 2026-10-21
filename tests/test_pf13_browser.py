"""TEST-SYSTEM-01: source cards and transactional alignment on the real page.

No app.js source slices, fake cryptography or mock document endpoints.
"""
from pathlib import Path
import json,os,tempfile,unittest
from browser_support import LiveDocument,browser_session

example='| 任务规模 | 计算类型 | Torch CPU (16 线程) | GPU (RTX 5080) | 加速倍数 |\n| :--- | :--- | ---: | ---: | ---: |\n| 128×128 | 前向 E² | 102.105 ms | 8.705 ms | 11.73× |\n| a\\|b | `<img onerror=alert(1)>` | &value | 12.0 | 2.4× |'
enhanced={'schema':'report-table-v1','id':'tbl-enhanced-test','caption':'增强表','align':['center','center'],'verticalAlign':'middle','rows':[[{'text':'表头','rowspan':1,'colspan':2},None],[{'text':'甲','rowspan':1,'colspan':1},{'text':'乙','rowspan':1,'colspan':1}]]}
enhanced_source='```report-table\n'+json.dumps(enhanced,ensure_ascii=False,indent=2)+'\n```'


class TableCards(unittest.TestCase):
    def test_source_card_clipboard_print_and_transactional_alignment(self):
      markdown='# 表格测试\n\n'+example+'\n\n'+enhanced_source+'\n'
      with browser_session() as browser,tempfile.TemporaryDirectory(prefix='hrs-table-cards-') as directory:
       with LiveDocument(browser,Path(directory),markdown,profile='engineering') as document:
        page=document.page;errors=document.errors
        document.context.grant_permissions(['clipboard-read','clipboard-write'])
        wrap=page.locator('.report-table-wrap').first
        assert wrap.locator('table').is_visible()
        assert wrap.locator('.hrs-table-source').is_hidden()
        assert wrap.locator('.hrs-table-source-code').text_content().strip('\n')==example
        assert wrap.locator('.hrs-table-syntax-pipe').count()>12
        assert wrap.locator('.hrs-table-syntax-delimiter').count()>=1
        assert wrap.locator('.hrs-table-syntax-inline').count()>=1
        assert not page.locator('img[onerror]').count()
        wrap.locator('[data-table-toggle]').click()
        assert wrap.locator('.hrs-table-source').is_visible()
        assert wrap.locator('table').is_hidden()
        wrap.locator('[data-table-fold]').click()
        assert wrap.locator('pre.hrs-table-source-pre').is_hidden()
        assert wrap.locator('[data-table-fold]').inner_text()=='展开源码'
        wrap.locator('[data-table-fold]').click()
        assert wrap.locator('pre.hrs-table-source-pre').is_visible()
        assert wrap.locator('.hrs-table-source-code').text_content().strip('\n')==example
        page.evaluate("()=>navigator.clipboard.writeText('sentinel-copy-not-complete')")
        wrap.locator('[data-table-copy]').click()
        page.wait_for_function("async()=>(await navigator.clipboard.readText())!=='sentinel-copy-not-complete'")
        copied=page.evaluate('()=>navigator.clipboard.readText()')
        assert copied.startswith('任务规模\t计算类型\tTorch CPU (16 线程)'),copied
        assert 'a|b' in copied and '102.105 ms' in copied,copied
        wrap.locator('[data-table-toggle]').click()
        assert wrap.locator('table').is_visible()
        assert wrap.locator('.hrs-table-source').is_hidden()
        second=page.locator('.report-table-wrap').nth(1)
        second.locator('[data-table-toggle]').click()
        assert second.locator('.hrs-table-source-code').text_content().strip('\n')==enhanced_source
        assert second.locator('.hrs-syntax-string').count()>0
        # The printed document always contains rendered HTML tables, even when the MD card is selected.
        page.emulate_media(media='print')
        assert second.locator('table').evaluate('(el) => getComputedStyle(el).display')=='table'
        assert second.locator('.hrs-table-source').evaluate('(el) => getComputedStyle(el).display')=='none'
        page.emulate_media(media='screen')
        # inspect real visual result screenshot
        if os.environ.get('TEST_ARTIFACT_DIR'):
         artifact=Path(os.environ['TEST_ARTIFACT_DIR']);artifact.mkdir(parents=True,exist_ok=True)
         page.screenshot(path=str(artifact/'table_source_card.png'),full_page=True)
        print('BROWSER source: view, fold/unfold, highlight, escaping, TSV, print OK')
        page.evaluate('''model => {
         const modal=({body,onOk})=>{
          const node=document.createElement('div');node.id='synthetic-modal';document.body.append(node);body(node);
          window.__applyModal=onOk;return new Promise(resolve=>{window.__resolveModal=resolve;});
         };
         window.__modalPromise=window.ReportTableEditor.open(model,{modal,toast:msg=>{window.__toast=msg;}});
         window.__complete=()=>{window.__resolveModal(window.__applyModal());return window.__modalPromise;};
        }''',enhanced)
        page.locator('#synthetic-modal textarea[data-r]').first.click()
        horizontal=page.locator('#synthetic-modal .table-editor-alignment select').nth(0)
        vertical=page.locator('#synthetic-modal .table-editor-alignment select').nth(1)
        assert horizontal.input_value()=='center',horizontal.input_value()
        assert vertical.input_value()=='middle',vertical.input_value()
        horizontal.select_option('right')
        vertical.select_option('bottom')
        # Undo and redo both alignment settings within the transactional modal.
        page.locator('#synthetic-modal .table-editor-tools button').nth(0).click()
        assert vertical.input_value()=='middle'
        page.locator('#synthetic-modal .table-editor-tools button').nth(0).click()
        assert horizontal.input_value()=='center'
        page.locator('#synthetic-modal .table-editor-tools button').nth(1).click()
        page.locator('#synthetic-modal .table-editor-tools button').nth(1).click()
        assert horizontal.input_value()=='right'
        assert vertical.input_value()=='bottom'
        result=page.evaluate('window.__complete()')
        assert result['align']==['right','center'],result
        assert result['verticalAlign']=='bottom',result
        assert not errors,errors
        assert (document.project/'report.md').read_text('utf8')==markdown

if __name__=='__main__': unittest.main(verbosity=2)
