# 工程报告源格式 v1

## 渲染与输出配置

`report.md/assets` 仍为唯一内容真源。工程 `meta.json` 的可选 `render_profile` 为 `free` 或 `engineering`；旧工程缺省为自由模式，新建工程技术报告在编辑器中默认工程模式。模式不等同于配色 `theme` 或新建内容 `template`，切换只保存配置，不改写 Markdown。草稿、可回编 HTML 的可选 `renderProfile` 及恢复工程保留该选择；旧归档没有此项时仍按自由模式解释。CLI 可用 `--render-profile` 临时指定输出，不修改工程配置。

`web/render_profile.js` 消费原词法器和UTF-16源映射派生显示。`render_profile.py::output_checks` 消费同一 Python IR 的标题记录，供文档检查、HTML CLI 和 Bridge 共同使用，不再复制标题解析规则。工程模式H1为不编号题名，H2—H6派生章号；正文、目录及离线HTML使用同一结果。显示号不进入源编辑回写，既有章节引用身份/题名语义不改。多个H1及章节向下跳级是工程输出错误，允许保存未整理的源稿，但阻止工程HTML和Word输出。手工数字前缀为置顶、可定位的提醒；界面按本次源快照确认，CLI须显式接受，不猜改量值或重写旧稿。Word按同一层级契约使用母模板的原生多级编号，正文列表仍独立。

可选配置 `render_options.show_object_numbers`、`show_heading_numbers`、`show_equation_numbers` 必须为布尔值。图表编号在新建自由笔记／导入普通Markdown默认false，旧工程或归档缺省true；章节编号和公式编号缺省false。自由模式可分别切换三项；工程模式固定章节及图表编号，公式编号仍可选。题注、导航、正文引用和HTML服从同一开关。Word按工程规则固定章节及图表编号，公式服从本次源快照的show_equation_numbers。普通／增强表格和普通／对象Mermaid共用序列，不再区分带号插入类型。配置随元数据、草稿、归档、恢复保存，不写进report.md。

独立可选 `color_theme` 为blue/celadon/violet/azure/navy/warm，缺省blue；HTML归档对应colorTheme。它与原内容模板theme、render_profile分开。URL的theme参数只接受清单，default及未知值回退蓝色；CLI --theme可临时覆盖输出，缺省读取工程，--output不被模式前缀改名。HTML带明确free/engineering模式属性和受限meta，纯阅读输出也能按模式呈现。帮助固定原蓝色。


工程摘要仅识别：唯一候选顶层引用块位于题名H1之后、首个H2之前，首段以 `摘要：` 开始，内容为普通段落；连续 `>` 行仍按原引用块范围处理。不匹配、多个候选或包含复杂子块时按普通引用处理。代码示例中的标记不识别。新工程模板不再生成 `## 摘要`，无摘要可删除整块，不补造内容。摘要只是输出角色，不新建稳定对象/第二份正文。Word仅加粗“摘要：”标签，其余使用普通正文段落，不占章节号；不再将整段套用章节字重。连续引用行在同一引用区域内保留可见换行，普通正文换行规则保持。

自由模式仍遵守安全HTML边界。工程模式中mark/span装饰标签去装饰保留文字；其他HTML按源码显示并产生输出提醒，不会偷偷执行。Word始终走Bridge工程预检，超出已有映射明确拒绝，不按任意CSS仿制版面。普通代码围栏保持字面内容；已声明但无效的工程对象仍报错，不能降级成代码绕过校验。Word导入的普通符号必须转义，原生公式/引用由独立结构适配器创建。

编辑器正式保存/独立另存时，将已有受控assets路径的独立Markdown图片段落规范为report-figure-v1，复用原图片序列化/校验、ID、图题与编号。行内/表内图片、代码和HTML不被改成块对象。该行为是用户保存事务，不在A0、只读导出或解析器中隐式改写源文。

## 临时工程工作页

工程模式Word入口直接配置；自由稿只有一个H1或无H1时就地切工程检查，多H1仍选择整篇/专题独立提取。另有显式可选的独立工程预览入口。提取沿原Marked/SourceMap/定义依赖，不替换编译器。允许保留不完整稿进入临时工程预览和检查；重复/缺失脚注、跨专题引用或工程错误阻止编译，不猜改源稿。

同源POST /api/report-workspace需要X-HRS-Project-Action:user-action，create绑定document_id/draft_id/revision/source_sha256及完整当前源稿，来源正式稿或已确认草稿必须一致；引用资源经原快照/原件校验并在复制前后复核。输出为自身工作区的独立工程，report_workspace元数据含hrs-report-workspace-v1、origin_document_id/origin_draft_id及source_sha256；仅自身直接目录允许作为此类工作页，不信任外部工程伪造的该字段。list按显式offset/limit分页（每页最多50项），只返回绑定来源，不能指定任意目录。

临时稿使用原保存/草稿/revision机制，工程模式独立编号；默认不回写来源。sync-plan冻结差异，sync-apply必须携带已审查plan_id/plan_sha256并重查源稿、临时稿和附件，按源UTF-16范围修改并复用report_lock/commit_report_locked与.history备份。来源不一致或存在当前未处理的恢复草稿时拒绝。共享脚注和链接定义消费原Marked/SourceMap定位，其他范围字节不变；同步不改配色/显示模式，不扩展A0或CLI块权限。旧临时稿/未保存来源没有可写回基线时不可同步。返回/恢复期间锁住并发UI和programmatic操作，完成范围及草稿恢复后才放开。输出优先放仍在登记且可访问的来源output，否则使用临时稿output。该入口是显式本机UI操作，不扩展A0或plan/apply权限。

## 自由笔记的专题与留白

可选布尔配置 `render_options.preserve_blank_lines` 控制块间多余空行：缺字段为false以保留旧稿显示，新建自由笔记/导入普通Markdown为true。两块间一个空行使用原段距，两个空行额外留一行，三个额外留两行；高度由共享正文行高单位定义。仅处理顶层块之间的尾部空行，不解释代码、列表、引用、表格和HTML内部空行。占位没有对象ID、编辑身份或编号；工程HTML和Word不应用这一显示选项。源字符、CRLF/LF和BOM不变。

自由笔记以原Marked识别的顶层H1划分专题，直到下一个H1；H1前非空内容是“前言／未分组内容”，没有H1时整篇是一个单元。同名标题按本次源快照的UTF-16范围/顺序区分，不强制写入章节ID。专题聚焦是本次会话视图，打开文稿默认全部，不保存到report.md或meta.json。聚焦只构建所选专题的DOM/数学/图形，目录只列本专题。章节、图表和公式在原编号函数上按该专题重新派生序列，继续服从原显示开关；返回全部恢复全文序列。对象ID、重复判定、引用定位与脚注号码仍基于全文共享索引。跨专题图表/公式引用显示所属专题及目标专题的局部号码，单击按原ID切换到目标。源码全文搜索可切换到目标专题，渲染正文全文查找会显示全部专题。源码界面以同一CodeMirror全文隐藏范围外内容，不裁剪持久正文；原事务/撤销和Agent快照不截断，用户普通编辑不能越过可见范围。聚焦时全局脚注定义隐藏，相关定义由源码下方面板通过原范围事务编辑；跨越隐藏定义的删除拒绝。全部专题显示定义边界，Ctrl单击定义定位真实脚注。普通滚动不自动换专题。

HTML范围分为整篇和勾选专题；整篇导出与当前聚焦无关。分册以每个专题的源码及所需定义/原件生成仅阅读或独立可回编v2 HTML，内部ID保留，编号按新分册派生；顶层脚注定义只收集实际使用者，Marked链接定义沿原词法结果补齐。正文不重排，原工程不写入。跨专题对象/章节引用集中拒绝，不因同时勾选两个分册就把跨文件引用当成已解决；可改导整篇或调整专题范围。所有选中项先预检，再暂存生成，最后统一提交一个HTML或含多个HTML的ZIP；失败不留下部分交付。单册采用安全标题与时间戳，仅真实重名时加序号；多册ZIP内按顺序组织，完整题名保留在正文。单册沿用既有归档容量/安全边界；单批最多500项/512MiB暂存，取消和服务关闭清理自身暂存。

图片仍存assets，预览使用lazy/async和有界尺寸缓存/原滚动锚点；不统一eager或decode。工程保存与HTML归档的资源容量规则分别按原入口执行；不得把归档100项限制当作编辑工程最多100张图。原始图片不降采样写回。

## 笔记表示、脚注及公式扩展

自由笔记的 `==文字==`为行内高亮，单行内闭合；开头的 🔴／🟢／🔵分别选择红／绿／蓝底色，符号本身仍是正文。颜色按钮的显式表示为安全的 `<mark style="background-color:#…">文字</mark>`。代码围栏、行内代码与公式中的符号不激活高亮。工程 HTML 和 Word 保留文字，去装饰；不永久重写原稿。

脚注引用 `[^key]`对应顶层定义 `[^key]: 正文`；key 为1—80个中英文、数字、下划线或短横线。后续四空格／制表符缩进行属于同一定义。重复键只使用第一份并诊断；缺定义保留字面并诊断。显示编号按首次引用顺序派生，同键重复引用共享编号，每处有返回入口。定义内的递归脚注按字面保留，不展开。正文、表题和单元格使用同一定义表，表题显示副本不增加引用次数。它不是新增图表身份对象，也不是自动识别外来 Word 的文献语义。Word输出可选择原生页底脚注（重复引用使用NOTEREF）或文末参考文献；后者标题进入目录、不编号，条目与引用显示[1]，用独立SEQ／REF并保存派生区域来源指纹。输出选项不改写Markdown；未定义、重复定义、嵌套脚注及脚注图片必须明确报错，不能静默删除。

行内与行间公式支持原生 `\boldsymbol{…}`（包括希腊字母／复合表达式），使用本地同版本 MathJax 扩展；原稿和归档保留原 TeX，不将其文本替换成 `\mathbf`。不支持论文任意宏包或在 HRS 运行 TeX 命令。

适用版本：**v0.6.4**。状态：v1 试行契约，由 `report_contract.py` 解析和校验。本文是现行格式的唯一技术规范，按当前主题组织；版本变化见[更新记录](CHANGELOG.md)，历史去向见[历史索引](docs/HISTORY_INDEX.md)。

内容真源是 `report.md` 与所引用的 `assets/`。IR、预览和导出均为派生结果，不另建一份正文。本契约不承诺完整 CommonMark/GFM AST 或任意 Word 无损互转；Word/WPS 与工程专业语义属于独立下游。

## 1. 项目目录和保留原则

```text
项目/
├── report.md                 作者修改的唯一正文源文件
├── assets/                   展示资源及已归档原件
├── diagrams/                 预留原始绘图源位置，本版未使用
└── build/
    └── report.ir.json        由校验工具生成，可删除后重建
```

正式保存才更新工程 Markdown；草稿恢复独立。不要求源工程是单文件，交付 HTML 可嵌入展示内容与源归档。图片不能以 `https://...` 充当已离线资源；资源沿用既有路径、格式和安全校验，不通过预览重排或修改旧稿。

## 2. 标准块、标题、列表与公式

### 正文与标题

ATX `#` 到 `######` 表示 H1–H6。可在标题末尾添加 `## 试验结果 {#sec-result}`，可选关闭 `##` 放在锚点之后。IR 标题保留层级、完整源码和可选 ID，`text` 不含锚点；标题源码不自动写入章号；自由模式由可选布尔值 `render_options.show_heading_numbers` 控制章节号（缺字段为 false），工程模式始终从H2开始按层级派生显示编号。H1不编号；目录、阅读与HTML使用同一派生结果。标题中已输入的数字均为普通标题文字，不自动判定、隐藏或迁移。源码和 IR 不写入派生章号，原工程检查提醒及Word的显式确认契约保持。导出报告目录覆盖H1—H6；H4—H6的显示字号跟随正文基准，语义级别和可选ID不因字号相同而改变。不为旧标题自动加 ID；工具栏显式插入章节引用时，可为无 ID 标题补 ID，与插入引用共用一笔撤销。Setext/嵌套标题的显式锚点不在此子集中。

普通段落、强调、链接和嵌套列表保留原始 Markdown 与源范围，不强制逐段分配 ID，目前没有完整 inline AST。`report-*` 专用围栏必须符合明确 schema，未知工程对象进入诊断，不能猜成普通正文。派生章节号位于标题可编辑文字之外，不属于Markdown正文。普通 `mermaid` 围栏保留完整源码，由本地完整Pele1.10.0渲染；继续使用Mermaid语法，兼容目标12.1，支持`<br/>`节点换行及其内置图种。主题由HRS语义变量提供，固定源码方向，图内`$$...$$`复用MathJax；任意HTML标签、脚本回调与Mermaid主题覆盖不在支持范围。解析失败明确报错且不改源码，每个围栏一张图。预览/HTML/PDF使用同一SVG，导出等待异步渲染完成；普通Mermaid与report-figure均进入图序列并可输出Word。普通围栏的原编辑窗口也可填写图题；首次应用非空题名时，沿同一源范围事务提升为report-figure并建立稳定ID，源图内容及未改动的CRLF保留，取消不写入，一次撤销恢复原围栏；已有对象只更新原ID的图题。解析和只读输出不主动提升。

基本流程图的可视排版复用`%% pos ID X Y`注释，X/Y为节点形状左上角的SVG用户坐标，非负且不超过100000。旧坐标继续读取；拖动时保存全部节点位置，连线/箭头/边标签同步，应用后为一笔原源事务，可撤销。仅改变位置时在方向行后写入位置注释，保留其余源码和CRLF；自动布局移除位置注释。位置不参与ID/编号或IR角色判断，预览与HTML/PDF/Word图形共用。可视编辑范围沿原Flow子集：flowchart/graph五种方向、ASCII节点ID、矩形/圆角/菱形、-->及-.->和可选边标签，最多90节点、100连线。复杂结构不简化、不删除源码，由完整引擎预览并直接编辑源文。外部Mermaid渲染器通常忽略这类注释，不保证HRS手工位置。

普通Markdown文件/文件夹超链接允许相对路径、Windows绝对路径和完整file://URI。浏览器只显示/分派，显式点击通过同源用户操作头调用/api/local-link/open；相对路径按当前已保存工程目录解析，未保存稿不能猜测来源目录。Windows交系统默认程序或资源管理器打开，HRS窗口保留；程序/脚本/快捷方式不直接执行。此入口不读取或导入目标内容、不纳入assets、不更改源文，不属于Agent写入或任意命令接口。HTML保留链接但不携带目标文件，跨目录或跨机器时由目标路径可用性决定；网页、页内锚点和受管图片附件保持各自路径规则。

### 安全 HTML 显示

普通 Markdown 可包含白名单 HTML。行内支持 br/sub/sup/u/mark/kbd/span 及常见强调、代码、链接标签；块级支持 div/p/details/summary、列表、引用、标题和普通 HTML table/thead/tbody/tr/th/td 等。HTML 块内部遵守原 Marked 的 HTML 块边界，不再次解析 Markdown。源码原样保存，不自动生成另一份 HTML 正文。

仅保留 title/lang/dir、安全链接、details 的 open、受限表格跨度等明确属性。删除脚本、style 标签、iframe/object/embed、表单、事件、危险 URL、任意 id/class/data 属性和 SVG/MathML 原始节点；工程公式仍由原 MathJax 路径生成。既有 Markdown 列表显示扩展和代码语言使用受限的内部展示属性，不允许伪造工程对象或控件身份。

内联 style 使用浏览器 CSS 解析后逐项白名单：文字颜色/字号/字重/行高/对齐，背景色，边框/圆角，宽高及上下限，内外间距，display、flex 及行列 gap、表格布局等。position/z-index、URL、表达式、变量、自定义属性及 important 不保留。未知样式忽略，源文不改写；节点数和嵌套深度有界。原始HTML块内部的段落、粗体和标题继承局部文字颜色；显式内联颜色继续生效，不由报告默认段落颜色覆盖。

Markdown 图片与 HTML img 的项目路径由 asset_paths.json 统一定义，Python 和浏览器消费同一规则。接受 assets/a.png、./assets/a.png 及 assets/sub/a.png 等安全子目录；单个目录/文件名最多121个ASCII字母、数字、下划线、连字符或点，首字符必须为字母或数字，最多8级子目录。禁止空目录段、点目录、末尾点、Windows保留名、反斜杠、URL编码及越界路径；文件及其父目录不能是符号链接或重解析点。显示类型仍为 PNG/JPEG/GIF/WebP/SVG。./ 仅在派生依赖和显示路径中归一化，不改写原始正文；正式对象 src 使用规范 assets/ 路径。

HTML img 的属性按 HTML 实体解码、重复属性取浏览器的首项。附件发现进入原 assets、MISSING_ASSET/EXTERNAL_IMAGE、快照与导出校验，不接受网络图或 data URL。代码/注释/转义示例不成为附件。只读阅读包使用其原包内路径规则，不混入工程注册。保存时独立 Markdown 图片仍沿既有规则提升为图片对象；行内图片与 HTML img 保持原来的展示角色。素材整理只处理原有平面资源组，子目录保守保留，不自动清理。

HTML 展示表格/图片不产生工程 ID、序号或引用；正式对象仍使用现行 report-table/report-figure/组图语法。工程表格单元格支持同一安全行内标签，仍是文本/数学单元格，不借 HTML 建立图片对象。含 HTML 的正文不走可能丢标签的可视反序列化，双击使用现有块源码窗口。离线 HTML 继承安全渲染结果；可回编归档保留原始 Markdown 和资源，导入时只在惰性模板读取归档，不执行输入 HTML。

### 列表样式

标准 `-`、`*` 和 `1.` 列表保持原语义。GFM任务项 `- [ ]`／`- [x]` 由同一Marked列表节点识别；编辑区可直接勾选，SourceMap映射到当前快照中的单个状态字符，复用历史、草稿和正式保存。代码和HTML input不产生可写任务。工程HTML、帮助和只读阅读包保留状态且禁用。自由HTML仅对原生任务开放本机阅读状态，存储键绑定文件路径/源SHA/状态字符位置；缺存储可降级，不修改归档JSON或Markdown，回编仍恢复原源码。受限注释 `<!-- hrs:list style=... -->` 可指定 `bullet/decimal/lower-alpha/paren-decimal/paren-lower-alpha`，后续仍使用相应标准 Markdown 列表。样式是显示策略，不把派生字母或括号数字逐项写进正文；IR 的 `list_styles[]` 保留样式及源范围，列表项仍是原始 Markdown。复杂多级编号模板未实现。

### 行内与块级数学

行内 `$...$`、`\(...\)` 和块级 `$$...$$`、`\[...\]` 保留原始 LaTeX、反斜杠和换行。表格单元格也保留文本及这些定界符；MathJax SVG 只用于显示，不写回 Markdown。代码和转义示例不应误识别为数学。

顶层 `\[` 开始、`\]` 结束的公式允许跨行，返回 `delimiter:bracket`；`$$...$$` 返回 `delimiter:dollar`。两种块公式均进入统一公式序列，不依据定界符或ID决定是否显示号。未闭合起始行进入结构诊断；行内数学不编号。

需要稳定引用时，在 `$$` 开始行紧邻前一行添加身份元数据，中间无空行；身份与编号显示分离：

```markdown
<!-- hrs:eq id=eq-energy -->
$$
E=mc^2
$$

由 @eq:eq-energy 可得。
```

所有有效块公式均派生number；`numbered:true`是IR中可参与序列的兼容属性，实际显隐由文档配置决定。低层公式解析器仅返回内容、定界符与身份，不返回插入类型编号策略。IR equation保留原始latex/source、定界符、UTF-16范围及可空id。无ID公式可显示号；显式插入引用时才通过既有事务补ID。关闭编号后已有@eq引用显示“该公式”并仍可定位。孤立元数据、重复ID和未知目标继续诊断；TeX显示成功不保证可转换为OMML。

## 3. 原生表格与增强表格

### GFM 管道表及题注

原生表以管道行和表头分隔行定义，可选题注推荐紧贴最后一行，无空行：

```markdown
| FSR | 结果 |
| ---: | ---: |
| 250 pm | 0.5 |
: 输入光谱 {#tbl-spectrum}
```

旧稿兼容表格与题注之间恰好一个空行；两个及以上空行不能归属同一表。新建或显式修改并保存该表时采用紧贴格式，不批量规范化旧稿。源码折叠/高亮是 UI 元数据，不扩充语法容错。

IR 为 `type:table`、`sourceKind:gfm-pipe`、`data.schema:gfm-pipe-table-v1`，保留行、对齐、可选题注/ID和原始源码。所有GFM表与增强表共用表序列，numbered:true表示参与序列；显示服从文档图表开关。匿名表不强制加ID。显式引用可写`:  {#tbl-id}`身份行，不要求捏造题名。水平对齐由`:---/---:/:---:`决定；合并、精确列宽和垂直对齐需明确升级增强表，不能自动改JSON。

不等长数据行的显示按表头列数补空/忽略额外列，原始 Markdown 保留；显式保存涉及丢失信息时按现有确认处理。单元格富文本仍须从源文安全解析，不能以 HTML 表格 DOM 代替语义。

### 增强表与合并网格

````markdown
```report-table
{
  "schema": "report-table-v1",
  "id": "tbl-data001",
  "caption": "试验结果汇总",
  "rows": [
    [{"text":"联合标题","rowspan":1,"colspan":3}, null, null],
    [{"text":"A","rowspan":1,"colspan":1},
     {"text":"25","rowspan":1,"colspan":1},
     {"text":"101","rowspan":1,"colspan":1}]
  ]
}
```
````

`id` 必填且全篇唯一，`caption` 只保存用户文字，最多 300 字。1–100 行、1–30 列、每行等宽，单格文本最多 30000 字符。合并主格保存正整数 `rowspan/colspan`，覆盖位置为 `null`；拒绝重叠、越界和无归属空位。

可选 `columnWidths` 长度等于逻辑列数，每项为大于 0、不超过 100 的有限数，合计 100，误差容限 0.000001，例如 `[20,50,30]`；省略时等宽，不自动补旧稿。可选 `align` 为逐列 `left/center/right/null`；`verticalAlign` 为整表 `top/middle/bottom`，未提供时保持原排版。网页与离线 HTML 使用相同数据，列宽用 `colgroup` 表示。

`text` 保留真实换行和 TeX。多行纯文本没有 HTML 表格结构或 TSV 列分隔时仍放入一个单元格；Excel HTML 优先于纯文本，显式 `<br>` 与带引号 TSV 格内换行保留。复制表格输出 TSV，不把源码卡片当表格数据。

行列操作先验证逻辑网格：合并区内插入扩大跨度，边界插入新增空格；删除覆盖行列缩小跨度，主格被删但仍有区域时保留文字并迁到剩余左上角。完全删除有内容格须确认，至少保留一行一列。合并仅允许其他被合并格为空，不自动拼接或丢文字；区域粘贴与合并冲突时先拆分。

弹窗编辑、区域粘贴、增删、合并/拆分和一次列宽拖拽均可撤销/重做。应用后整表为文稿一笔修改；取消或未修改应用保留原 Markdown 字节。不保存固定行高。查看 MD/表格仅切换展示，打印固定使用可视表格。

## 4. 单图、流程图、组图与资源

### 带题注的单图与流程图

````markdown
```report-figure
{
  "schema": "report-figure-v1",
  "id": "fig-flow001",
  "caption": "数据处理流程",
  "kind": "mermaid",
  "source": "flowchart LR\n    A[读取数据] --> B[校验数据]"
}
```
````

图片模式使用 `kind:image`、`src:assets/filename.svg`、可选 `alt`。图题最多 300 字，alt 最多 300 字；Mermaid source 必须非空且最多 50000 字符。旧普通 Markdown 图片不强制迁移。图题在下、表题在上；编号不存入题注。

`sourceAsset` 保存可选原件路径，`rendition` 保存预览信息，原件与预览沿用同一 16 位资源 ID 和既有安全规则；PDF 对应 PNG 预览，EMF 对应 PNG/SVG。旧 `vectorSource/rasterFallback` 保持兼容，不自动改写。`rendition.dpi` 为 (0,600] 内有限实际有效值，旧整数兼容；未知 DPI 省略，不默认 300。当前 PDF 插图只渲染第一页，保留完整原件；外部 PDF 文献链接不自动成为插图。

### 简短组图围栏

```markdown
::: {#fig-conditions layout-ncol=3}

![工况 A](assets/a.svg)

![工况 B](assets/b.png)

![工况 C](assets/c.png)

不同工况下的响应对比

:::
```

这是本工具明确校验的 fenced div 子集，借鉴 Quarto 写法，无 Quarto 运行依赖。必须指定唯一 `#fig-ID` 和 `layout-ncol=1/2/3/4`；可选 `layout-nrow=1/2/3`、`subfig-labels=on/off`。2–12 张本地图片，不超过指定行列容量；属性顺序可交换，空行可选。每张说明为纯文本，可转义反斜线/方括号、最多 300 字；最后一行组图题为无首尾空白的单行文字、最多 300 字。未知/重复属性、嵌套 div、多行题注或复杂图片语法报错并保留源码。

IR 为 `type:image-group`、`data.schema:report-image-group-v1`，包含 `id/caption/columns/images[{src,caption}]` 及可选 `rows/showSubfigureLabels`。图片可通过现有尾随元数据保留 `source/fallback/format/dpi/page/width/height/engine`，归入原件与预览字段；Markdown 仍保存简短源块，不写回 IR JSON。具体资源校验复用现有解析器，不把任意属性当成支持字段。

旧组图未设置行数时自动排布，未设置子图字母开关时显示字母。每张图保持宽高比、按列等分、说明底部对齐，最后一行可未填满；关闭字母保留说明和总题注。组图窗口支持文件/剪贴板输入及调序；取消、未修改应用和旧快照保护沿用源文保真机制。

整组与普通图共享图号，`@fig:fig-conditions` 引用整组。字母不写入稳定 ID；子图独立 ID/引用未支持。预览、离线 HTML 与 PDF 使用同一组布局；可回编 HTML 保存完整 Markdown 与必需资源。SVG 继续走安全导入流程，不等于所有绘图软件的 SVG 均已验收。

## 5. 稳定身份、编号、引用与源快照

### ID 与派生编号

稳定 ID 为字符串：增强表 `tbl-`、单图/流程图/组图 `fig-`、章节 `sec-`、块公式 `eq-`，后缀为 1–60 个 ASCII 字母、数字、下划线或连字符。空后缀、错误前缀、超长、空白、非 ASCII 或非字符串值均拒绝。无效对象进入既有结构诊断，不为异常旧稿自动生成 ID 或改写原文。

| 对象 | 稳定 ID | IR `type` | 编号策略 |
| --- | --- | --- | --- |
| ATX H1–H6 | 可选 `sec-...` | `heading` | 不自动章号，`level` 仅描述层级 |
| GFM 管道表 | 可选 `tbl-...` | `table` | 与增强表共用表序列，显隐由文档控制 |
| 增强表 | 必填 `tbl-...` | `table` | 正文顺序，独立表序列 |
| 图片/对象Mermaid | 必填 `fig-...` | `figure` | 与组图共享图序列 |
| 普通Mermaid | 可无 | `mermaid` | 与图片/组图共享图序列 |
| 组图 | 必填 `fig-...` | `image-group` | 整组一个图号 |
| 有身份的 `$$` 块公式 | `eq-...` | `equation` | 与匿名块公式共用公式序列 |
| 普通 `$$` / `\[...\]` | 可无 | `equation` | 同一公式序列，显隐由文档控制 |

编号按有效对象的正文出现顺序派生，无效/重复对象不占号，显示号不写进 caption 或原 Markdown。有效单图、组图、普通/增强表的题注为空时仍显示“图 N／表 N”，不显示“未填写题注”。结构层级、身份、编号策略和输出样式分别管理，不承诺复杂章节分节自动编号。

浏览器唯一对象规则源为 `web/object_catalog.js`，编辑器源码摘要、预览、引用选择及离线目录复用它；Reader 从它和 `report_reader_core.js` 构建。Python 独立提供同一语义 IR，以共享样例交叉验证。已有离线 HTML 内嵌当时 Reader，安装新程序不自动更新；可信旧 HTML 可导入后重新导出。旧浏览器兼容代码不代表目标 Chrome/Edge 实机验收通过。

### 引用上下文与拒绝条件

正文用 `@fig:fig-flow001`、`@tbl:tbl-data001`、`@sec:sec-result`、`@eq:eq-energy` 指向身份。章节引用显示目标标题，改名后更新文字，调序不改变 ID。图表公式显示号按各自最终顺序计算；同一文件内不保留旧可见号。

只扫描有效正文，包括普通链接可见标签、列表与 GFM 表内容；代码围栏、行内代码、链接 URL/title/定义、图片 token、原生 HTML 属性/块、数学和转义示例不参与引用。四种数学定界符内的 `@...` 均不是引用。Python 使用保长上下文扫描，前端使用 Marked token，以同一组正反例校验。

重复 ID、缺失目标和类型不匹配属于结构错误，正式保存拒绝并保留恢复草稿，不能静默分配身份。多来源整合须另定义命名空间与引用映射，不在当前单报告契约内。当前引用是 HTML 内部链接，未生成 Word REF/SEQ 或书签。

### 源快照与坐标

IR 的 `offset_unit:utf16` 表示块、引用、诊断的 `start/end` 是起点包含、终点不包含的 UTF-16 范围；CRLF 两个字符分别计数，非 BMP 字符计两个单元，行号从 1 开始。对象诊断可带 `objectId`，重复对象诊断指向自身源区间。

`source_snapshot.text_utf8_sha256` 是完整输入字符串按 UTF-8 编码的 SHA-256；`utf16_length` 是长度，`newline_mode:preserved`，`bom_preserved` 标记首部 U+FEFF。CLI 从原字节解码，保留 BOM、CRLF/LF 和混合换行，另给出 `file_sha256/file_bytes/source_path/encoding`；BOM 参与摘要与偏移，只在首行结构识别时忽略。HTTP `/api/validate` 是提交文本快照，不能冒充磁盘文件摘要。

坐标仅在摘要相同的快照内有效；修改后重新解析。预览基础块编辑用同一源映射，复杂内容回源编辑，旧快照拒绝写回。读取和 IR 生成不改文件，不能依赖预览文字搜索恢复坐标。

## 6. 工程 IR 输出契约

在 `app/` 目录执行。随包 `docs/IR_EXAMPLE_SOURCE.md` 是**结构演示**，未附带其引用的四个示意附件；可直接使用已有 A0 只读入口读取摘要和结构范围：

```powershell
python agent_readonly.py summary docs/IR_EXAMPLE_SOURCE.md
python agent_readonly.py outline docs/IR_EXAMPLE_SOURCE.md
```

两条命令输出 `hrs-agent-read-v1` 的摘要/结构投影，默认不检查附件存在性；结构读取成功及 `sourceContractValid` 不能证明附件齐全或 Word 编译完成。`docs/IR_EXAMPLE.json` 是同一示例经 `analyze(text)` 派生的完整结构 IR，不是完整附件验收。

实际工程需有 `report.md/assets`，完整校验和 IR 导出如下；替换为真实输入与输出目录：

```powershell
python report_contract.py validate 路径/完整工程/report.md --json
python report_contract.py ir 路径/完整工程/report.md --output 指定的输出目录/report-ir.json
```

这两种操作始终检查附件；未配附件的结构示例返回退出码 1 和四条 `MISSING_ASSET`，不能为演示关闭校验。

### IR 字段与诊断

输出 `schema:engineering-report-ir-v1`、`source_format:engineering-report-v1`、`offset_unit`、`source_snapshot`、`blocks[]`、`objects.ids/entries`、`references[]`、`assets[]`、`list_styles[]`、`diagnostics[]`、`ok` 和 `stats`。块区分 `heading/markdown/table/figure/image-group/equation/mermaid/code/invalid-object`，保留源码和源行号/范围，复杂对象含验证后的 `data`。

`objects.ids` 是 ID→源行号的兼容索引；`objects.entries[]` 提供 `id/kind/line/start/end/numbered/sequence/scope/referencedBy`，表带 `sourceKind`，标题带 `level`。无 ID 对象不进入稳定 ID 索引，仍可通过 `blocks[]` 读取；范围只对同一快照有效。

结构诊断包括 `DUPLICATE_ID/INVALID_OBJECT/UNKNOWN_OBJECT/MISSING_REFERENCE/EXTERNAL_IMAGE/MISSING_ASSET` 等，严重性为 `error/warning`。CLI 不通过返回 1。增强表/图未知根字段保留在派生 `data.extensions`；未知根字段和表单元格附加字段产生 `UNSUPPORTED_OBJECT_FIELDS`，原始 source 保留，不能静默视为支持。扩展容器是 IR 输出，不要求在 Markdown 新增该字段。

### 受控块 plan/apply

app/block_cli.py 在现有 IR 与 A0 精确定位上生成 hrs-block-plan-v1。plan 绑定源 SHA、目标 ID 或快照内索引、UTF-16 范围、替换内容、候选摘要、范围外前后缀摘要及引用资源摘要，并输出可查看的差异；原稿不写。

apply 必须显式给出已检查计划的 SHA-256。它重新读取源文并重新定位、重建候选，检查计划、候选、范围与附件后，通过与编辑器共用的 .hrs-write.lock、.history 备份及原子保存提交 report.md。旧源、计划/候选篡改、越界候选、缺失或变化的附件、锁冲突及文件占用均失败，不用整链重试掩盖问题。CRLF、BOM、中文和非BMP字符参与快照；范围外原始字节保持。替换、前插、后插共用一次提交，不提供批量附件写入。

此命令与只读A0、只导出HTML的浏览器薄入口分别存在；不把任何普通读取或导出隐式升级成写入。Bridge的块命令委托HRS实现。命令示例见app/README.md；写回后旧编辑器revision会失效，其恢复草稿仍保留。

### 完整预检与安装命令

标准安装后的hrs capabilities返回命令/副作用/可选依赖。hrs read ACTION SOURCE委托原A0；hrs plan .../hrs apply ...委托原块提交；hrs html export/recover ...委托原HTML引擎。完整预检使用hrs check PROJECT --render-profile engineering --browser BROWSER，复用页面Marked/脚注及输出策略，并检查附件，返回hrs-output-preflight-v1、完整范围、源摘要和diagnostics；失败非零退出，源不写。未安装Playwright/未提供本机浏览器时明确失败，不安装依赖或退回成“检查通过”。

HTTP /api/validate仅Python源码契约，返回source_contract_valid、preflight.complete=false及保守valid=false/safeToCompile=false。A0相应字段为sourceContractValid。完整页面入口为ReportStudioProgrammatic.check({renderProfile,renderOptions,expectSourceSha256})，仅programmatic=1暴露，返回完整文本检查，互斥/快照约束沿原open/export。页面文本检查本身不扫描磁盘附件，CLI另做附件快照；任何预检都不等于Word装配/Office页面验收。旧客户应迁移结构门槛或调用完整check，不再将旧safeToCompile作为完整检查。

### Agent A0 只读接口

`agent_readonly.py` 提供 `summary/objects/get/references/diagnostics/outline/get-block`，只向 stdout 输出 JSON，不写项目、不开 HTTP RPC、不运行文稿代码。`sourceContractValid` 为结构入场条件；IR 错误或不支持字段使其为 false，不等于工程专业参数或 DOCX 验证。

`outline` 返回快照内临时序号、UTF-16 范围及摘要。`get-block --index N` 必须带 `--expect-sha256`，与当前 `snapshot.text_utf8_sha256` 一致；否则为 `MISSING_SNAPSHOT_PRECONDITION/STALE_SNAPSHOT`。匿名序号不是稳定身份，重排后重新查询。`get --id` 只对唯一 ID 返回 `FOUND`；重复 ID 返回 `AMBIGUOUS_ID`、`found:false`，不能任选第一项。

### 本地浏览器程序化导出入口

仅在显式 `?programmatic=1` 上下文暴露 `ReportStudioProgrammatic`，`schema:hrs-programmatic-v1`。`ready()` 等待初始化，`open(documentId)` 读取本地服务中已存在的文稿，`exportHTML({quality,sourceMode,includePdfOriginals})` 调用原 `buildExport` 并返回 HTML 字符串。参数及画质/归档选项复用现有验证，不另定义生成格式。

`topics()` 返回绑定同一快照的documentId、revision、sourceSha256及topics[{key,title,start,end}]；范围为全文UTF-16。`exportHTML` 可附topicKey和expectSourceSha256生成单册字符串，缺失/过期摘要拒绝；省略topicKey仍导整篇。`exportModules(keys,{quality,expectSourceSha256,...})` 显式在当前工程output提交一册HTML或多册ZIP，强制可回编/free，并返回filename/path/bytes/modules；使用原归档、资源校验及统一暂存事务。调用方先open目标再取得topics；open/export互斥，源/工程/呈现变化拒绝。这些命令不修改原稿；A0和block_cli的全文快照、显式apply约束保持。

`/api/export/modules/begin|stage|finish|cancel` 为同源JSON内部导出事务：begin绑定document_id/draft_id/revision/source_sha256，stage使用原HTML审计及附件摘要，finish再次验证所有分册后统一交付。令牌仅用于当前服务临时会话；不接收输出目录或任意文件路径，不能作为源写入接口。

打开和导出共用互斥状态；当前调用未完成时拒绝第二次程序化操作，调用方按完成顺序执行。失败后释放状态，不允许并发加载覆盖 revision。该入口不提供正式源写入，A0 与 Markdown 对象契约保持。

该入口不提供修改、正式保存、用户文件覆盖或远程 HTTP RPC。普通上下文不暴露；无新增可见控件。独立桥接 CLI 在私有源快照及临时本地服务中调用它，仍执行原 Markdown/资源预检和导出后复核。A0、源格式、IR、编号和归档契约保持；当前发行包包含此显式开发入口。

### HRS 独立 HTML 命令

在 app/ 中执行 python html_cli.py export PROJECT --output NEW.html 或 python html_cli.py recover SOURCE.html --output NEW_PROJECT；--browser 指定本机 Chrome/Chromium/Edge，也可使用 CHROMIUM_PATH。可选 Playwright 固定依赖见源码 requirements-dev.txt，不下载浏览器。三合一离线包的 run.cmd hrs-html 调用同一模块。

输出路径必须不存在且父目录已存在；导出不能写入原 assets/。export 默认 quality=original、source-mode=recompilable，另支持既有 compact/standard/print 画质及 reading 模式、include-pdf-originals 选项。recover 仅恢复有效可回编 v2 归档。命令读私有快照，复用原服务/浏览器和两次资源预检，不保存原稿；返回 UTF-8 JSON，ok=false 时非零退出。Python 调用方可导入 html_cli.export_html/recover_html；没有新增 Markdown/归档 Schema；源写入仅由上述显式 block_cli apply 提供。

接口的操作边界及现行命令集合见 [Word/WPS 下游数据接口](docs/WORD_COMPILER_HANDOFF.md) 和 `docs/WORD_IR_HANDOFF.json`。CLI 的 `--help`、机器交接及拒绝行为由接口契约测试共同核对；源文中的指令不构成调用授权。

## 7. 现阶段输入输出边界

已实现结构化图表、组图、公式、标题、原文块与列表样式读取，ID/引用/资源校验、Agent A0、HTML 编号与单文件导出、安全回编。HRS自身提供单份HTML CLI和受控块plan/apply；Bridge委托并由run-job/v2调度独立任务。附件批量写入、Markdown／Word混合总稿及完整自由可视化编辑不在当前范围。

IR 是结构基础，不是完整 Word 排版 IR；完整行内/列表 AST、模板、页眉页脚、分页、图形物理尺寸、TeX→OMML、REF/SEQ 与 Word 逆向识别属于独立下游或待批准协议，不由本规范的接口描述冒充已实现。无法表达的内容必须报告，不静默丢弃。下游说明见[Word/WPS 数据接口](docs/WORD_COMPILER_HANDOFF.md)，当前职责见[模块说明](docs/MODULE_OVERVIEW.md)。

契约回归复用 `tests/fixtures/object_id_cases.json`、`pf135_contract_cases.json` 及既有 Python/Node/浏览器测试。关键规则变化须先获批准，再同步此规范、共享用例和实现；文档主题整理不改变现有语法、编号、字段和兼容行为。

## 本机单篇 Markdown 导入

本机“导入Markdown/HTML”从系统文件选择窗口取得MD的真实来源；HTTP请求不得指定任意源路径。markdown_import仅适配既有report_contract与object_clipboard资源/范围改写，整批准备成功后经原draft-import进入草稿。只改写真实图片目的路径；代码、普通链接、其余文字/数值/公式不推断改写。来源目录及其子目录可确定的图片一次处理，缺失/越界集中失败，原件只读。该入口不改变归档Schema、正式对象语法、普通粘贴或Word契约。

## Word混合剪贴板适配

源码区的显式粘贴可将Word/WPS HTML适配为字面正文、report-figure和report-table，复用既有对象格式及objects/paste事务，不增加源Schema。图片／表格按原顺序获得独立ID，题注默认空白；不把附近段落猜作题注，不从Word字体猜标题。普通代码围栏内保留字面粘贴；HRS自身富剪贴板优先使用原资源包。

原SourceBlocks/SourceMap分别保留换行视图及Marked行首Tab展开的词法映射，所有范围回到未改写的原始UTF-16文本。不能通过删除Tab、吞掉定位错误或放宽过期范围检查处理粘贴。

内部POST /api/clipboard/document要求当前编辑器同源及X-Report-Studio-Clipboard:user-action，只接受text参数。text为字符串时核对本次Windows Unicode文字（仅等价换行）；text=null用于浏览器未暴露格式时的显式原生探测。格式在一次剪贴板打开期间读取；不接受调用方文件路径，不做后台读取。返回HTML及准备好的资源包，不写源稿／正式附件；无原生富格式时返回available=false供原单图入口继续处理。

CF_HTML的UTF-8字节范围必须有效，HTML不超过2 MB、图片不超过100张／单张12 MiB／总计30 MiB。仅在同一原生快照的RTF逻辑图片数量和HTML图片顺序可对应时使用原图，忽略nonshppict备用副本；否则只使用实际HTML声明且可读取的本地图片。图片和资源仍由原校验器拒绝危险／无效内容；不下载外链图片，不读取UNC地址。嵌套表、表内图片及不能表达的嵌入对象明确拒绝整段。全部资源准备完成后再经原对象接口暂存，并核对源／会话／选区后一次提交；失败不静默保留部分文字。

### 混合粘贴的公式边界（2.0）

本机显式Ctrl+V复用原对象粘贴事务。`/api/clipboard/document`读取同一次Windows快照中的WPS原生DOCX选择、HTML、文字及图片；核对文字与视觉位置后才绑定公式。KSEE3的Equation Native/MTEF3通过有界只读解析转换为LaTeX，不激活OLE服务器。OMML和标准MathML复用现有Word组件的MathAdapter/Pandoc批量转换；`/api/clipboard/math`是同源、user-action保护的内部适配接口，接受formulas数组（format为omml/mathml，source为XML），不接受文件路径。返回tex列表，不写源。与公式分离且可明确定位的外部括号式号不进入HRS；表达式内部数字保留。未知版本/模板、数学缺失、快照或位置不一致均整段拒绝，不以预览图冒充数学。具体支持范围见使用手册。
