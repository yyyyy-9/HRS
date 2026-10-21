"""Copy/check the canonical Bridge model; never edit the generated HRS copy."""
from pathlib import Path
import argparse,hashlib
ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bridge',type=Path,required=True)
    g=p.add_mutually_exclusive_group(required=True);g.add_argument('--write',action='store_true');g.add_argument('--check',action='store_true')
    a=p.parse_args();raw=(a.bridge/'hrs_bridge/browser_model.js').read_bytes();target=ROOT/'app/web/bridge_model.js'
    if a.write:target.write_bytes(raw)
    else:assert target.read_bytes()==raw,'Generated HRS model differs from canonical Bridge module'
    print('Bridge browser model SHA256:',hashlib.sha256(raw).hexdigest())
