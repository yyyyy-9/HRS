// Generated from interface_types.py; edit the Python transport types.
type HrsJsonValue = string | number | boolean | null | HrsJsonValue[] | { [key: string]: HrsJsonValue };

interface HrsApiSuccess {
  ok: true;
}

interface HrsApiError {
  ok: false;
  error: string;
  code?: string;
}

interface HrsBlockTimeRecord {
  key: string;
  kind: "heading" | "figure" | "image-group" | "table" | "mermaid";
  id: string | null;
  start: number;
  end: number;
  own_sha256: string;
  content_sha256: string;
  created: string | null;
  modified: string | null;
  pending?: boolean;
}

interface HrsBlockTimestamps {
  schema: "hrs-block-times-v1";
  source_sha256: string;
  records: Array<HrsBlockTimeRecord>;
}

interface HrsSaveResponse {
  ok: true;
  document_id: string;
  revision: string;
  saved: boolean;
  title: string;
  theme: string;
  warnings?: Array<string>;
  markdown?: string;
  markdown_file?: string;
  block_timestamps?: HrsBlockTimestamps;
}

interface HrsSourceSnapshot {
  text_utf8_sha256: string;
  utf16_length: number;
  newline_mode: string;
  bom_preserved: boolean;
  file_sha256?: string;
}

interface HrsDocumentResponse {
  ok: true;
  document_id: string;
  markdown: string;
  revision: string;
  render_profile?: string;
  render_options?: Record<string, string | number | number | boolean | null | Array<string | number | number | boolean | null | Array<HrsJsonValue> | Record<string, HrsJsonValue>> | Record<string, string | number | number | boolean | null | Array<HrsJsonValue> | Record<string, HrsJsonValue>>>;
  project_path?: string | null;
  block_timestamps?: HrsBlockTimestamps;
}

interface HrsDraftResponse {
  ok: true;
  accepted: boolean;
  seq: number;
  markdown_sha256: string;
  block_timestamps?: HrsBlockTimestamps;
}

interface HrsClipboardAsset {
  base64: string;
  sha256: string;
}

interface HrsObjectBundle {
  format: "hrs-object-clipboard-v1";
  markdown: string;
  assets?: Record<string, HrsClipboardAsset>;
  local_images?: Record<string, HrsClipboardAsset>;
  source_key?: string | null;
  operation?: "copy" | "cut" | "import";
}

interface HrsWordBrowserModel {
  schema: "hrs-word-browser-model-v1";
  tokens: Array<Array<string | number | number | boolean | null | Array<string | number | number | boolean | null | Array<HrsJsonValue> | Record<string, HrsJsonValue>> | Record<string, string | number | number | boolean | null | Array<HrsJsonValue> | Record<string, HrsJsonValue>>>>;
  inline: Array<Array<string | number | number | boolean | null | Array<string | number | number | boolean | null | Array<HrsJsonValue> | Record<string, HrsJsonValue>> | Record<string, string | number | number | boolean | null | Array<HrsJsonValue> | Record<string, HrsJsonValue>>>>;
  numbering_policy?: "document-v2";
  request_sha256?: string;
  render_options?: Record<string, string | number | number | boolean | null | Array<string | number | number | boolean | null | Array<HrsJsonValue> | Record<string, HrsJsonValue>> | Record<string, string | number | number | boolean | null | Array<HrsJsonValue> | Record<string, HrsJsonValue>>>;
  profile?: Record<string, string | number | number | boolean | null | Array<string | number | number | boolean | null | Array<HrsJsonValue> | Record<string, HrsJsonValue>> | Record<string, string | number | number | boolean | null | Array<HrsJsonValue> | Record<string, HrsJsonValue>>>;
  diagrams?: Record<string, string | number | number | boolean | null | Array<string | number | number | boolean | null | Array<HrsJsonValue> | Record<string, HrsJsonValue>> | Record<string, string | number | number | boolean | null | Array<HrsJsonValue> | Record<string, HrsJsonValue>>>;
  svgAssets?: Record<string, string | number | number | boolean | null | Array<string | number | number | boolean | null | Array<HrsJsonValue> | Record<string, HrsJsonValue>> | Record<string, string | number | number | boolean | null | Array<HrsJsonValue> | Record<string, HrsJsonValue>>>;
  footnotes?: Record<string, Array<string | number | number | boolean | null | Array<string | number | number | boolean | null | Array<HrsJsonValue> | Record<string, HrsJsonValue>> | Record<string, string | number | number | boolean | null | Array<HrsJsonValue> | Record<string, HrsJsonValue>>>>;
}

interface HrsWorkspaceStatus {
  state: "running" | "completed" | "failed" | "cancelled";
  phase: string;
  bytes_done: number;
  bytes_total: number;
  result: Record<string, string | number | number | boolean | null | Array<string | number | number | boolean | null | Array<HrsJsonValue> | Record<string, HrsJsonValue>> | Record<string, string | number | number | boolean | null | Array<HrsJsonValue> | Record<string, HrsJsonValue>>> | null;
  error: string | null;
}

type HrsApiResponse = HrsApiSuccess | HrsApiError;

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
