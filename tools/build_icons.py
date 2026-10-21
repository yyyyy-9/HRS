"""Rasterize the reviewed SVG into PNG/Windows ICO via the optional CLI browser.

No redraw, network, or runtime dependency is added to the portable application.
"""
import argparse,base64,struct
from pathlib import Path
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--browser',required=True);a=p.parse_args()
    root=Path(__file__).resolve().parents[1]/'app/web'
    svg=(root/'app-icon.svg').read_bytes()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as api:
        browser=api.chromium.launch(executable_path=a.browser,headless=True)
        page=browser.new_page();page.set_content('<canvas></canvas>')
        def raster(size):
            return base64.b64decode(page.evaluate("""async ({src,size})=>{
              const img=new Image();img.src=src;await img.decode();
              const canvas=document.querySelector('canvas');canvas.width=size;canvas.height=size;
              canvas.getContext('2d').drawImage(img,0,0,size,size);
              return canvas.toDataURL('image/png').split(',')[1];
            }""",{'src':'data:image/svg+xml;base64,'+base64.b64encode(svg).decode(),'size':size}))
        (root/'app-icon.png').write_bytes(raster(512))
        sizes=(16,20,32,48,64,128,256);images=[raster(s) for s in sizes]
        offset=6+16*len(sizes);header=struct.pack('<HHH',0,1,len(sizes));entries=[]
        for size,data in zip(sizes,images):
            entries.append(struct.pack('<BBBBHHII',0 if size==256 else size,0 if size==256 else size,0,0,1,32,len(data),offset));offset+=len(data)
        (root/'app-icon.ico').write_bytes(header+b''.join(entries)+b''.join(images));browser.close()
    print('Generated PNG 512px and ICO 16/20/32/48/64/128/256px from supplied SVG')
if __name__=='__main__':main()
