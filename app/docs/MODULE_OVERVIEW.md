# HTML Report Studio 模块说明

## 统一定义与派生缓存

`release.json`只维护产品版本和包修订，`release_info.py`派生服务、构建与帮助使用的身份；运行界面从health读取同一结果。协议schema和安全信任摘要有独立生命周期，不随产品发布机械变更。

`product_settings.json`只维护产品级选择目录、中文标签、配色样式文件以及新稿／旧工程显示默认值。`product_settings.py`提供不可变Python视图；`tools/build_settings.js`生成不可变的`web/product_settings.js`，构建和文档门禁检查同源。界面主题颜色仍由theme*.css维护；高亮语义颜色/符号映射由product_settings唯一维护；渲染语义仍归原ReportProfile，归档边界不另写主题目录和默认值。

`SourceMap.create`复用已有tokens，位置/行号二分查找，对象身份索引按实际赋值失效重建。app只缓存一个正在编辑的源快照，不持久化第二份模型；章号和摘要集合在本次渲染建立；preview_commit.js只复用未变安全正文DOM，结构/对象变化不增量猜测语义，目录/定义行更新位置但保持节点。呈现设置写入复用同一请求适配并绑定文稿会话。

源码范围映射同时处理CRLF与Marked行首Tab展开，原文不改写。`rich_clipboard.js`仅适配剪贴板HTML：惰性解析后将正文变成字面文本、图片和表格变成既有对象；`clipboard_document.py`在显式同源粘贴时读取同一Windows快照，优先取得可对应的RTF原图片，或只读取该HTML声明的本地图片。资源校验、身份、草稿暂存与一次源码提交仍由原`object_clipboard`链持有，不另建文稿、编号或保存逻辑。

## 同源桌面宿主

浏览器与桌面共用同一App；`desktop/`只维护窗口、私有preload、固定运行库和更新器。`host_services.py`适配私有PDF和父进程句柄，`portable_host/portable_window`继续拥有页面租约；窗口关闭共用app的原草稿冲刷，不另存正文。`host_capabilities.json`定义核心支持的宿主协议，产品版本仍来自release.json。原build_release可由同一冻结负载生成两端，独立verify_desktop核对最终包与Python/Word组件，详见源码安装说明。

## Word beta 界面适配

web/word_export.js 管模板选择、生成状态、错误和打开成品；word_export.py 只用标准库管理本机选择凭据、工程模板偏好与独立子进程。studio.py 复用现有 IR、revision 和正式／草稿附件校验冻结快照；独立便携包的 word_support 包含原 Bridge／WPS 核心与四个库，复用自带 Python；同源 browser_model.js 由当前页面提供模型，prepare／提交绑定快照，不另起 Node 或浏览器。原生公式才使用可选 Pandoc。Full 继续支持原完整 CLI。源范围、编号、模板契约和 Word 原生对象规则仍归原项目，不在 HRS 增加第二套编译器。

report_workspace.js提供范围/恢复/管理选择与任务进度，report_workspace.py管理有界任务、分块附件和可逆生命周期；studio.py只沿原revision/资源/目录选择接口提交。operations.js集中UI租约和请求期限，避免相互解锁。临时稿默认独立；用户审查差异并确认后，可沿冻结范围/共享定义显式同步，复用原锁/备份/原子保存。独立保存另分配新身份，旧临时稿保留。图片对象转换在确认目录后应用，取消选择不改写源文。preflight.js统一页面输出诊断，Python接口只标出源码契约范围；安装cli委托这些已有读/检查/提交/HTML实现。

## 渲染与输出配置

`web/render_profile.js`在原Marked和SourceMap上派生两模式的章号、摘要范围、HTML显示策略及Word装饰降级；编辑器、阅读包与Bridge共用它。`render_profile.py`验证模式与显示选项，并消费既有IR提供工程标题输出检查；文档检查、HTML CLI和Bridge调用同一规则。它们不建立第二份对象IR，不改变内容真源、编号对象身份或资源校验。

`web/color_theme.js`与`color_theme.py`消费统一配色目录，管理工程/草稿配置及临时输出覆盖；theme*.css集中颜色，design_tokens.css只维护尺寸结构。表格命名和简洁操作栏在object_catalog.js，Reader由它与report_reader_core.js经原生成器构建。自由HTML任务的localStorage只记录本机阅读状态，不回写源归档；帮助固定蓝色并沿用原Markdown生成器。

当前发布身份以`release.json`和[当前状态](CURRENT_STATUS.md)为准。本页说明当前程序由哪些模块组成、数据如何流转、各层负责什么。具体语法以[源格式规范](../source_format_v1.md)为准；操作方法见[使用手册](USER_GUIDE.md)，版本演进见[更新记录](CHANGELOG_READABLE.md)。

## 自由台账的派生视图与交付

`web/notebook_view.js` 只消费原Marked/SourceMap，派生H1专题范围、顶层额外空行和分册定义依赖；`object_catalog.indexSource` 复用原numbering函数取得全文对象序列，DOM呈现使用同一序列。主编辑器缓存一个当前全文快照的词法/范围/对象/脚注结果，聚焦只构建选定范围的显示节点。source_projection.js使用CodeMirror现有扩展点隐藏范围之外源码和定义，限制本机输入跨界；同一全文缓冲/UTF-16/撤销仍是原真源。脚注定义在独立面板通过原范围事务编辑。source-editor.js只公开既有适配层所需扩展原语，上游载荷保持逐字节原样。编号、目录、引用和全文源码仍完整；不建立第二份持久正文。分册独立派生编号并复用原HTML归档。`preview_images.js` 管理懒加载、有界尺寸缓存及原锚点恢复，成功切稿时清理。

`module_exports.py` 暂存已经通过原审计/源资源校验的HTML；全部完成后原子交付一册或ZIP，失败清理自己的临时文件。工程源、历史和共享资源不因分册删除。界面和显式programmatic调用消费同一实现；原单篇HTML CLI、A0和plan/apply契约保持。

## 内置全文查找

`web/document_search.js`提供非模态Ctrl+F／F3查找栏。源码消费现有完整Markdown字符串，复用SourceBlocks折叠记录和CodeMirror范围／选区；正文消费原预览DOM，跨行内节点建立临时Range，排除隐藏源码及题注镜像重复。查找结果是临时显示状态，不是第二份持久正文或语义解析。`app.js`只负责初始化、视图准备和渲染／修改后的刷新；`document_search.css`仅作用于编辑器查找界面，原Reader／导出CSS和归档语义不变。

## 源码操作、笔记与外链

`web/source_actions.js`通过现有 CodeMirror 视图定位折叠范围，把复制／剪切／删除交回主编辑器和原撤销链。`source_blocks.js`仍输出临时源码范围，原始 HTML 的候选边界由已有 Marked 词法器识别，再平衡外层标签；不建立第二份正文。

`web/note_syntax.js`注册高亮与脚注扩展；八色和清除使用安全源码表示，脚注入口生成源引用/定义；正文、表题和定义由同一个 Marked／安全清洗链渲染，脚注编号按实际引用顺序派生。表格栏镜像题注但不登记额外引用，离线Reader保留语义节点。高亮复杂块保留源码编辑。`render_profile.js`控制工程去装饰，脚注定义和引用由独立Bridge的共用页面模型投影为原生Word脚注；表格编辑器沿原事务提供所有列水平居中。

`web/external_links.js`接管网页链接点击，经同源、显式动作的 `/api/external/open` 请求由本机系统打开 HTTP／HTTPS。独立离线 Reader 只设置新页面打开，不调用本机服务。`app-icon.svg/png/ico`及 manifest 复用已有 R 标记。

离线 MathJax 主包保持 3.2.1，配套本地 `vendor/input/tex/extensions/boldsymbol.js`显式加载；原 TeX 不替换为 mathbf。许可随既有 MATHJAX-LICENSE 分发。

## 内容真源与处理流程

正式内容保存为工程中的 `report.md` 与 `assets/`。编辑器缓冲区用于本次编辑，草稿用于恢复；IR、预览和导出 HTML 都从内容真源派生，不能分别维护成另一份正文。

```text
Markdown 与 assets
  → Python 结构解析 / 校验 → IR 与 Agent 只读结果
  → 浏览器 Markdown 渲染 → 编辑预览 → HTML 导出 / 打印
  → 正式保存、草稿恢复与资源管理
可回编 HTML → 校验归档及资源 → 恢复 Markdown 与 assets
```

Python 和浏览器各有适应运行环境的解析实现，以现行规范及共享用例保持一致。浏览器的对象合法性与派生编号集中在 `object_catalog.js`；离线 Reader 由原有源模块构建，不独立维护第二套编号算法。

## 解析、对象与源码定位

| 模块 | 当前职责 | 输入与输出 |
| --- | --- | --- |
| `report_contract.py` | 结构解析、对象校验、依赖和引用检查 | Markdown、可选资源目录 → `engineering-report-ir-v1` |
| `pipe_table_contract.py`、`equation_contract.py` | 原生管道表、块公式契约 | 原文 → 结构与源范围，保留原始定界符 |
| `html_assets.py` | HTML IMG 附件发现，复用原路径和附件校验，不渲染或编号 | HTML 属性 → 原附件依赖 |
| `reference_context.py` | 屏蔽代码、URL、数学等非引用上下文 | 原文 → 等长扫描上下文 |
| `web/source_blocks.js`、`web/source_map.js` | 专用块/GFM 扫描、UTF-16 定位、快照范围检查 | Markdown 与 Marked token → 源范围 |
| `web/object_catalog.js` | 浏览器对象合法性、编号和 DOM 对象索引 | 结构对象/渲染节点 → 统一对象目录 |
| `agent_readonly.py` | 本地 A0 七种只读查询 | 指定文稿 → stdout JSON，不写工程 |
| `block_cli.py`、`project_commit.py` | 快照约束的 plan/apply，以及编辑器共用的锁、备份、原子提交 | plan只写新候选；显式apply才更新report.md，资源不批量写入 |
| `object_clipboard.py`、`web/object_clipboard.js` | 对象片段身份映射、资源打包及草稿暂存适配 | 消费原IR/源范围；不创建另一份正文模型 |

稳定 ID 标识对象，源码范围绑定同一份快照，显示编号按有效对象顺序派生。普通段落和匿名表格不强制分配 ID；目前没有完整的逐段行内 AST。Agent 的调用、冲突拒绝和范围条件统一见[规范第6节](../source_format_v1.md)。

## 编辑与预览

| 模块 | 当前职责 |
| --- | --- |
| `web/safe_html.js` | 预览、表格行内、阅读包共用的惰性 HTML 标签/属性/样式白名单，不改源文 |
| `web/app.js`、`web/vendor/source-editor.js` | 主界面调度与 CodeMirror Markdown 编辑器，组织预览和用户操作 |
| `web/pipe_tables.js`、`web/report_tables.js`、`web/table_editor.js` | GFM/增强表模型、粘贴与逻辑网格操作、临时表格编辑窗口 |
| `web/report_layout.js` | 组图围栏解析、验证与序列化 |
| `web/list_styles.js`、`web/report_equations.js`、`web/table_content.js` | 列表显示样式、块公式、表格单元格文本/数学分段 |
| `web/mermaid_renderer.js`、`web/vendor/pele/` | 本地完整Pele渲染Mermaid源文，缓存布局、统一主题及MathJax公式；预览、编辑窗口、阅读包共用，HTML/PDF/Word使用固化主题的独立SVG |
| `web/diagram.js`、`web/inline_formula.js`、`web/code_highlight.js`、`web/dialogs.js` | 简单流程图的节点文字/连线编辑辅助、行内公式插入、基础高亮和共用确认窗口；Flow子集不决定正式渲染范围 |
| `web/design_tokens.css`、`web/surface_components.css`、其他现有 CSS | 共享样式与编辑/打印/阅读布局 |

模型助手返回结构或源码片段；程序可用block_cli生成候选，再由显式apply提交。预览折叠、工具栏、阅读导航和代码卡片属于显示层，不产生新的 Markdown 对象。复杂内容继续保留原文，不用可视化近似结果覆盖源内容。

## 本地服务、保存与文档生命周期

`studio.py` 的 `StudioServer` / `Handler` 提供本机 HTTP 服务，协调工程、校验、上传、草稿、正式保存和导出相关请求。正式保存复用已有 revision 冲突检查和原子写入；自动草稿独立于正式 `report.md`。`project_workspace.py` 负责工程路径、注册与显式复制/迁移。

`portable_host.py` 启动服务并选择浏览器，`portable_sessions.py` 管理窗口租约与断开超时，`portable_transport.py` 负责本地控制消息。便携版使用随包 Python 和原启动脚本。服务生命周期能力已存在，不能因尚无 Agent 写接口就另建一套服务或保存机制。

帮助页由现有静态路由提供：`/web/` 是前端资源，`/docs/` 是限定类型的只读文档，另有三份明确公开的根文档。文档路由不允许写入、路径越界或读取程序文件。它不等于 Agent HTTP RPC。

## 图形资源与安全边界

- `clipboard_graphics.py`：Windows 图形剪贴板读取，保留 EMF 原件并生成预览。
- `pdf_graphics.py`：PDF 校验与第一页 PNG 预览，保留原 PDF；实际 DPI/像素信息随预览保存。
- `svg_prolog.py` 与服务内既有 SVG 校验：安全处理 SVG，不抓取外部 DTD。
- `asset_housekeeping.py`：显式检查未使用素材，按资源组移入项目回收区或恢复；确认后按完整扫描快照清空回收批次，拒绝未知文件、链接、内容变化和当前文稿/草稿引用；文件占用时保留可重试状态。常规保存/导出不自动清理资源。
- `vector_conversion.py`：保留的可选 EMF→SVG 实验工具，不是当前默认导入流程。

预览图和 `sourceAsset` 原件分别负责显示与追溯。资源处理受路径、格式、大小及既有验证约束；编辑器不解释图片中的工程参数。

## HTML 导出、阅读与回编

`web/app.js` 组织现有渲染和导出流程；`web/export_rendition.js` 处理输出画质，`web/export_archive.js` 构造/读取可回编归档及 SHA-256 校验。导出的单文件 HTML 可以是纯阅读版或可回编版；只有有效可回编归档才能恢复完整源文和必要原件。

`web/report_reader_core.js` 与对象目录经 `tools/build_reader_bundle.js` 生成 `web/report_reader.js`，提供目录、搜索、对象导航、复制/折叠、图片放大。报告目录覆盖H1—H6，锚点在原导出链生成；预览与导出深层标题字号由各自既有CSS按正文基准控制。它增强已渲染 DOM，不修改 Markdown，也不生成 Word 语义。`reading_pack.py` / `web/reading_pack.js` 是独立的只读 ZIP/目录阅读功能，不自动合并当前工程。

## 帮助构建、模块索引与验证入口

在完整独立源码的 `app/` 目录执行下列检查。三合一 TestOnly 按包根 `run.cmd check` 检查现行资料，不要求它未附带的历史档案；Clean 没有测试，请使用同批测试包：

```powershell
python tools/audit_modules.py --check
node tools/build_readable_docs.js --check
python tools/maintain_docs.py --check
```

`docs/MODULE_CATALOG.json` 是 `audit_modules.py` 生成的逐模块用途、入口、输入/输出、状态影响及哈希索引；本页提供总览，不复制那些指纹。索引不是可随意导入的通用 API，浏览器 IIFE 和 Windows 平台模块仍有运行条件。

`tools/build_readable_docs.js` 使用随包 Marked、Reader 和共用样式，由七份 Markdown 生成十一份帮助 HTML；正文只在 Markdown 维护。Python-only 文档检查可在便携包中运行；Node 用于开发构建及确定性重建检查。源码根 `tools/run_checks.py` 组织现有专项/回归，测试与开发发布工具仅在源码包提供，普通使用不需要安装它们。

## 程序接口与独立下游

编辑器 Agent 提供 A0 读取，没有受控写入。正式版显式 programmatic 上下文提供原浏览器薄入口，html_cli.py 以私有快照/临时服务调用同一渲染和归档链，导出或恢复到新路径并返回 JSON；桥接的 HTML 命令委托它。可选 Playwright 依赖与本机浏览器条件见 README，普通编辑器上下文保持。独立桥接已有块创建/替换候选和单份 HTML 调用，正式提交及批处理按[短期计划](SHORT_TERM_PLAN.md)从具体 Issue 推进。

Word/WPS 编译与逆向识别由独立项目负责，独立桥接试用包消费本项目接口并接入 WPS 模板/Scanner。可用数据、命令和已知限制见[Word/WPS 下游数据接口](WORD_COMPILER_HANDOFF.md)；机器交接索引为 `docs/WORD_IR_HANDOFF.json`。编辑器自身不实现 DOCX/OMML 编译，不承诺任意排版往返。

实际完成度和验证边界见[当前状态](CURRENT_STATUS.md)；长期方向见[长期路线](LONG_TERM_ROADMAP.md)。

## 开发测试与发行工具

源码tools/test_catalog.py持有功能归属、具名用例与保留分组别名，run_checks生成去重计划并持有结果分类，Source/Full共用；run_python_tests仅执行明确选择并隔离所需运行时。tests/browser_support复用实际StudioServer，逐用例隔离context/工程/草稿，清理失败现场，不把模拟API当真实服务。纯测试依赖不进入普通运行包。

build_release从显式SHA绑定的现行便携输入构建源码/运行包，消费同一App清单且不写源；verify_release独立读取实际ZIP、清单和release_policy，检查保护范围及历史，不导入生产者自证。Word组件与模板仍由原项目提供，测试/发布工具不复制转换语义。使用与授权边界见维护规则及源码README_TESTS。

## 混合粘贴的数学适配

clipboard_math.py将同次WPS原生选择中的数学位置绑定到HTML图像，核对源文字、数量和关系；legacy_math.py有界读取MS-CFB/Equation Native/MTEF3常见子集，不激活OLE。OMML/MathML调用原word_export子进程与Bridge MathAdapter批量转换。rich_clipboard仅将成功的TeX接入原对象片段；资源/身份/一次提交仍由object_clipboard持有。编辑器与ZIP阅读页经同一numberObjects入口消费原SourceMap，离线HTML由原Reader重建。编号统一归object_catalog和report_contract，低层公式定界符解析不决定编号显隐。
