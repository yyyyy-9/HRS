"""Installed command adapter; resource files and user state have separate roots."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys

APP = Path(__file__).resolve().parent


def user_data_root():
    explicit = os.environ.get('HRS_DATA_DIR')
    if explicit:
        return Path(explicit).expanduser().resolve()
    if sys.platform == 'win32':
        parent = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData/Local')
    elif sys.platform == 'darwin':
        parent = Path.home() / 'Library/Application Support'
    else:
        parent = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share')
    return (parent / 'HTMLReportStudio').resolve()


COMMANDS = {
    'read': {'module':'agent_readonly','read_only':True,'requires':[],'scope':'source-contract'},
    'plan': {'module':'block_cli','read_only':True,'requires':[],'scope':'candidate-only'},
    'apply': {'module':'block_cli','read_only':False,'requires':[],'scope':'explicit-reviewed-plan-sha256'},
    'html': {'module':'html_cli','read_only':True,'requires':['playwright','local-browser'],'scope':'new-output-only'},
    'check': {'module':'html_cli','read_only':True,'requires':['playwright','local-browser'],'scope':'engineering-text-and-assets'},
}


def capabilities():
    from release_info import load_release
    return {'schema':'hrs-cli-capabilities-v1',**load_release(),'commands':COMMANDS,
            'server_actions':['start','stop','status','info','license'],
            'model_api_client':False,'downstream_word_verification':False}


def main(argv=None):
    # Legacy modules already share this application directory in the portable
    # build. Keep that same boundary in the installed CLI, with no server on import.
    if str(APP) not in sys.path:
        sys.path.insert(0, str(APP))
    from release_info import load_release
    identity = load_release()
    argv=list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0]=='capabilities':
        if len(argv)>1 and argv[1:]!=['--json']:
            raise SystemExit('Usage: hrs capabilities [--json]')
        print(json.dumps(capabilities(),ensure_ascii=False));return 0
    if argv and argv[0] in COMMANDS:
        command=argv.pop(0)
        try:
            from importlib import import_module
            module=import_module(COMMANDS[command]['module'])
            if command=='check':return module.check_main(argv)
            if command in ('plan','apply'):argv.insert(0,command)
            return module.main(argv)
        except (OSError,ValueError,ImportError) as error:
            print(json.dumps({'ok':False,'operation':command,'code':'COMMAND_UNAVAILABLE','error':str(error)},ensure_ascii=False));return 1
    parser = argparse.ArgumentParser(description='HRS local editor and snapshot-bound commands (127.0.0.1 only)',
        epilog='Data commands: hrs read ACTION SOURCE | hrs check SOURCE | hrs plan ... | hrs apply ... | hrs html export/recover ... | hrs capabilities. Use COMMAND --help for options.')
    parser.add_argument('--version', action='version', version=identity['release'])
    parser.add_argument('action', nargs='?', default='start', choices=['start', 'stop', 'status', 'info', 'license'])
    parser.add_argument('--data-dir', type=Path, default=None, help='User state root; never the installed application directory')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--keep-alive', action='store_true', help='Keep the local service until an explicit hrs stop')
    args = parser.parse_args(argv)
    if args.action == 'license':
        print((APP / 'COPYRIGHT').read_text('utf8'))
        print((APP / 'LICENSE').read_text('utf8'))
        return 0
    root = (args.data_dir.expanduser().resolve() if args.data_dir else user_data_root())
    if root == APP or root.is_relative_to(APP):
        parser.error('--data-dir must be outside installed application resources')
    if args.action == 'info':
        rights = json.loads((APP / 'RIGHTS.json').read_text('utf8'))
        print(json.dumps({**identity, 'license': rights['own_license']['selected'],
                          'author': rights['own_license']['holder'], 'app': str(APP),
                          'data_dir': str(root), 'bind': '127.0.0.1'}, ensure_ascii=False))
        return 0
    from portable_host import main as host_main
    command = [args.action, '--root', str(root)]
    if args.no_browser:
        command.append('--no-browser')
    if args.keep_alive:
        command.append('--keep-alive')
    return host_main(command)


if __name__ == '__main__':
    raise SystemExit(main())

