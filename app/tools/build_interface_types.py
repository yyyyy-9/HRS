"""Derive browser wire declarations from the Python transport types."""
import json
from pathlib import Path
import types
from typing import ForwardRef, Literal, NotRequired, get_args, get_origin, get_type_hints

from interface_types import JsonValue, WIRE_TYPES, WIRE_ALIASES


def browser_type(kind):
    if kind == JsonValue:
        return 'HrsJsonValue'
    origin, args = get_origin(kind), get_args(kind)
    if origin is NotRequired:
        return browser_type(args[0])
    if origin is Literal:
        return ' | '.join(json.dumps(item) for item in args)
    if origin is types.UnionType:
        return ' | '.join(browser_type(item) for item in args)
    if origin is list:
        return 'Array<' + browser_type(args[0]) + '>'
    if origin is dict:
        return 'Record<string, ' + browser_type(args[1]) + '>'
    if isinstance(kind, ForwardRef):
        return 'Hrs' + kind.__forward_arg__
    if kind in WIRE_TYPES:
        return 'Hrs' + kind.__name__
    return {str: 'string', int: 'number', float: 'number', bool: 'boolean', type(None): 'null'}[kind]


def declarations():
    result = ['// Generated from interface_types.py; edit the Python transport types.\n',
              'type HrsJsonValue = string | number | boolean | null | HrsJsonValue[] | { [key: string]: HrsJsonValue };\n']
    for kind in WIRE_TYPES:
        result.append('\ninterface Hrs' + kind.__name__ + ' {\n')
        for name, value in get_type_hints(kind, include_extras=True).items():
            optional = '?' if get_origin(value) is NotRequired else ''
            result.append('  ' + name + optional + ': ' + browser_type(value) + ';\n')
        result.append('}\n')
    for name,kind in WIRE_ALIASES.items():
        result.append('\ntype Hrs' + name + ' = ' + browser_type(kind) + ';\n')
    result.append('''
type HrsControl = HTMLButtonElement | HTMLInputElement | HTMLSelectElement;
type HrsRequestError = Error & { status?: number; code?: string };
interface HrsRequestOptions { timeout?: number; signal?: AbortSignal }
declare var module: { exports: unknown };
interface HrsOperationOptions { editor: { readOnly: boolean }; onEditing?: (locked: boolean) => void }
interface HrsLeaseOptions { nodes?: Iterable<HrsControl>; editing?: boolean }
interface HrsOperations {
  acquire(options?: HrsLeaseOptions): () => void;
  setDisabled(node: HrsControl, value: boolean): void;
  readonly busy: boolean;
  readonly editing: boolean;
}
declare var ReportOperations: {
  create(options: HrsOperationOptions): HrsOperations;
  request(path: string, method?: string, data?: HrsJsonValue, headers?: Record<string, string>, options?: HrsRequestOptions): Promise<HrsApiResponse>;
};
''')
    return ''.join(result)


def update(write=False):
    path = Path(__file__).resolve().parents[1] / 'web/interfaces.d.ts'
    expected = declarations()
    if write:
        path.write_text(expected, encoding='utf-8', newline='\n')
    elif not path.is_file() or path.read_text('utf-8') != expected:
        raise ValueError('Interface declarations are stale; run audit_modules.py --write')
