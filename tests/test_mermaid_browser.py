"""MERMAID-01 / PELE-01: offline Mermaid syntax, preserved editing and export.

Real local service and Chromium; only the inherited test-owned save chooser
is replaced. Requests are observed, never mocked. User source stays unchanged.
"""
from pathlib import Path
import io,json,os,re,unittest,zipfile
from collections import Counter
from browser_support import ManualService
from browser_support import source,value

ROOT=Path(__file__).resolve().parents[1]
CASES=json.loads((ROOT/'tests/fixtures/mermaid_full.json').read_text('utf8'))

def manuscript(cases=CASES):
    return '# Mermaid 验证\n\n'+''.join('## '+c['name']+'\n\n```mermaid\n'+c['source']+'\n```\n\n' for c in cases)

def geometry(page,selector):
    """Observe actual SVG shape/arrow positions in its viewBox coordinates."""
    return page.locator(selector).evaluate('''svg=>{
      const nodes={};for(const node of svg.querySelectorAll('.pele-node[data-id]')){
        const shape=[...node.children].find(e=>['rect','polygon','ellipse','circle','path'].includes(e.localName));
        const b=shape.getBBox(),p=svg.createSVGPoint();p.x=b.x;p.y=b.y;
        const point=p.matrixTransform(shape.getCTM()).matrixTransform(svg.getCTM().inverse());
        nodes[node.dataset.id]={x:point.x,y:point.y,width:b.width,height:b.height};
      }
      return {nodes,view:svg.getAttribute('viewBox').split(/[ ,]+/).map(Number),edges:[...svg.querySelectorAll('.pele-edge[data-hrs-to]')].map(e=>({from:e.dataset.hrsFrom,to:e.dataset.hrsTo,path:e.querySelector('path:not(.pele-marker)').getAttribute('d'),tip:e.querySelector('.pele-marker').getAttribute('d').match(/-?\\d*\\.?\\d+/g).slice(0,2).map(Number)}))};
    }''')

class MermaidFull(ManualService):
    def setUp(self):
        super().setUp()
        self.external=[]
        self.page.on('request',lambda r:self.external.append(r.url) if re.match(r'https?://',r.url) and not r.url.startswith(f'http://127.0.0.1:{self.server.server_port}/') else None)

    def load_diagrams(self,cases=CASES):
        text=manuscript(cases);source(self.page,text)
        self.page.wait_for_function('({n,text})=>document.querySelectorAll("#preview-content .hrs-mermaid-render > svg").length===n&&[...document.querySelectorAll("#preview-content .doc-block")].every(b=>b._sourceDocument===text)',arg={'n':len(cases),'text':text})
        self.assertEqual(self.page.locator('#preview-content .diagram-error').count(),0)
        return text

    def test_01_supplied_three_and_full_engine_diagram_types(self):
        text=self.load_diagrams()
        for i,case in enumerate(CASES[:4]):
            self.assertEqual(self.page.locator('#preview-content .mermaid-card').nth(i).locator('.pele-node').count(),case['nodes'])
        first=self.page.locator('#preview-content .mermaid-card').first
        self.assertIn('0.5 nm',first.inner_text());self.assertNotIn('<br',first.inner_text())
        boxes=first.locator('.pele-node').evaluate_all('ns=>ns.map(n=>n.getBoundingClientRect().toJSON())')
        for i,a in enumerate(boxes):
            for b in boxes[i+1:]:
                self.assertFalse(a['left']<b['right']-1 and b['left']<a['right']-1 and a['top']<b['bottom']-1 and b['top']<a['bottom']-1,'Nodes overlap')
        self.assertEqual(value(self.page),text);self.assertEqual(self.external,[])
        ids=self.page.locator('#preview-content svg [id],#preview-content svg[id]').evaluate_all('xs=>xs.map(e=>e.id)')
        self.assertEqual(len(ids),len(set(ids)),str({k:v for k,v in Counter(ids).items() if v>1}))
        if self.evidence:
            self.page.locator('[data-view=reading]').click()
            self.page.wait_for_function('document.querySelectorAll("#preview-content .mermaid-card svg").length===9')
            for i in range(3):self.page.locator('#preview-content .mermaid-card').nth(i).screenshot(path=str(self.evidence/f'user-{i+1}.png'))

    def test_02_edit_multiline_label_and_complex_source_without_loss(self):
        text=self.load_diagrams(CASES[:1]);self.page.locator('#preview-content .mermaid-card').dblclick()
        self.page.wait_for_selector('#modal-layer:not([hidden])')
        self.page.wait_for_selector('#modal-body .modal-diagram-svg svg')
        name=self.page.locator('#modal-body [aria-label="节点文字"]')
        self.assertEqual(name.input_value(),'PLD100L\n0.5 nm')
        name.fill('PLD100L\n0.6 nm')
        self.page.locator('#modal-body .modal-diagram-svg [data-node="B"]').click()
        self.assertIn('单程 Littrow',name.input_value(),'Rendered node did not map back to its source ID')
        self.page.locator('#modal-ok').click()
        self.page.wait_for_function('document.querySelector("#preview-content .mermaid-card")?.textContent.includes("0.6 nm")')
        self.assertIn('<br/>0.6 nm',value(self.page))
        complex_text=self.load_diagrams(CASES[3:4]);self.page.locator('#preview-content .mermaid-card').dblclick()
        self.page.wait_for_selector('#modal-body .modal-diagram-svg svg')
        field=self.page.locator('.diagram-source-input');self.assertEqual(field.input_value(),CASES[3]['source'])
        field.fill(CASES[3]['source'].replace('输入','输入源'))
        self.page.wait_for_function('document.querySelector(".modal-diagram-svg")?.textContent.includes("输入源")')
        self.page.locator('#modal-ok').click()
        self.page.wait_for_function('document.querySelector("#preview-content .mermaid-card")?.textContent.includes("输入源")')
        self.assertEqual(value(self.page),complex_text.replace('输入','输入源'))

    def test_03_recompilable_offline_html_and_native_reading_pack(self):
        text=self.load_diagrams()
        html=self.page.evaluate('()=>ReportStudioProgrammatic.exportHTML({sourceMode:"recompilable"})')
        self.assertNotIn('mermaid.min.js',html,'Static export must not need the rendering library')
        self.assertNotIn('pele.global.js',html,'Static export must not need the rendering library')
        dest=self.folder/'mermaid.html';dest.write_text(html,encoding='utf8')
        reader=self.browser.new_page();external=[]
        reader.on('request',lambda r:external.append(r.url) if r.url.startswith(('http:','https:')) else None)
        reader.goto(dest.as_uri());self.assertEqual(reader.locator('main .mermaid-card svg').count(),len(CASES))
        self.assertEqual(external,[]);reader.close()
        restored=self.page.evaluate('async html=>{const doc=new DOMParser().parseFromString(html,"text/html");return (await ReportExportArchive.readArchive(JSON.parse(doc.querySelector("#report-source").textContent),doc)).markdown;}',html)
        self.assertEqual(restored,text)
        memory=io.BytesIO()
        with zipfile.ZipFile(memory,'w') as archive:archive.writestr('REPORT.md',text.encode('utf8'))
        self.page.locator('#file-reader-zip').set_input_files({'name':'mermaid.zip','mimeType':'application/zip','buffer':memory.getvalue()})
        self.page.wait_for_function('n=>document.querySelectorAll("#reader-article .hrs-mermaid-render svg").length===n',arg=len(CASES))
        self.assertEqual(value(self.page),text);self.assertEqual(self.external,[])

    def test_04_formal_figure_and_error_recovery(self):
        figure={'schema':'report-figure-v1','id':'fig-optics','kind':'mermaid','caption':'测试光路','source':CASES[0]['source']}
        text='# 工程报告\n\n## 光路\n\n```report-figure\n'+json.dumps(figure,ensure_ascii=False)+'\n```\n\n参见 @fig:fig-optics。\n'
        source(self.page,text)
        self.page.wait_for_selector('#preview-content figure[data-figure-id="fig-optics"] svg')
        self.page.locator('#render-profile').select_option('engineering')
        self.page.wait_for_function('document.body.dataset.renderProfile==="engineering"')
        html=self.page.evaluate('()=>ReportStudioProgrammatic.exportHTML({sourceMode:"recompilable"})')
        self.assertIn('测试光路',html);self.assertEqual(value(self.page),text)
        source(self.page,'# 错误\n\n```mermaid\nflowchart TB\n A[broken\n```\n')
        self.page.wait_for_selector('#preview-content .diagram-error')
        self.assertNotIn('存在渲染失败',self.page.locator('#preview-content').inner_text())
        self.page.evaluate('()=>window._mermaidProbe=0')
        safe='flowchart LR\n A["<script>window._mermaidProbe=1</script>安全"] --> B[结束]\n click B "javascript:window._mermaidProbe=2"'
        source(self.page,manuscript([{'name':'安全标签','source':safe}]))
        self.page.wait_for_selector('#preview-content .mermaid-card svg')
        self.assertEqual(self.page.evaluate('window._mermaidProbe'),0)
        self.assertEqual(self.page.locator('#preview-content svg script,#preview-content svg [onclick],#preview-content svg a[href^="javascript:"]').count(),0)
        self.assertEqual(self.external,[])

    def test_05_unmanaged_resources_are_rejected_before_network(self):
        code='flowchart LR\n A@{ img: "https://example.invalid/a.png", label: "外部图片" }'
        result=self.page.evaluate('async code=>{try{await ReportMermaid.render(code);return "unexpected success";}catch(e){return e.message;}}',code)
        self.assertIn('外部',result)
        override='%%{init: {"themeCSS":"@import url(https://example.invalid/style.css);","securityLevel":"loose"}}%%\nflowchart LR\n A[安全]-->B[文本]'
        svg=self.page.evaluate('code=>ReportMermaid.render(code)',override)
        self.assertNotIn('example.invalid',svg)
        self.assertEqual(self.external,[])

    def test_06_palette_reuses_layout_and_standalone_svg_keeps_colors(self):
        # PELE-01: a color-only change must reuse geometry; exported SVG must
        # also carry its colors when the surrounding HRS stylesheet is absent.
        self.assertTrue(self.page.evaluate('!!window.pele?.render'),'Pele is not the active offline renderer')
        result=self.page.evaluate('''async source=>{
          const runtime=window.pele;let calls=0;
          window.pele={...runtime,render:(...args)=>{calls++;return runtime.render(...args);}};
          const host=document.createElement('div');document.body.append(host);
          const style=document.documentElement.style,old=style.getPropertyValue('--hrs-diagram-bg');
          try{
            ReportMermaid.clearCache();await ReportMermaid.into(host,source);
            const before=host.querySelector('svg').getAttribute('viewBox'),layoutCalls=calls;
            style.setProperty('--hrs-diagram-bg','#e1f0ff');
            const liveFill=getComputedStyle(host.querySelector('.pele-node rect')).fill;
            const frozen=await ReportMermaid.render(source);
            const doc=new DOMParser().parseFromString(frozen,'image/svg+xml');
            const colors=doc.documentElement.style.getPropertyValue('--pele-surface');
            const after=doc.documentElement.getAttribute('viewBox');
            host.innerHTML=frozen;
            const svg=host.querySelector('svg'),rect=svg.querySelector('.pele-node rect'),box=rect.getBBox(),view=svg.viewBox.baseVal;
            const pt=svg.createSVGPoint();pt.x=box.x+8;pt.y=box.y+8;
            const sample=pt.matrixTransform(rect.getCTM()).matrixTransform(svg.getCTM().inverse());
            const model=await ReportBridgeModel.render({markdown:'# Figure',sections:[],sectionStarts:[],inline:[],diagram_sources:{probe:source}});
            const img=new Image();img.src='data:image/png;base64,'+model.diagrams.probe;await img.decode();
            const canvas=document.createElement('canvas');canvas.width=img.naturalWidth;canvas.height=img.naturalHeight;
            const ctx=canvas.getContext('2d');ctx.drawImage(img,0,0);
            const pixel=[...ctx.getImageData(Math.floor((sample.x-view.x)*canvas.width/view.width),Math.floor((sample.y-view.y)*canvas.height/view.height),1,1).data];
            return {calls,layoutCalls,liveFill,colors,before,after,pixel};
          }finally{window.pele=runtime;host.remove();if(old)style.setProperty('--hrs-diagram-bg',old);else style.removeProperty('--hrs-diagram-bg');}
        }''',CASES[0]['source'])
        self.assertEqual(result['layoutCalls'],1,'The engine counter did not observe the initial render')
        self.assertEqual(result['calls'],result['layoutCalls'],'Theme color change regenerated diagram geometry')
        self.assertEqual(result['liveFill'],'rgb(225, 240, 255)')
        self.assertEqual(result['colors'],'#e1f0ff');self.assertEqual(result['before'],result['after'])
        self.assertEqual(result['pixel'],[225,240,255,255],'Word PNG lost the selected diagram color')
        self.assertEqual(self.external,[])

    def test_07_math_labels_are_typeset_and_portable_without_changing_source(self):
        # PELE-01: without the MathJax resolver Pele falls back to raw TeX.
        case={'name':'图内公式','source':r'flowchart LR'+'\n'+r' A["$$\boldsymbol{\alpha}+\beta$$"] --> B["$$\frac{1}{2}$$"]'}
        text=self.load_diagrams([case,case])
        svgs=self.page.locator('#preview-content .mermaid-card svg.pele')
        self.assertEqual(svgs.count(),2)
        self.assertGreater(svgs.first.locator('[data-mml-node]').count(),0)
        self.assertNotIn(r'\alpha',svgs.first.text_content())
        sizes=svgs.first.locator('.pele-math svg').evaluate_all('xs=>xs.map(svg=>({width:Number(svg.getAttribute("width")),actual:parseFloat(getComputedStyle(svg).width)}))')
        self.assertTrue(sizes)
        if self.evidence:self.page.locator('#preview-content').screenshot(path=str(self.evidence/'math-labels.png'))
        for size in sizes:self.assertAlmostEqual(size['actual'],size['width'],delta=0.5,msg='Report SVG stylesheet stretched the inner math label')
        self.assertEqual(self.page.locator('#preview-content [data-mjx-error],#preview-content [data-mml-node="merror"]').count(),0)
        html=self.page.evaluate('()=>ReportStudioProgrammatic.exportHTML({sourceMode:"recompilable"})')
        self.assertNotIn('pele.global.js',html)
        self.assertEqual(value(self.page),text)
        restored=self.page.evaluate('async html=>{const doc=new DOMParser().parseFromString(html,"text/html");return (await ReportExportArchive.readArchive(JSON.parse(doc.querySelector("#report-source").textContent),doc)).markdown;}',html)
        self.assertEqual(restored,text)
        ids=svgs.locator('[id]').evaluate_all('xs=>xs.map(e=>e.id)')
        self.assertEqual(len(ids),len(set(ids)))
        dest=self.folder/'math-labels.html';dest.write_text(html,encoding='utf8')
        reader=self.browser.new_page()
        try:
            reader.goto(dest.as_uri())
            self.assertEqual(reader.locator('main svg.pele').count(),2)
            self.assertGreater(reader.locator('main .pele-math [data-mml-node]').count(),0)
            self.assertTrue(reader.pdf(print_background=True).startswith(b'%PDF-'),'Static math diagram PDF did not render')
        finally:reader.close()
        self.assertEqual(self.external,[])

    def test_08_limits_fixed_direction_and_failed_source_do_not_show_stale_svg(self):
        # PELE-01: defaults must not silently rotate engineering diagrams or
        # keep a previous successful drawing after a rejected source update.
        result=self.page.evaluate('''async source=>{
          const host=document.createElement('div');host.style.width='300px';document.body.append(host);
          try{
            await ReportMermaid.into(host,source);
            const a=host.querySelector('[data-id="A"]').getBoundingClientRect(),b=host.querySelector('[data-id="B"]').getBoundingClientRect();
            let error='';try{await ReportMermaid.into(host,'flowchart LR\\n A[broken');}catch(e){error=e.message;}
            const oversized='flowchart TB\\n'+Array.from({length:501},(_,i)=>'N'+i+'-->N'+(i+1)).join('\\n');
            const limit=[];for(const prefix of ['', '%%{init: {"maxEdges":5000}}%%\\n']){
              try{await ReportMermaid.render(prefix+oversized);limit.push('');}catch(e){limit.push(e.message);}
            }
            return {horizontal:b.x>a.right,svgCount:host.querySelectorAll('svg').length,state:host.dataset.mermaidState,error,limit};
          }finally{host.remove();}
        }''','flowchart LR\n A[开始] --> B[结束]')
        self.assertTrue(result['horizontal']);self.assertEqual(result['svgCount'],0)
        self.assertEqual(result['state'],'error');self.assertTrue(result['error']);self.assertTrue(all(result['limit']))
        self.assertEqual(self.external,[])

    def test_09_series_colors_do_not_use_pale_node_backgrounds(self):
        # PELE-01: pie percentages are white; mapping category series to HRS's
        # pale node surfaces makes the third slice's label nearly invisible.
        self.load_diagrams([{'name':'分类比例','source':'pie\n "A":30\n "B":25\n "C":45'}])
        colors=self.page.locator('#preview-content .pele-slice').evaluate_all('xs=>xs.map(x=>getComputedStyle(x).fill)')
        ink=self.page.locator('#preview-content .pele-slice-labels').evaluate('x=>getComputedStyle(x).fill')
        def luminance(color):
            values=[float(v)/255 for v in re.findall(r'[\d.]+',color)[:3]]
            linear=[v/12.92 if v<=0.04045 else ((v+0.055)/1.055)**2.4 for v in values]
            return sum(v*w for v,w in zip(linear,[0.2126,0.7152,0.0722]))
        a,b=sorted([luminance(colors[2]),luminance(ink)])
        self.assertEqual(len(set(colors)),3)
        self.assertGreaterEqual((b+0.05)/(a+0.05),3,'Categorical color was replaced by a low-contrast node surface')
        self.assertEqual(self.external,[])

    def test_10_real_drag_updates_source_and_cancel_keeps_original(self):
        # MERMAID-DRAG-01: real pointer input must persist the old position
        # annotations, rather than moving a disposable modal-only SVG.
        text=self.load_diagrams(CASES[:1]);p=self.page
        p.locator('#preview-content .mermaid-card').dblclick()
        node=p.locator('#modal-body .modal-diagram-svg .pele-node[data-id="B"]')
        node.wait_for();box=node.bounding_box()
        p.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2)
        p.mouse.down();p.mouse.move(box['x']+box['width']/2+65,box['y']+box['height']/2+35,steps=8);p.mouse.up()
        self.assertIn('%% pos B ',p.locator('.diagram-source-input').input_value(),'Dragging did not preserve a node position')
        placed=p.locator('.diagram-source-input').input_value()
        node=p.locator('#modal-body .modal-diagram-svg .pele-node[data-id="B"]');box=node.bounding_box()
        p.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2);p.mouse.down()
        p.mouse.move(box['x']+box['width']/2+25,box['y']+box['height']/2+10,steps=3)
        node.dispatch_event('pointercancel',{'pointerId':1});p.mouse.up()
        self.assertEqual(p.locator('.diagram-source-input').input_value(),placed,'Cancelled pointer movement wrote positions')
        p.locator('#modal-cancel').click();self.assertEqual(value(p),text)

    def test_11_legacy_positions_arrows_math_html_pdf_and_word_png_agree(self):
        cases=[{'name':direction,'source':'flowchart '+direction+'\n    %% pos A 40 200\n    %% pos B 420 40\n    A["输入<br/>$$\\boldsymbol{k}$$"] -->|是| B{判断}\n    B -.-> A\n    B --> B'} for direction in ['LR','TB','RL','BT']]
        text=self.load_diagrams(cases);p=self.page
        for i,case in enumerate(cases):
            selector=f'#preview-content .hrs-mermaid-render >> nth={i} >> svg.pele'
            layout=geometry(p,selector)
            for key,wanted in {'A':(40,200),'B':(420,40)}.items():
                self.assertAlmostEqual(layout['nodes'][key]['x'],wanted[0],delta=.01)
                self.assertAlmostEqual(layout['nodes'][key]['y'],wanted[1],delta=.01)
            self.assertEqual(len(layout['edges']),3)
            for edge in layout['edges']:
                b=layout['nodes'][edge['to']];x,y=edge['tip']
                self.assertGreaterEqual(x,b['x']-.1);self.assertLessEqual(x,b['x']+b['width']+.1)
                self.assertGreaterEqual(y,b['y']-.1);self.assertLessEqual(y,b['y']+b['height']+.1)
                if edge['to']=='B':
                    self.assertAlmostEqual(abs((x-b['x']-b['width']/2)/(b['width']/2))+abs((y-b['y']-b['height']/2)/(b['height']/2)),1,delta=.001,msg='Arrow detached from diamond')
                else:
                    self.assertLess(min(abs(x-b['x']),abs(x-b['x']-b['width']),abs(y-b['y']),abs(y-b['y']-b['height'])),.1,'Arrow detached from its node')
            png=p.evaluate('''async ({source,layout})=>{
              const m=await ReportBridgeModel.render({markdown:'# Diagram',sections:[],sectionStarts:[],inline:[],diagram_sources:{test:source}});
              const image=new Image();image.src='data:image/png;base64,'+m.diagrams.test;await image.decode();
              const canvas=document.createElement('canvas');canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;const c=canvas.getContext('2d');c.drawImage(image,0,0);
              const a=layout.nodes.A,v=layout.view,x=(a.x+5-v[0])*canvas.width/v[2],y=(a.y+a.height/2-v[1])*canvas.height/v[3];
              return {pixel:[...c.getImageData(Math.floor(x),Math.floor(y),1,1).data],width:canvas.width,height:canvas.height};
            }''',{'source':case['source'],'layout':layout})
            self.assertEqual(png['pixel'],[238,243,255,255],'Word image did not preserve the manually placed node')
        html=p.evaluate('()=>ReportStudioProgrammatic.exportHTML({sourceMode:"recompilable"})')
        dest=self.folder/'placed.html';dest.write_text(html,encoding='utf8')
        reader=self.browser.new_page()
        try:
            reader.goto(dest.as_uri())
            static=geometry(reader,'main .hrs-mermaid-render >> nth=0 >> svg.pele')
            self.assertAlmostEqual(static['nodes']['B']['x'],420,delta=.01)
            self.assertTrue(reader.pdf(print_background=True).startswith(b'%PDF-'))
        finally:reader.close()
        restored=p.evaluate('async html=>{const d=new DOMParser().parseFromString(html,"text/html");return (await ReportExportArchive.readArchive(JSON.parse(d.querySelector("#report-source").textContent),d)).markdown}',html)
        self.assertEqual(restored,text);self.assertEqual(value(p),text);self.assertEqual(self.external,[])

    def test_12_drag_apply_undo_save_reopen_rename_and_auto_layout(self):
        p=self.page;did='d'*32;self.server.registry.register(did,self.project)
        p.evaluate('id=>ReportStudioProgrammatic.open(id)',did)
        text=manuscript(CASES[:1]).replace('\n','\r\n');source(p,text)
        p.wait_for_selector('#preview-content .mermaid-card svg')
        p.locator('#preview-content .mermaid-card').dblclick()
        node=p.locator('#modal-body .modal-diagram-svg [data-node="B"]');node.wait_for();box=node.bounding_box()
        p.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2);p.mouse.down();p.mouse.move(box['x']+box['width']/2+75,box['y']+box['height']/2+45,steps=10);p.mouse.up()
        p.locator('#modal-ok').click();p.wait_for_function('document.querySelector("#markdown").sourceEditor.value.includes("%% pos B ")')
        placed=value(p);self.assertEqual(re.sub(r'^[ \t]*%% pos[^\r\n]*(?:\r\n|\n|\r)','',placed,flags=re.M),text)
        found=re.search(r'%% pos B (\d+) (\d+)',placed);wanted=(int(found[1]),int(found[2]))
        selector='#preview-content .hrs-mermaid-render > svg'
        p.wait_for_function('text=>[...document.querySelectorAll("#preview-content .doc-block")].every(b=>b._sourceDocument===text)&&!!document.querySelector("#preview-content svg")',arg=placed)
        observed=geometry(p,selector)['nodes']['B'];self.assertAlmostEqual(observed['x'],wanted[0],delta=.01);self.assertAlmostEqual(observed['y'],wanted[1],delta=.01)
        p.locator('#btn-undo').click();self.assertEqual(value(p),text)
        p.locator('#btn-redo').click();self.assertEqual(value(p),placed)
        with p.expect_response(lambda r:'/api/save' in r.url and r.request.method=='POST') as pending:p.locator('#btn-save').click()
        self.assertTrue(pending.value.ok,pending.value.text());self.assertEqual((self.project/'report.md').read_bytes(),placed.encode('utf8'))
        p.reload();p.wait_for_function('typeof ReportStudioProgrammatic!=="undefined"');p.evaluate('async id=>{await ReportStudioProgrammatic.ready();await ReportStudioProgrammatic.open(id)}',did)
        p.wait_for_selector(selector);self.assertEqual(value(p),placed)
        observed=geometry(p,selector)['nodes']['B'];self.assertAlmostEqual(observed['x'],wanted[0],delta=.01);self.assertAlmostEqual(observed['y'],wanted[1],delta=.01)
        p.locator('#preview-content .mermaid-card').dblclick();p.locator('#modal-body [data-node="B"]').click()
        if self.evidence:p.locator('#modal-body').screenshot(path=str(self.evidence/'dragged.png'))
        p.locator('[aria-label="节点文字"]').fill('修改后的节点\n第二行');p.locator('#modal-ok').click()
        p.wait_for_function('document.querySelector("#preview-content").textContent.includes("修改后的节点")')
        observed=geometry(p,selector)['nodes']['B'];self.assertAlmostEqual(observed['x'],wanted[0],delta=.01);self.assertAlmostEqual(observed['y'],wanted[1],delta=.01)
        p.locator('#btn-undo').click();self.assertEqual(value(p),placed)
        p.wait_for_function('text=>[...document.querySelectorAll("#preview-content .doc-block")].every(b=>b._sourceDocument===text)&&!!document.querySelector("#preview-content svg")',arg=placed)
        p.locator('#preview-content .mermaid-card').dblclick();p.get_by_role('button',name='自动布局',exact=True).click()
        self.assertNotIn('%% pos',p.locator('.diagram-source-input').input_value())
        if self.evidence:p.locator('#modal-body').screenshot(path=str(self.evidence/'automatic.png'))
        p.locator('#modal-ok').click();self.assertEqual(value(p),text)
        self.assertEqual((self.project/'report.md').read_bytes(),placed.encode('utf8'),'Unsaved layout reset overwrote the saved project')
        self.assertEqual(self.external,[])

if __name__=='__main__':unittest.main(verbosity=2)
