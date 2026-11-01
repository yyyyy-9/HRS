"""Wire shapes shared with the generated browser declarations.

These describe transport, not Markdown semantics. Extra fields stay available
for compatible extensions; existing owners still check resources and snapshots.
"""
from typing import Literal, NotRequired, TypeAlias, TypedDict, get_args, get_origin, get_type_hints
import types

JsonValue: TypeAlias = str | int | float | bool | None | list['JsonValue'] | dict[str, 'JsonValue']


class ApiSuccess(TypedDict):
    ok: Literal[True]


class ApiError(TypedDict):
    ok: Literal[False]
    error: str
    code: NotRequired[str]


ApiResponse: TypeAlias = ApiSuccess | ApiError


class SaveResponse(ApiSuccess):
    document_id: str
    revision: str
    saved: bool
    title: str
    theme: str
    warnings: NotRequired[list[str]]
    markdown: NotRequired[str]
    markdown_file: NotRequired[str]


class SourceSnapshot(TypedDict):
    text_utf8_sha256: str
    utf16_length: int
    newline_mode: str
    bom_preserved: bool
    file_sha256: NotRequired[str]


class DocumentResponse(TypedDict):
    ok: Literal[True]
    document_id: str
    markdown: str
    revision: str
    render_profile: NotRequired[str]
    render_options: NotRequired[dict[str, JsonValue]]
    project_path: NotRequired[str | None]


class DraftResponse(TypedDict):
    ok: Literal[True]
    accepted: bool
    seq: int
    markdown_sha256: str


class ClipboardAsset(TypedDict):
    base64: str
    sha256: str


class ObjectBundle(TypedDict):
    format: Literal['hrs-object-clipboard-v1']
    markdown: str
    assets: NotRequired[dict[str, ClipboardAsset]]
    local_images: NotRequired[dict[str, ClipboardAsset]]
    source_key: NotRequired[str | None]
    operation: NotRequired[Literal['copy', 'cut', 'import']]


class WordBrowserModel(TypedDict):
    schema: Literal['hrs-word-browser-model-v1']
    tokens: list[list[JsonValue]]
    inline: list[list[JsonValue]]
    numbering_policy: NotRequired[Literal['document-v2']]
    request_sha256: NotRequired[str]
    render_options: NotRequired[dict[str, JsonValue]]
    profile: NotRequired[dict[str, JsonValue]]
    diagrams: NotRequired[dict[str, JsonValue]]
    svgAssets: NotRequired[dict[str, JsonValue]]
    footnotes: NotRequired[dict[str, list[JsonValue]]]


class WorkspaceStatus(TypedDict):
    state: Literal['running', 'completed', 'failed', 'cancelled']
    phase: str
    bytes_done: int
    bytes_total: int
    result: dict[str, JsonValue] | None
    error: str | None


WIRE_TYPES = (ApiSuccess, ApiError, SaveResponse, SourceSnapshot, DocumentResponse, DraftResponse,
              ClipboardAsset, ObjectBundle, WordBrowserModel, WorkspaceStatus)
WIRE_ALIASES = {'ApiResponse': ApiResponse}


def _matches(value, expected):
    origin, args = get_origin(expected), get_args(expected)
    if origin is NotRequired:
        return _matches(value, args[0])
    if origin is Literal:
        return any(type(value) is type(item) and value == item for item in args)
    if origin is types.UnionType:
        return any(_matches(value, item) for item in args)
    if origin is list:
        return isinstance(value, list) and all(_matches(item, args[0]) for item in value)
    if origin is dict:
        return isinstance(value, dict) and all(_matches(k, args[0]) and _matches(v, args[1]) for k, v in value.items())
    if expected in WIRE_TYPES:
        return isinstance(value, dict) and all(
            (name not in value and get_origin(kind) is NotRequired) or
            (name in value and _matches(value[name], kind))
            for name, kind in get_type_hints(expected, include_extras=True).items())
    # JSON trees are already parsed at these boundaries; their semantics remain
    # owned by the existing token/asset validators, not this transport layer.
    if getattr(expected, '__forward_arg__', None) == 'JsonValue':
        return value is None or isinstance(value, (str, int, float, bool, list, dict))
    return value is None if expected is type(None) else type(value) is expected


def require_wire(value, kind):
    """Validate known transport fields without coercion or dropping extensions."""
    if not _matches(value, kind):
        name=next((name for name,value in WIRE_ALIASES.items() if kind is value),getattr(kind,'__name__',str(kind)))
        raise ValueError('接口字段格式无效：' + name)
    return value
