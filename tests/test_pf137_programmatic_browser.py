"""B1: opt-in headless calls reuse the real renderer without editor UI changes."""
import hashlib,json,os,re,sys,tempfile,threading
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]/'app'
sys.path.insert(0,str(ROOT))
from studio import StudioServer
from portable_host import PortableHandler,WindowSessions

with tempfile.TemporaryDirectory(prefix='hrs-programmatic-test-') as directory:
    folder=Path(directory);project=folder/'project';project.mkdir()
    raw=b'# Programmatic report\n\nExact source.\n'
    (project/'report.md').write_bytes(raw)
    server=StudioServer(('127.0.0.1',0),project,folder/'workspace')
    server.RequestHandlerClass=PortableHandler
    server.portable_lifecycle=WindowSessions('programmatic-test',enabled=False)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base='http://127.0.0.1:'+str(server.server_port)
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=os.environ['CHROMIUM_PATH'],headless=True)
            page=browser.new_page()
            page.goto(base+'/web/index.html',wait_until='load')
            assert page.evaluate('typeof window.ReportStudioProgrammatic')=='undefined'
            page.goto(base+'/web/index.html?programmatic=1',wait_until='load')
            result=page.evaluate('''async()=>{const api=ReportStudioProgrammatic;await api.ready();await api.open('legacy');
                const html=await api.exportHTML({quality:'original',sourceMode:'recompilable'});
                const doc=new DOMParser().parseFromString(html,'text/html');
                return {schema:api.schema,payload:JSON.parse(doc.getElementById('report-source').textContent)};}''')
            assert result['schema']=='hrs-programmatic-v1'
            assert result['payload']['markdown'].encode('utf8')==raw
            assert result['payload']['snapshot']['markdownSha256']==hashlib.sha256(raw).hexdigest()
            # API-01: a second open must not race the first load/revision state.
            rejected=page.evaluate('''async()=>{const api=ReportStudioProgrammatic;
                const opening=api.open('legacy');await Promise.resolve();
                let rejected=false;try{await api.open('legacy');}catch(e){rejected=/in progress/.test(e.message);}
                await opening;return rejected;}''')
            assert rejected, 'Concurrent programmatic opens must be rejected'
            assert (project/'report.md').read_bytes()==raw
            assert not list((project/'output').iterdir())
            browser.close()
        print('BROWSER programmatic: normal context unchanged; opt-in original export, exact source, no save or output side effects PASS')
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
