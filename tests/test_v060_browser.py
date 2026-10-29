"""V060 / THEME-01..08: real service, shared palette, table names and output identity.

Manual/save/task cases are selected separately; this class checks palette and presentation.
"""
import json,os,struct,sys,tempfile,unittest,zlib
from pathlib import Path
from browser_support import ManualService
from browser_support import source,value,select

TABLE={'schema':'report-table-v1','id':'tbl-review','caption':'',
 'rows':[[{'text':'材料','rowspan':1,'colspan':1},{'text':'折射率','rowspan':1,'colspan':1}],
         [{'text':'玻璃','rowspan':1,'colspan':1},{'text':'1.5','rowspan':1,'colspan':1}],
         [{'text':'示例 B','rowspan':1,'colspan':1},{'text':'1.8','rowspan':1,'colspan':1}]]}
def table_source():
 return '# 表格稿\n\n```report-table\n'+json.dumps(TABLE,ensure_ascii=False)+'\n```\n\n见 @tbl:tbl-review。\n\n| 参数 | 数值 |\n| --- | --- |\n| A | 10 |\n'

class ThemeFeedback(ManualService):
 def export(self):return self.page.evaluate("()=>ReportStudioProgrammatic.exportHTML({sourceMode:'recompilable'})")
 def open_html(self,html,name='review.html',context=None):
  path=self.project.parent/name;path.write_bytes(html.encode('utf8'))
  page=(context or self.browser).new_page();page.goto(path.as_uri());page.wait_for_selector('[data-hrs-reader-ready="1"]');return page

 def test_09_offline_theme_switch_preserves_geometry_source_and_assets(self):
  """HTML-THEME-01: real file:// export, six palettes, one SVG/image and unchanged archive."""
  def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
  image=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',4,2,8,6,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\x20\x80\x40\xff'*4)*2))+chunk(b'IEND',b'')
  (self.project/'assets/offline-theme.png').write_bytes(image)
  text=table_source()+r'''
## 离线配色

**正文与 $x$**，说明[^theme]。

![原始图片](assets/offline-theme.png)

```mermaid
flowchart LR
 A[开始] --> B[结果]
```

$$\boldsymbol{x}=1$$

[^theme]: 配色不改变来源。
'''
  source(self.page,text)
  self.page.locator('#color-theme').select_option('celadon')
  self.page.wait_for_function("document.documentElement.dataset.colorTheme==='celadon'")
  html=self.export()
  if self.evidence:(self.evidence/'offline-theme.html').write_bytes(html.encode('utf8'))
  reader=self.open_html(html,'offline-theme.html')
  self.assertEqual(reader.locator('.hrs-reader-theme-select').count(),1)
  choices=json.loads((Path(__file__).resolve().parents[1]/'app/product_settings.json').read_text('utf8'))['color_themes']['choices']
  self.assertEqual(reader.locator('.hrs-reader-theme-select option').evaluate_all('xs=>xs.map(x=>({id:x.value,label:x.textContent}))'),[{'id':c['id'],'label':c['label']} for c in choices])
  original=reader.locator('#report-source').text_content()
  geometry=reader.locator('svg.pele').evaluate('e=>({viewBox:e.getAttribute("viewBox"),nodes:e.innerHTML})')
  saved_image=reader.locator('main img').first.get_attribute('src')
  reader.evaluate('''()=>{window.originalThemeNodes=[document.querySelector('svg.pele'),document.querySelector('main img'),document.querySelector('.markdown-math svg')]}''')
  requests=[];reader.on('request',lambda req:requests.append(req.url) if req.url.startswith(('http:','https:')) else None)
  colors=set()
  for choice in choices:
   reader.locator('.hrs-reader-theme-select').select_option(choice['id'])
   self.assertEqual(reader.locator('html').get_attribute('data-hrs-color-theme'),choice['id'])
   colors.add(reader.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--hrs-brand').trim()"))
   self.assertEqual(reader.locator('svg.pele').evaluate("e=>getComputedStyle(e).getPropertyValue('--pele-accent').trim()"),reader.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--hrs-brand').trim()"))
   self.assertEqual(reader.locator('.markdown-math svg').first.evaluate('e=>getComputedStyle(e).color'),reader.locator('.hrs-reader-main').evaluate('e=>getComputedStyle(e).color'))
   self.assertEqual(reader.locator('.hrs-reader-main').evaluate('e=>getComputedStyle(e).backgroundColor'),reader.evaluate("()=>{const e=document.createElement('i');e.style.background='var(--hrs-paper)';document.body.append(e);const c=getComputedStyle(e).backgroundColor;e.remove();return c}"))
   self.assertEqual(reader.locator('svg.pele').evaluate('e=>({viewBox:e.getAttribute("viewBox"),nodes:e.innerHTML})'),geometry)
   self.assertTrue(reader.evaluate('''()=>originalThemeNodes.every((node,i)=>node===[document.querySelector('svg.pele'),document.querySelector('main img'),document.querySelector('.markdown-math svg')][i])'''))
   self.assertEqual(reader.locator('#report-source').text_content(),original)
   self.assertEqual(reader.locator('main img').first.get_attribute('src'),saved_image)
  self.assertEqual(len(colors),6);self.assertEqual(requests,[])
  self.assertTrue(reader.evaluate("typeof pele==='undefined'&&typeof MathJax==='undefined'"))
  self.assertEqual(value(self.page),text)
  reader.reload();reader.wait_for_selector('.hrs-reader-theme-select')
  self.assertEqual(reader.locator('.hrs-reader-theme-select').input_value(),choices[-1]['id'])
  if self.evidence:reader.screenshot(path=str(self.evidence/'offline-theme-warm.png'),full_page=True)
  reader.evaluate("()=>{const key=Object.keys(localStorage).find(key=>key.startsWith('hrs-reader-theme-v1:'));localStorage.setItem(key,'unknown-palette')}")
  reader.reload();reader.wait_for_selector('.hrs-reader-theme-select')
  self.assertEqual(reader.locator('.hrs-reader-theme-select').input_value(),'celadon')
  reader.close()
  restored=self.page.evaluate('''async html=>{const doc=new DOMParser().parseFromString(html,'text/html');return ReportExportArchive.readArchive(JSON.parse(doc.querySelector('#report-source').textContent),doc)}''',html)
  self.assertEqual(restored['markdown'],text)
  self.assertEqual(restored['colorTheme'],'celadon')
  self.assertIn('offline-theme.png',restored['assets'])

 def test_10_offline_print_noscript_and_unavailable_storage(self):
  """HTML-THEME-01: default palette survives blocked storage/JS, print paper stays white."""
  source(self.page,'# 离线阅读\n\n## 正文\n\n两种模式共用正文。\n')
  self.page.locator('#color-theme').select_option('violet')
  self.page.wait_for_function("document.documentElement.dataset.colorTheme==='violet'")
  for profile in ('free','engineering'):
   self.page.locator('#render-profile').select_option(profile)
   self.page.wait_for_function('p=>document.body.dataset.renderProfile===p',arg=profile)
   html=self.page.evaluate("()=>ReportStudioProgrammatic.exportHTML({sourceMode:'reading'})")
   with self.browser.new_context() as context:
    context.add_init_script("Object.defineProperty(window,'localStorage',{get(){throw Error('storage unavailable')}})")
    reader=self.open_html(html,'reading-'+profile+'.html',context)
    self.assertEqual(reader.locator('.hrs-reader-theme-select').input_value(),'violet')
    reader.locator('.hrs-reader-theme-select').select_option('celadon')
    self.assertEqual(reader.locator('html').get_attribute('data-hrs-color-theme'),'celadon')
    reader.emulate_media(media='print')
    self.assertEqual(reader.locator('.hrs-reader-main').evaluate('e=>getComputedStyle(e).backgroundColor'),'rgb(255, 255, 255)')
    self.assertEqual(reader.locator('body').evaluate('e=>getComputedStyle(e).backgroundColor'),'rgb(255, 255, 255)')
    self.assertFalse(reader.locator('.hrs-reader-theme-select').is_visible())
   path=self.project.parent/('noscript-'+profile+'.html');path.write_text(html,encoding='utf8')
   with self.browser.new_context(java_script_enabled=False) as context:
    reader=context.new_page();reader.goto(path.as_uri())
    self.assertEqual(reader.locator('main h1').inner_text(),'离线阅读')
    self.assertEqual(reader.locator('html').get_attribute('data-hrs-color-theme'),'violet')
    self.assertEqual(reader.locator('.hrs-reader-theme-select').count(),0)
    self.assertEqual(reader.locator('#report-source').evaluate('e=>JSON.parse(e.textContent).snapshot'),{'kind':'reading-only'})

 def test_05_palette_six_colors_and_export_identity(self):
  self.assertEqual(self.page.locator('#color-theme').count(),1,'A usable palette selector is missing')
  original=value(self.page);colors={}
  for name in ('blue','celadon','violet','azure','navy','warm'):
   self.page.locator('#color-theme').select_option(name)
   self.page.wait_for_function('n=>document.documentElement.dataset.colorTheme===n',arg=name)
   colors[name]=self.page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--hrs-brand').trim()")
   self.assertTrue(colors[name]);self.assertEqual(value(self.page),original)
   self.assertEqual(self.page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--hrs-danger-soft').trim()"),'#e8bec0')
  self.assertEqual(len(set(colors.values())),6)
  html=self.export();reader=self.open_html(html)
  self.assertEqual(reader.locator('html').get_attribute('data-hrs-render-profile'),'free')
  self.assertEqual(reader.locator('html').get_attribute('data-hrs-color-theme'),'warm')
  self.assertEqual(reader.locator('.hrs-reader-brand').inner_text(),'笔记阅读')
  self.assertEqual(reader.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--hrs-brand').trim()"),colors['warm'])
  self.assertEqual(reader.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--hrs-table-radius').trim()"),'8px')
  payload=reader.locator('#report-source').evaluate('e=>JSON.parse(e.textContent)')
  self.assertEqual(payload['renderProfile'],'free');self.assertEqual(payload['colorTheme'],'warm');reader.close()
  self.page.goto(f'http://127.0.0.1:{self.server.server_port}/web/index.html?programmatic=1&theme=default')
  self.page.evaluate('()=>ReportStudioProgrammatic.ready()')
  self.assertEqual(self.page.locator('#color-theme').input_value(),'blue')

 def test_06_eight_highlights_preserve_literal_colors(self):
  colors={'yellow':'#fff1a8','orange':'#ffe0b2','red':'#ffd7d7','pink':'#fbd5e8','purple':'#e7d7fa','blue':'#d9eaff','cyan':'#c9f2f3','green':'#d8f3dc'}
  for color,hexvalue in colors.items():
   text='# 高亮\n\n选中文字\n';source(self.page,text);a=text.index('选中');select(self.page,a,a+4)
   self.page.locator('#highlight-picker > summary').click();self.page.locator('[data-highlight-color='+color+']').click()
   self.page.wait_for_function('c=>document.querySelector("#markdown").sourceEditor.value.includes(c)',arg='==选中文字==' if color=='yellow' else hexvalue)
   self.assertNotIn('var(',value(self.page));self.page.wait_for_selector('#preview-content mark[style]')
   expected=self.page.evaluate("c=>{const e=document.createElement('span');e.style.backgroundColor=c;document.body.append(e);const result=getComputedStyle(e).backgroundColor;e.remove();return result}",hexvalue)
   self.page.wait_for_function("c=>{const e=document.querySelector('#preview-content mark');return e&&getComputedStyle(e).backgroundColor===c}",arg=expected)
   self.assertEqual(self.page.locator('#preview-content mark').evaluate('e=>getComputedStyle(e).backgroundColor'),expected)
  source(self.page,'# 三色\n\n==🔴重要== ==🟢进展== ==🔵信息==\n')
  self.page.wait_for_function("document.querySelectorAll('#preview-content mark').length===3")
  computed=self.page.locator('#preview-content mark').evaluate_all('xs=>xs.map(x=>getComputedStyle(x).backgroundColor)')
  self.assertEqual(len(set(computed)),3)
  reader=self.open_html(self.export());self.assertEqual(reader.locator('main mark').evaluate_all('xs=>xs.map(x=>getComputedStyle(x).backgroundColor)'),computed);reader.close()

 def test_07_table_names_and_number_toggle_agree(self):
  source(self.page,table_source());self.page.wait_for_selector('.hrs-table-mini')
  self.page.locator('#show-object-numbers').uncheck()
  self.page.wait_for_function("document.querySelector('#preview-content a.object-xref')?.textContent==='材料 · 折射率'")
  self.assertEqual(self.page.locator('#preview-content .hrs-table-kind').all_text_contents(),['材料 · 折射率','参数 · 数值'])
  cells=self.page.locator('#preview-content .report-table-wrap .hrs-table-rendered td');self.assertGreaterEqual(cells.count(),6)
  self.assertTrue(cells.evaluate_all("xs=>xs.every(e=>getComputedStyle(e).backgroundColor==='rgb(255, 255, 255)')"))
  reader=self.open_html(self.export())
  names=reader.locator('.hrs-reader-object-order a').all_text_contents()
  self.assertTrue(any('材料 · 折射率' in n for n in names),names)
  self.assertTrue(any('参数 · 数值' in n for n in names),names)
  self.assertTrue(reader.locator('main .hrs-table-rendered td').evaluate_all("xs=>xs.length>=6&&xs.every(e=>getComputedStyle(e).backgroundColor==='rgb(255, 255, 255)')"));reader.close()
  self.page.locator('#show-object-numbers').check()
  self.page.wait_for_function("document.querySelector('#preview-content .hrs-table-kind')?.textContent.startsWith('表 1')")
  self.assertEqual(self.page.locator('#preview-content a.object-xref').inner_text(),'表 1')
  self.page.locator('#render-profile').select_option('engineering')
  self.page.wait_for_function("document.body.dataset.renderProfile==='engineering'")
  reader=self.open_html(self.export(),'engineering.html')
  self.assertEqual(reader.locator('html').get_attribute('data-hrs-render-profile'),'engineering')
  self.assertEqual(reader.locator('.hrs-reader-brand').inner_text(),'报告阅读')
  self.assertIn('表 1',reader.locator('main .hrs-table-heading-caption').first.inner_text());reader.close()

 def test_08_offline_tasks_bound_to_content_and_storage_optional(self):
  source(self.page,'# 任务稿\n\n- [ ] 原任务\n');self.page.wait_for_selector('#preview-content .hrs-task-checkbox')
  context=self.browser.new_context()
  try:
   html=self.export();reader=self.open_html(html,'same.html',context)
   box=reader.locator('main input[type=checkbox]');self.assertTrue(box.is_enabled());box.click();reader.reload();self.assertTrue(box.is_checked());reader.close()
   source(self.page,'# 新的文稿\n\n- [ ] 完全不同的任务\n');self.page.wait_for_function("document.querySelector('#preview-content li')?.textContent.includes('完全不同')")
   reader=self.open_html(self.export(),'same.html',context);self.assertFalse(reader.locator('main input[type=checkbox]').is_checked());reader.close()
   context.add_init_script("Object.defineProperty(window,'localStorage',{get(){throw Error('storage unavailable')}})")
   reader=self.open_html(html,'no-storage.html',context);reader.locator('main input[type=checkbox]').click();self.assertTrue(reader.locator('main input[type=checkbox]').is_checked());reader.close()
  finally:context.close()
  self.page.locator('#render-profile').select_option('engineering');self.page.wait_for_function("document.body.dataset.renderProfile==='engineering'")
  reader=self.open_html(self.export(),'engineering-task.html');self.assertTrue(reader.locator('main input[type=checkbox]').is_disabled());reader.close()

 def test_09_help_keeps_original_layout_and_blue(self):
  self.page.locator('#color-theme').select_option('warm');self.page.wait_for_function("document.documentElement.dataset.colorTheme==='warm'")
  help_page=self.browser.new_page();help_page.goto(f'http://127.0.0.1:{self.server.server_port}/web/help.html')
  self.assertEqual(help_page.locator('.docs-shell .docs-nav').count(),1)
  self.assertEqual(help_page.locator('.docs-paper').count(),1)
  self.assertEqual(help_page.locator('.hrs-reader-theme-select').count(),0)
  self.assertEqual(help_page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--hrs-brand').trim()"),'#344dc3')
  help_page.close()

 def test_10_new_free_default_and_existing_preference(self):
  self.page.evaluate("()=>ReportStudioProgrammatic.open('new')")
  self.page.locator('#render-profile').select_option('free')
  self.page.wait_for_function("document.body.dataset.renderProfile==='free'")
  self.assertFalse(self.page.locator('#show-object-numbers').is_checked())
  self.page.locator('#show-object-numbers').check()
  self.page.wait_for_function("document.querySelector('#preview-content').dataset.hrsShowObjectNumbers==='1'")
  for profile in ('engineering','free'):
   self.page.locator('#render-profile').select_option(profile)
   self.page.wait_for_function('p=>document.body.dataset.renderProfile===p',arg=profile)
  self.assertTrue(self.page.locator('#show-object-numbers').is_checked())

 def test_11_palette_and_profile_survive_html_import_save_and_draft(self):
  source(self.page,table_source());self.page.wait_for_selector('.hrs-table-mini')
  self.page.locator('#show-object-numbers').uncheck();self.page.locator('#color-theme').select_option('navy')
  self.page.wait_for_function("document.documentElement.dataset.colorTheme==='navy'")
  self.page.wait_for_function("document.querySelector('#preview-content').dataset.hrsShowObjectNumbers==='0'")
  html=self.export();original=value(self.page)
  self.page.locator('#file-import').set_input_files({'name':'restored.html','mimeType':'text/html','buffer':html.encode('utf8')})
  self.page.locator('#modal-extra').click()
  self.page.wait_for_function("document.querySelector('#toast').textContent.includes('已导入为未保存草稿')")
  self.assertEqual(value(self.page),original);self.assertEqual(self.page.locator('#color-theme').input_value(),'navy')
  self.assertFalse(self.page.locator('#show-object-numbers').is_checked())
  self.page.locator('#btn-save').click();self.page.wait_for_selector('#modal-body input')
  self.page.locator('#modal-body input').first.fill('主题配置保存')
  self.page.locator('#modal-ok').click();self.page.locator('.confirm-window button').filter(has_text='确认位置').click()
  self.page.wait_for_function("document.querySelector('#save-indicator').textContent.includes('已保存')")
  saved=self.destination/'主题配置保存';meta=json.loads((saved/'meta.json').read_text('utf8'))
  self.assertEqual(meta['color_theme'],'navy');self.assertEqual(meta['render_profile'],'free');self.assertFalse(meta['render_options']['show_object_numbers'])
  source(self.page,original+'\n草稿内容\n');self.page.wait_for_function("document.querySelector('#save-indicator').textContent.includes('草稿已备份')")
  self.page.reload();self.page.wait_for_selector('#modal-body .draft-picker')
  self.page.locator('#modal-ok').click()
  self.page.wait_for_function("document.querySelector('#markdown').sourceEditor.value.includes('草稿内容')")
  self.assertEqual(self.page.locator('#color-theme').input_value(),'navy');self.assertFalse(self.page.locator('#show-object-numbers').is_checked())

 def test_12_table_toolbar_column_alignment_and_retained_actions(self):
  model={**TABLE,'verticalAlign':'bottom'}
  source(self.page,'# 编辑\n\n```report-table\n'+json.dumps(model,ensure_ascii=False)+'\n```\n')
  self.page.wait_for_selector('.hrs-table-mini');self.page.locator('#preview-content .hrs-table-menu > summary').click()
  self.page.get_by_role('button',name='编辑表格',exact=True).click()
  self.page.wait_for_selector('.table-edit-grid textarea')
  self.export() # Read-only preview refresh must not invalidate the source-bound dialog.
  self.assertEqual(self.page.locator('.table-editor-tools > .table-editor-row').count(),2)
  self.page.locator('.table-edit-grid textarea[data-r="0"][data-c="1"]').click()
  self.page.locator('.table-editor-alignment select').first.select_option('center')
  self.page.get_by_role('button',name='撤销表格',exact=True).click()
  self.page.get_by_role('button',name='重做表格',exact=True).click()
  self.page.locator('.table-editor-more > summary').click()
  self.assertTrue(self.page.get_by_role('button',name='增加一行',exact=True).is_visible())
  self.assertTrue(self.page.get_by_role('button',name='合并第一行',exact=True).is_visible())
  self.page.locator('#modal-ok').click()
  self.page.wait_for_function("document.querySelector('#markdown').sourceEditor.value.includes('center')")
  import re
  actual=json.loads(re.search(r'```report-table\n([\s\S]*?)\n```',value(self.page))[1])
  self.assertEqual(actual['align'],[None,'center']);self.assertEqual(actual['verticalAlign'],'bottom');self.assertEqual(actual['rows'],model['rows'])

 def test_13_compact_menus_are_visible(self):
  self.page.set_viewport_size({'width':900,'height':850});source(self.page,table_source())
  self.page.wait_for_selector('.hrs-table-mini');self.page.locator('.hrs-table-menu > summary').first.click()
  self.assertTrue(self.page.locator('.hrs-table-menu-body').first.evaluate("e=>[...e.querySelectorAll('button')].every(b=>{const r=b.getBoundingClientRect();return document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)===b})"))
  self.page.locator('#highlight-picker > summary').click()
  self.assertTrue(self.page.locator('[data-highlight-color]').evaluate_all("xs=>xs.every(b=>{const r=b.getBoundingClientRect();return document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)?.closest('[data-highlight-color]')===b})"))
  if self.evidence:self.page.screenshot(path=str(self.evidence/'compact-menus.png'))

 def test_14_table_source_change_refuses_stale_dialog(self):
  original=table_source();source(self.page,original);self.page.wait_for_selector('.hrs-table-mini')
  self.page.locator('table').first.dblclick();self.page.wait_for_selector('.table-edit-grid textarea')
  self.page.locator('.table-caption-input').fill('不应提交的题注')
  current=original+'\n另一处源文变更\n';source(self.page,current)
  self.page.locator('#modal-ok').click()
  self.page.wait_for_function("document.querySelector('#toast').textContent.includes('表格位置已变化')")
  self.assertEqual(value(self.page),current)

 def test_15_http_reading_state_is_snapshot_bound(self):
  import functools,threading
  from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
  source(self.page,'# HTTP笔记\n\n- [ ] 第一份任务\n');self.page.wait_for_selector('#preview-content .hrs-task-checkbox')
  target=self.project.parent/'http-note.html';target.write_bytes(self.export().encode())
  class Quiet(SimpleHTTPRequestHandler):
   def log_message(self,*args):pass
   def end_headers(self):
    # Replacing the synthetic file twice in one second must not reuse a 304
    # based on HTTP-date granularity instead of loading the new fixture bytes.
    self.send_header('Cache-Control','no-store');super().end_headers()
  server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=str(target.parent)))
  thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  reader=self.browser.new_page()
  try:
   reader.goto(f'http://127.0.0.1:{server.server_port}/http-note.html')
   reader.locator('main input[type=checkbox]').click();reader.reload()
   self.assertTrue(reader.locator('main input[type=checkbox]').is_checked())
   source(self.page,'# HTTP新笔记\n\n- [ ] 另一份未完成任务\n');self.page.wait_for_function("document.querySelector('#preview-content li')?.textContent.includes('另一份')")
   target.write_bytes(self.export().encode());reader.reload()
   self.assertIn('另一份未完成任务',reader.locator('main').inner_text())
   self.assertFalse(reader.locator('main input[type=checkbox]').is_checked())
  finally:reader.close();server.shutdown();server.server_close();thread.join(timeout=3)

if __name__=='__main__':unittest.main()
