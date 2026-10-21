#!/usr/bin/env python3
"""Read-only module and report-IR inventory for the Markdown/Agent tool.

Usage (from repository root):
  python tools/audit_modules.py --write    # refresh docs/MODULE_CATALOG.json
  python tools/audit_modules.py --check    # validate current catalog, no writes
  python tools/audit_modules.py --json     # print live inspection to stdout

It never reads the user's external project or executes JavaScript. Python names
come from AST; JS exports are matched as visible source declarations. Consumers
should call report_contract.analyze; the catalog is inventory only.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from release_info import load_release
CATALOG=ROOT/'docs/MODULE_CATALOG.json'
# Names verified from source, not guessed reflection values.
DEFS=[
 ('host_services','host_services.py','host-adapter','private optional desktop PDF capability; existing source/resource/output checks stay in studio',
   ['desktop_bridge','render_desktop_pdf','watch_desktop_parent','release_desktop_windows'],'owning host environment and checked temporary HTML','native PDF / owner-bound lifecycle','explicit print and owned leases only; never source or arbitrary output','not-semantic'),
 ('output_preflight','web/preflight.js','output-policy','complete text diagnostics over Python IR plus shared Marked/SourceMap/notes; partial APIs remain explicit',
   ['complete'],'current source snapshot, IR and existing model','complete text preflight receipt','read-only','entry-check'),
 ('ui_operations','web/operations.js','ui-lifecycle','shared nested leases and request deadlines/cancellation without premature unlock',
   ['create','request'],'current UI controls/editor and bounded requests','owned leases/structured request errors','temporary UI only','not-semantic'),
 ('preview_commit','web/preview_commit.js','presentation','reuse unchanged safe prose DOM and keep current source metadata; structural changes retain full rendering',
   ['reusable','commit'],'current/staged DOM and existing SourceMap','reconciled preview','DOM only','display-only'),
 ('report_workspace','report_workspace.py','owned-project-metadata','owned report metadata, lifecycle/copy jobs and reviewed origin-range sync through existing report commits',
   ['info','list_reports','lifecycle','WorkspaceJobs','CopyAsset'],'owned workspace and source document identity','validated temporary report state/jobs','owned lifecycle only; creation reuses Handler atomic transaction','not-semantic'),
 ('report_workspace_ui','web/report_workspace.js','source-ui','select whole/topic or resume an existing report; original app owns transition and native Word calls',
   ['choose','createJob'],'source-bound topic choices and recoverable reports','explicit lifecycle/selection and progress','explicit owned report actions; original project unchanged','never-source-of-truth'),
 ('source_projection','web/source_projection.js','source-projection','CodeMirror same-document visible range, hidden-note protection and footnote boundary hints',
   ['attach'],'existing editor and SourceMap UTF-16 ranges','display decorations and guarded native transactions','same source buffer; no persistence','secondary'),
 ('notebook_view','web/notebook_view.js','source-projection','H1 topics, extra blank-line gaps and standalone definition closure over the existing lexer/source map',
   ['index','title'],'full source/Marked tokens/SourceMap','read-only topic ranges and independently compilable excerpts','source unchanged','secondary'),
 ('preview_images','web/preview_images.js','presentation','lazy preview images, bounded intrinsic size cache and viewport anchor restoration',
   ['attach','dimensions'],'preview/scroller and existing viewport callbacks','lazy loading and cached image dimensions','temporary DOM/cache only','display-only'),
 ('module_exports','module_exports.py','export-transaction','private staged module HTML and atomic single HTML/ZIP delivery using original source/asset checks',
   ['ModuleExports'],'source-bound module requests and audited HTML','complete independent HTML files in project output','explicit export writes only; never source','not-semantic'),
 ('installed_cli','cli.py','application-entry','standard Python/conda command delegates to the existing local host with user data outside installed resources',
   ['main','user_data_root','capabilities'],'explicit action and optional data root','local host lifecycle or read-only identity/license','start/stop only after explicit action','not-semantic'),
 ('installed_package','__init__.py','application-entry','import-only package marker without server or user-state writes',
   [],'package import','no server','read-only','not-semantic'),
 ('installed_module','__main__.py','application-entry','python -m entry delegates to the same installed CLI',
   [],'CLI arguments','existing CLI result','explicit action only','not-semantic'),
 ('product_defaults','product_settings.py','product-configuration','single JSON owner for palette/profile choices, labels and render-option defaults; immutable Python view',
   ['load_settings'],'product_settings.json','validated immutable catalog','read-only','not-semantic'),
 ('browser_defaults','web/product_settings.js','generated-configuration','generated immutable browser view of product_settings.json; checked by build_settings.js',
   ['ReportSettings'],'canonical product JSON','identical browser catalog','generated only','not-semantic'),
 ('release_identity','release_info.py','release-configuration','release.json reader shared by service, source builder and documentation gates; protocol versions remain independent',
   ['load_release'],'release.json','derived display identity and package stem','read-only','not-semantic'),
 ('color_theme','web/color_theme.js','presentation-configuration','independent palettes and bounded transactional stylesheet loading with previous-theme rollback',
   ['normalize','fromURL','path','apply'],'explicit UI/URL or restored palette','palette stylesheet and root setting','presentation only','not-semantic'),
 ('palette_configuration','color_theme.py','project-settings','validated independent color_theme metadata; source and engineering rules unchanged',
   ['normalize','read'],'optional project metadata','allowed palette name','read-only','not-semantic'),
 ('object_clipboard','object_clipboard.py','resource-import','validates fragment identities and resource bytes, remaps declared objects and internal references, stages imported assets',
   ['copy_bundle','paste_bundle'],'explicit clipboard fragment and existing IR','validated new source and draft assets','writes draft assets after candidate validation','indirect'),
 ('source_clipboard','web/object_clipboard.js','source-ui','one clipboard and local-image adapter for source cards, selection and Markdown import',
   ['copy','paste','importMarkdown'],'explicit source selection and clipboard/files','existing editor change transaction','explicit clipboard reads/writes and draft import','never-source-of-truth'),
 ('project_commit','project_commit.py','project-write','shared revision-checked lock, backup and atomic report commit for editor and explicit block apply',
   ['report_lock','backup_report','commit_report','commit_report_locked'],'current source bytes and expected SHA-256','backup path and committed report','writes original only inside explicit commit','primary'),
 ('block_commands','block_cli.py','programmatic-block-write','plans one existing IR block edit and explicitly applies a reviewed snapshot-bound candidate',
   ['plan','write_plan','apply_plan','main'],'source, target, replacement, expected source/plan SHA-256','candidate, diff or explicit commit receipt','plan new files; apply original with shared backup/atomic save','primary'),
 ('render_profile','web/render_profile.js','output-policy','shared source-map projection for free/engineering display, chapter labels, abstract role and explicit Word decoration downgrade',
   ['normalize','html','plan','wordTokens'],'existing Markdown tokens/source map and profile','derived labels/roles/diagnostics; source unchanged','display/output only','primary'),
 ('profile_configuration','render_profile.py','project-settings','validated optional meta.json render_profile; never a second content source',
   ['normalize','read','normalize_options','read_options','output_checks','require_output'],'existing project metadata and parsed IR headings','profile, options and shared output diagnostics','read-only','primary'),
 ('html_commands','html_cli.py','programmatic-html','HRS-owned optional command adapter calling the original renderer/export/archive with private project snapshots',
   ['export_html','recover_html','browser_session','main'],'explicit project or HRS HTML and new output path','UTF-8 JSON receipt and new HTML/project','temporary local service/browser; writes explicit new output only','primary'),
 ('html_asset_references','html_assets.py','resource-contract','discovers HTML image dependencies without rendering or inventing objects',
   ['references','ImageReferences'],'Markdown outside code/comments/raw text','image paths and source positions','read-only','primary'),
 ('safe_html','web/safe_html.js','html-security','shared inert allowlist for Markdown preview, inline table text and reading packs',
   ['fragment','assetPath','safeLink','hasHTML'],'HTML from the original Markdown renderer','fresh safe display nodes','DOM only; source unchanged','display-only'),
 ('agent_readonly','agent_readonly.py','agent-api-read','local stdout-only AI Agent A0: object, reference and diagnostic queries with snapshot and explicit structural-only scope',
   ['project','analyze_file','main'],'explicit report.md or project path','hrs-agent-read-v1 stdout JSON','read-only; no project writes or HTTP RPC','primary'),
 ('readable_docs_builder','tools/build_readable_docs.js','docs-build','deterministic offline Markdown help compiler using bundled Marked and trusted reader',
   ['build','imageData','main'],'canonical app/docs/*.md and bundled guide images','eleven offline HTML documents from seven canonical Markdown sources','writes application docs only under explicit --write','exclude'),
 ('ui_theme_tokens','web/design_tokens.css','presentation','shared structural dimensions and aliases to independent palette properties',
   [],'document root','design tokens','CSS only','not-semantic'),
 ('shared_surface_components','web/surface_components.css','presentation','canonical table/window toolbar, caption, grid and code-card surface style',
   [],'table/code DOM','shared screen, print and help CSS component rules','CSS only','not-semantic'),
 ('readable_docs_theme','tools/readable_docs_theme.css','docs-style','single-page help-specific styling layered over shared reader',
   [],'generated help HTML','CSS presentation','CSS only','not-semantic'),
 ('report_contract','report_contract.py','report-ir','validates Markdown source and produces read-only engineering-report-ir-v1',
   ['analyze','validate_table','validate_figure','parse_image_group'], 'Markdown and project assets', 'JSON IR, errors, dependencies', 'read-only', 'primary'),
 ('asset_housekeeping','asset_housekeeping.py','project-maintenance','explicitly scans, quarantines and restores unreferenced project assets without altering report source',
   ['AssetHousekeeper'],'saved project and recovery/history Markdown','asset groups and reversible project-local trash batches','project writes only after user confirmation','exclude'),
 ('project_workspace','project_workspace.py','project-management','validates external project directories and handles copy/migration',
   ['validate_project_name','pick_project_parent','pick_import_file','copy_project_tree','ProjectRegistry','is_link'],'explicitly chosen directory','project location / registry','writes only on explicit operation','indirect'),
 ('markdown_import','markdown_import.py','local-import','reads an explicitly selected MD and adapts existing IR/assets into a complete draft payload',
   ['prepare_markdown_import'],'one native-selected MD and its relative images','existing rewritten Markdown and validated asset payload','read-only original','indirect'),
 ('studio_http','studio.py','local-api','local document server, assets, validation, drafts, save and export',
   ['StudioServer','Handler','normalize_svg','check_image'],'browser HTTP requests','JSON API / binary resources','reads/writes projects and drafts','do-not-import'),
 ('native_picker','native_picker.py','windows-navigation','Common Item Dialog with per-action successful-directory memory; history never grants file access',
   ['PickerHistory','configure','choose'],'explicit native dialog action','selected path or cancellation','user selection and navigation preferences','exclude'),
 ('word_export','word_export.py','word-export-adapter','native-selected templates and offline Bridge/WPS subprocess; no duplicate compiler',
   ['WordExport','runtime_paths','check_template'],'current frozen HRS project and selected template','DOCX and existing Bridge provenance','explicit output and local preference writes','delegates'),
 ('word_export_ui','web/word_export.js','browser-ui','theme-aware beta entry, Word template chooser, progress, errors and result actions',
   ['open'],'editor snapshot via callback','Word export UI requests','explicit user actions only','never-source-of-truth'),
 ('bridge_word_model','web/bridge_model.js','generated-bridge-adapter','exact copy of canonical Bridge browser_model.js; reuses current HRS lexer/profile and graphical renderer',
   ['build','render'],'source-bound Bridge request','existing engineering tokens and PNG renditions','no source writes; bounded canvas','delegates'),
 ('clipboard_graphics','clipboard_graphics.py','graphics-io','reads Windows clipboard EMF/PNG/DIB and produces raster preview',
   ['ClipboardGraphic','validate_emf','emf_to_png','read_windows_graphic'],'Windows clipboard / EMF','source bytes / PNG preview','reads OS clipboard','indirect'),
 ('pdf_graphics','pdf_graphics.py','graphics-io','single-page PDF figure raster preview with original PDF preserved',
   ['PdfPreview','validate_pdf','png_dimensions','render_pdf_preview'],'PDF bytes','PNG preview, dimensions','temporary files / Windows PDF renderer','indirect'),
 ('svg_prolog','svg_prolog.py','graphics-security','normalizes SVG document prolog without external DTD fetch',
   ['safe_svg_prolog'],'SVG bytes','normalized bytes','read-only','indirect'),
 ('reference_context','reference_context.py','reference-mask','masks code, URLs and unsafe places for reference checking',
   ['masked_context','label_key'],'Markdown text','masked text','read-only','primary'),
 ('reading_pack','reading_pack.py','reader-only','isolated ZIP/directory Markdown browsing',
   ['ReadBundle','ReadPackManager','normalized_reference'],'explicit external ZIP or folder','read-only Markdown and media','memory session only','exclude'),
 ('portable_host','portable_host.py','windows-launch','portable local web server and browser lifecycle',
   ['PortableServer','PortableHandler','start','stop'],'Windows launcher / local session','server and browser window','service lifecycle','exclude'),
 ('portable_sessions','portable_sessions.py','windows-launch','session lease and disconnection timeout',
   ['WindowSessions','WindowLease'],'browser sessions','lease state','memory state','exclude'),
 ('portable_transport','portable_transport.py','windows-launch','simple control transport for portable host',
   ['read_control','write_control'],'local transport stream','control messages','local transport','exclude'),
 ('vector_conversion','vector_conversion.py','legacy-optional','optional EMF-to-SVG experiment; NOT HF8 default',
   ['try_emf_svg','find_inkscape'],'EMF bytes','optional SVG','may use external Inkscape if requested','exclude'),
 ('app_ui','web/app.js','browser-ui','main editor UI orchestration, captions, references and export',
   ['insertCommand','insertObjectReference','numberObjects','insertSectionReference'],'editor state / browser DOM','visual preview and UI events','modifies editor state via explicit action','never-source-of-truth'),
 ('source_blocks','web/source_blocks.js','source-map','source block/fold ranges and explicit saved-image promotion through existing figure serialization',
   ['scan','readObject','normalized','replacement','lexer'],'Markdown text and optional full-document link definitions','source ranges, raw objects and the configured original Marked lexer','read-only','reference'),
 ('document_search','web/document_search.js','read-only-search','whole Markdown string or rendered text search with source fold navigation and temporary display ranges',
   ['attach'],'current Markdown, rendered DOM and explicit literal query','transient match count and current selection/range','read-only source; UI only','display-only'),
 ('document_search_styles','web/document_search.css','presentation','theme-aware non-modal find bar and temporary current-match paint',
   [],'find UI and active rendered text range','search presentation only','CSS only','not-semantic'),
 ('source_actions','web/source_actions.js','source-ui','exact folded source selection, clipboard and deletions through existing editor history',
   ['attach'],'current editor source/ranges','source selection / commands','explicit clipboard and source edit','exclude'),
 ('note_syntax','web/note_syntax.js','presentation','shared Marked highlight and footnote extensions without source rewriting',
   ['installMarked','prepare','finalize','bindNavigation','hasRich'],'Marked tokens and DOM','note markup / derived footnote navigation','Marked registration and presentation DOM','policy-gated'),
 ('external_links','web/external_links.js','browser-ui','route explicit web-link clicks to the local system-browser API',
   ['attach','decorate','externalURL'],'user click / safe URL','system browser request','explicit external application launch','exclude'),
 ('mathjax_boldsymbol','web/vendor/input/tex/extensions/boldsymbol.js','vendor','exact MathJax 3.2.1 offline boldsymbol component; main bundle unchanged',
   [],'TeX boldsymbol','native MathJax math variant','MathJax extension registration','not-omml-validation'),
 ('source_map','web/source_map.js' ,'source-map','maps existing Marked block/link-definition tokens to UTF-16 source ranges',
   ['create','assertRange','rebaseUnchanged','taskRanges','listFrames','textFrame','replaceNormalizedText'],'Markdown / Marked tokens','source ranges','read-only until UI applies edit','reference'),
 ('native_pipe_tables','web/pipe_tables.js','table-model','parse and serialize native GFM pipe tables and preserve alignment/caption',
   ['parseRaw','stringify','requiresPromotion','promoted'],'original Markdown GFM table','editable logical grid or canonical GFM text','read-only helper; caller handles user confirmation','primary'),
 ('report_tables','web/report_tables.js','table-model','HTML/TSV paste and logical merged-cell table operations',
   ['parseTSV','parseHTML','logicalGrid','validateWidths'],'clipboard cells / table object','normalized grid / new table object','read-only helpers; calling UI decides write','secondary'),
 ('table_editor','web/table_editor.js','browser-ui','visual structured table editing modal',
   ['open'],'table model / browser event','updated table model','temporary UI state','never-source-of-truth'),
 ('dialogs','web/dialogs.js','browser-ui','in-page confirmation dialog and focus trapping shared by editor and table editor',
   ['confirm','trapFocus','isOpen'],'UI message','user decision (boolean)','temporary DOM only','never-source-of-truth'),
 ('report_layout','web/report_layout.js','image-group-model','parses/serializes image group Markdown fences and attributes',
   ['parseGroup','groupSnippet','validateGroup'],'Markdown group fence / model','group model / Markdown snippet','read-only helpers','secondary'),
 ('list_styles','web/list_styles.js','list-style','Markdown list style hints and semantic HTML list rendering',
   ['listSnippet','installMarked'],'Markdown + list style','Markdown source / Marked extension','global Marked extension','needs-word-mapping'),
 ('table_content','web/table_content.js','inline-tokenizer','splits structured table cell text into text and math',
   ['tokenize'],'cell text','$ or \\(...\\) inline / block math token spans','read-only','secondary'),
 ('code_highlight','web/code_highlight.js','presentation','code and GFM native table syntax highlighter in source/preview',
   ['language','sourceTokens','highlightHTML'],'Markdown fenced code','highlight spans','read-only visual','exclude'),
 ('inline_formula','web/inline_formula.js','presentation','inserts inline TeX without changing original semantics',
   ['inlineSnippet'],'selected editor text','Markdown $...$ snippet','read-only helper','secondary'),
 ('mermaid_renderer','web/mermaid_renderer.js','presentation','official local Mermaid rendering shared by editor, dialogs and reading packs; asynchronous cache and unique SVG identities',
   ['render','into','renderAll'],'complete Mermaid source / trusted palette','safe standalone SVG','temporary DOM and bounded render cache','needs-vector-rendition'),
 ('diagram','web/diagram.js','mermaid-editor-helper','optional simple-node editing model; never gates complete Mermaid rendering',
   ['parse'],'Mermaid source','editable diagram model','read-only parse','needs-vector-rendition'),
 ('export_archive','web/export_archive.js','archive','HTML v2 recompilable asset index and SHA-256 verification',
   ['buildArchive','readArchive'],'Markdown and graph assets','v2 HTML embedded archive','constructs export only','reference'),
 ('export_rendition','web/export_rendition.js','presentation','DPI-dependent bitmap downscaling for HTML export',
   ['rendition'],'image bytes / physical width','image bytes for HTML','canvas bitmap rendering','exclude'),
 ('browser_object_catalog','web/object_catalog.js','object-contract','single browser-side validation and derived-numbering semantics for editor/source/reader',
   ['tableValidate','figureValidate','validObject','numbering','indexDOM','indexSource','sourceTexts'],'validated DOM, parsed object records and SourceMap','semantic object counts, numbers, lookup and dependency text','read-only','primary'),
 ('standalone_reader_core','web/report_reader_core.js','reader-source','authoritative offline reader interaction logic; shared catalog injected by bundle',
   ['objectOutline','installTableCards','mount'],'rendered document DOM','offline reader navigation and copy/fold','DOM-only','exclude'),
 ('standalone_reader_builder','tools/build_reader_bundle.js','reader-build','deterministic offline report_reader.js generator from catalog and reader core',
   [],'canonical JS modules','standalone browser reader JS','writes bundled app reader only with --write','exclude'),
 ('html_report_reader','web/report_reader.js','generated-presentation','generated and byte-checked standalone reader: offline section navigation and dual object lists (chronological / figure-table-equation categories), search, copy/fold, zoom, back-to-top',
   ['headingOutline','mount','init','pdfAssetStore'],'rendered HTML DOM','navigation, copy and zoom controls','DOM only: never mutates source JSON or Markdown','exclude'),
 ('html_report_reader_styles','web/report_reader.css','presentation','offline interactive reader layout; print hides navigation, search, lightbox and buttons',
   [],'static reader DOM','responsive and print styles','CSS only','not-semantic'),
 ('reading_pack_ui','web/reading_pack.js','reader-only','read-only external Markdown reader UI',
   ['resolveRelative','closeReader'],'selected ZIP / folder','read-only preview','UI memory state','exclude'),
 ('print_styles','web/print.css','presentation','offline HTML print layout and figure/list/table styles',
   [],'semantic HTML','CSS layout','CSS only','not-semantic'),
 ('editor_styles','web/style.css','presentation','interactive editor UI styling',
   [],'browser DOM','CSS layout','CSS only','not-semantic'),
 ('pipe_table_contract','pipe_table_contract.py','source-contract','read-only GFM pipe table scanner and Quarto tbl-id parser for Python IR',
   ['parse_at','split_cells'],'Markdown source lines','IR table with precise source ranges','read-only','primary'),
 ('equation_contract','equation_contract.py','source-contract','parse $$ and \\[ ... \\] display math, with opt-in stable IDs for numbered $$ blocks', ['parse_equation'],'Markdown block','equation source record','read-only','primary'),
 ('report_equations','web/report_equations.js','source-contract','shared editor $$ and \\[...\\] equation parsing; stable IDs only for opt-in $$ blocks', ['parse','snippet','installMarked'],'Markdown block','equation token','read-only helpers','reference'),
 ('codemirror_bundle','web/vendor/source-editor.js','vendor','prebuilt CodeMirror 6 editor; bundled third-party licences',
   [],'editor state','editor DOM and source text','browser only','exclude'),
]


def inventory()->dict:
    modules=[]
    for ident,rel,layer,job,entry,inputs,outputs,effects,word in DEFS:
        path=ROOT/rel
        if not path.is_file():raise ValueError('Missing module: '+rel)
        raw=path.read_bytes()
        if path.suffix=='.py':
            tree=ast.parse(raw.decode('utf-8'),filename=rel)
            symbols={n.name for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))}
            # AST exports are top-level only; Handler methods are exposed through the class.
            missing=[name for name in entry if name not in symbols]
        elif path.suffix=='.js':
            src=raw.decode('utf-8')
            # Frontend modules may be browser-only IIFEs. Verify named functions
            # are textually declared and/or object keys, without executing code.
            missing=[name for name in entry if not re.search(r'\b'+re.escape(name)+r'\b',src)]
        else:missing=[]
        if missing:raise ValueError(f'{rel} missing declared entrypoints: {missing}')
        modules.append({'id':ident,'path':rel,'layer':layer,'responsibility':job,
            'entrypoints':entry,'input':inputs,'output':outputs,'side_effects':effects,
            'word_pipeline_role':word,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
            'review_flags':(['large-monolithic-module'] if len(raw)>75000 and rel in ('studio.py','web/app.js') else [])})
    return {'catalog_format':'hrs-module-catalog-v1','app_baseline':load_release()['release'].removeprefix('v'),
            'scope':'source tree only; no external report files are opened',
            'caveat':'This is an interface index, not a Python import dependency graph or a DOCX compiler.',
            'items':modules}


def main()->int:
    parser=argparse.ArgumentParser()
    options=parser.add_mutually_exclusive_group(required=True)
    options.add_argument('--write',action='store_true')
    options.add_argument('--check',action='store_true')
    options.add_argument('--json',action='store_true')
    args=parser.parse_args()
    try:actual=inventory()
    except (SyntaxError,UnicodeError,ValueError,OSError) as err:
        parser.exit(2,'审查失败：'+str(err)+'\n')
    if args.write:
        CATALOG.parent.mkdir(parents=True,exist_ok=True)
        CATALOG.write_text(json.dumps(actual,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
        print('Created:',CATALOG.relative_to(ROOT),'('+str(len(actual['items']))+' modules)')
    elif args.check:
        try:previous=json.loads(CATALOG.read_text('utf-8'))
        except (OSError,json.JSONDecodeError) as err:
            parser.exit(2,'清单未生成或不可读：'+str(err)+'\n')
        if previous!=actual:parser.exit(1,'源码与模块目录不一致：请先人工审查变更，再运行 --write 重建\n')
        print('Module audit OK:',len(actual['items']),'modules, SHA-256 and entrypoints matched')
    else:print(json.dumps(actual,ensure_ascii=False,indent=2))
    return 0

if __name__=='__main__':raise SystemExit(main())
