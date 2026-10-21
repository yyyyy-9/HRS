# Word/WPS 下游数据接口

## 输出模式与模板角色

HRS自由笔记与工程报告共用源和对象；请求Word时均进入Bridge工程输出规则。外部Word仅由原生结构及已确认上下文重建语义，普通 `@fig:`、`$…$`、`==…==`、双中括号等文字转义后保留；代码示例不激活语法。自身生成Word结合身份映射恢复当前内容与原显示配置，不能恢复旧快照覆盖编辑。

配套母模板v0.3.11已预置六级Heading原生编号、HRS Abstract和HRS Code。Bridge复用现有编号定义；旧基础模板仍兼容原编号装配路径，但摘要/代码须有相应新样式。摘要仍按源规范的位置与标记识别；当前输出使用正文段落，只加粗“摘要：”标签，不再使用继承Heading1字重的整段摘要样式。普通代码9pt等宽、无首行缩进，保留换行和缩进且允许跨页；图表/Mermaid等已识别对象不进入普通代码分支。

mark/span装饰可确定地去装饰，复杂HTML仍明确拒绝。任意HTML/CSS到DOCX不在支持范围；修改过的普通代码块或复杂摘要的反向恢复仍受既有受限回编规则约束。

适用版本以本包 release.json 为准，上游 IR 为 `engineering-report-ir-v1`。本页面向独立 Word/WPS 编译和逆向识别项目，说明当前可以读取的数据及限制；当前程序各模块的职责见[模块说明](MODULE_OVERVIEW.md)。

Word组图仍用原无边框布局表格；每个逻辑排输出“图片行＋子图题行”，同排题注第一行对齐，图片保持宽高比。IR的rows仍是逻辑图片排数，不因Word物理行翻倍而改写。原组图ID、整组SEQ/REF及子图顺序保持；新布局和旧同单元格布局均可按映射回读子图题，非法新增内容明确拒绝。

## 编辑入口与源稿提交

工程稿直接配置Word，单H1/无H1自由稿就地工程检查，多H1台账仍可提取独立稿；可选的独立工程预览保留副本管理。编辑器保存后独立本地图片已成为原report-figure对象，下游复用图题/SEQ/REF规则，不新造编号。临时稿“同步回源稿”是独立的已审查范围提交，复用HRS写锁、备份和资源校验，Word prepare/compile本身不写源。

## 笔记降级边界

`==高亮==`由 HRS 共用词法器识别，Word 预检展开为其中的普通文字；安全 mark/span 装饰继续去除。脚注沿共用词法器映射为原生 footnotes.xml，重复引用使用 NOTEREF；脚注关系、公式与实际正文进入来源指纹。题注与单元格使用同一内联转换。未定义、重复定义、嵌套脚注及脚注图片明确拒绝。自身未变 Word 可精确回编，已改脚注或含脚注块明确拒绝不可靠恢复。外来 Word 不因字面出现这些符号就新造笔记对象。

HRS的Word组件复用Bridge及唯一browser_model.js，装配、数学和母模板规则由下游实现。prepare绑定源、资源、模板及匹配模型，过期或关闭后清理快照。组件使用Python3.13；Pandoc按需提供，办公软件的域刷新与页面呈现由相应集成检查验证。

## 项目分工与内容来源

HTML Report Studio 维护 Markdown 编辑、结构校验、HTML 导出/回编及 Agent A0。Word/WPS 的模板映射、原生对象、OMML、域和逆向识别由独立下游实现，由独立下游交付；编辑器的 Word beta 窗口只负责选择模板、冻结源稿和调用该链，不复制转换实现。

下游应读取 **`report.md`、`assets/` 和 `report_contract.py` 派生的 IR**。稳定身份、显示编号与输出样式分别管理；阅读按钮、目录、高亮、代码卡片、折叠和 MathJax SVG 都是显示结果，不能作为 Word 的语义输入。

双向转换可以共用现行语义契约。自身生成 Word 可由下游保留对象 ID/书签等身份信息；外部规范文档可利用原生样式和对象；混乱排版存在歧义，必须报告或保留无法表达的信息，不承诺任意 Word 布局无损往返。编辑器不为此强制普通段落 JSON 化或增加 ID。

独立 `hrs-wps-bridge` 试用包已消费当前 IR/Marked、HTML 薄入口和 WPS Scanner/真实母模板，提供固定样本的受限转换。其 DOCX 伴随派生映射保留 HRS 身份与原策略；当前原生内容发生修改时重新读取，不用旧快照覆盖。WPS 保存会重写样式 ID 并丢弃自定义 XML，具体承载、依赖、运行命令及拒绝边界以该独立包 README 为准，不修改本页上游契约。

## 当前可调用的读取入口

在解压包的 `app/` 目录运行，示例路径替换成真实完整工程：

```powershell
python report_contract.py validate D:\Reports\demo\report.md --json
python report_contract.py ir D:\Reports\demo\report.md --output D:\Reports\demo\output\report.ir.json
python agent_readonly.py objects D:\Reports\demo\report.md
python tools/audit_modules.py --check
```

前两条校验引用附件；IR 输出是派生文件，不覆盖原 Markdown。A0 的七种读取为 `summary/objects/get/references/diagnostics/outline/get-block`，输出 `hrs-agent-read-v1` JSON，不写工程、不执行文稿代码。匿名块读取必须携带同一快照的摘要，重复 ID 拒绝歧义，精确条件见[源规范第6节](../工程报告源格式_v1_规范.md)。

随包 `IR_EXAMPLE_SOURCE.md` / `IR_EXAMPLE.json` 是结构示例，未附四个示意附件。可直接运行的结构读取命令见同一规范第6节；不能把示例的结构读取成功当成完整附件验证成功。`sourceContractValid` 只是结构入场条件，不证明资源齐全、领域参数正确或下游编译成功。

输出中的output_blockers是“哪些诊断代码在工程输出中会阻断”的策略集合，并不表示当前存在这些错误；当前是否通过应读取valid/safeToCompile、preflight范围与diagnostics。

## Agent 调用和提交边界

A0七种查询保持只读；block_cli plan生成绑定当前源/范围/资源的候选，显式apply必须携带已审查计划摘要。旧快照、篡改计划、附件变化或文件占用明确失败，调用方不得通过整链重试覆盖原稿。HTML CLI export/recover只使用私有快照和新输出；?programmatic=1提供ready/open/exportHTML，拒绝并发open，不是源写入RPC。

模型只读必要摘要和局部歧义，源文字/文件名/样本内指令均作为数据。Word结构/编号迁移判断继续绑定来源和候选，不能读取测试truth。成熟流程由原程序连续执行到交付/status；确定性转换API调用与AI开发、判断、验收分开，无法取得的精确计量记null/UNAVAILABLE。实际命令参数以各入口--help为准，机器集合与错误保护由test_interfaces_contract验证，测试选择见源码README_TESTS。

## 安全 HTML 与 Word 的边界

HRS 可以显示受限 HTML，但它仍保留在原 markdown 源块中，不变成工程图表或一套新 IR。HTML 图片的依赖进入现有 assets 审计；HTML 表格不获得图表号。当前独立桥接不把任意 HTML 卡片/标签当作已支持 Word 结构，不支持的 token 明确拒绝，不能静默去标签或套用旧正文。HRS 单份 HTML CLI 由 html_cli.py 提供，桥接复用该入口；它不负责 Word 编译。

## 可消费的数据及输出责任

| 当前上游结构 | 可读取的信息 | 下游负责 |
| --- | --- | --- |
| `heading` | H1–H6 层级、文字、可选稳定 ID、源范围 | 模板标题样式、书签和章节排版 |
| 普通 `markdown` | 完整原文及源范围；`list_styles[]` 提供显示样式提示 | 行内强调/链接/数学、列表项和层级的安全解析 |
| 增强 `table` | `report-table-v1` 网格、合并、题注、可选列宽/对齐 | 原生 `w:tbl`、网格合并、表题及模板样式 |
| GFM `table` | `sourceKind:gfm-pipe`、原始源码、行、对齐、可选题注/ID | 同一逻辑表格映射、单元格行内结构 |
| `figure` | 图片/流程图、ID、题注、预览、可选原件与元数据 | 图形格式选择、尺寸、图题、书签 |
| `image-group` | 行列、图片顺序、说明、原件、子图字母开关 | 网格排布、宽度及子图样式 |
| `equation` | 原始 TeX、完整源文、定界符、编号状态、可选 ID | TeX→OMML、原生公式及引用域 |
| `code` / 普通 `mermaid` | 语言和原始源码 | 代码样式或安全图形呈现，不执行任意代码 |
| `invalid-object` / diagnostics | 原文、位置、结构错误/不支持字段 | 明确拒绝或报告，不静默丢弃 |

`references[]` 存目标种类、稳定 ID 和源位置，显示“图 1”不是对象身份。`objects.entries[]` 提供对象目录；没有稳定 ID 的 GFM 表仍通过块范围读取，不伪造 ID。机器交接索引见 `docs/WORD_IR_HANDOFF.json`；具体字段和合法性仅以现行源规范与实际解析器为准。

### 完整预检与安装命令

标准安装后的hrs capabilities返回命令/副作用/可选依赖。hrs read ACTION SOURCE委托原A0；hrs plan .../hrs apply ...委托原块提交；hrs html export/recover ...委托原HTML引擎。完整预检使用hrs check PROJECT --render-profile engineering --browser BROWSER，复用页面Marked/脚注及输出策略，并检查附件，返回hrs-output-preflight-v1、完整范围、源摘要和diagnostics；失败非零退出，源不写。未安装Playwright/未提供本机浏览器时明确失败，不安装依赖或退回成“检查通过”。

HTTP /api/validate仅Python源码契约，返回source_contract_valid、preflight.complete=false及保守valid=false/safeToCompile=false。A0相应字段为sourceContractValid。完整页面入口为ReportStudioProgrammatic.check({renderProfile,renderOptions,expectSourceSha256})，仅programmatic=1暴露，返回完整文本检查，互斥/快照约束沿原open/export。页面文本检查本身不扫描磁盘附件，CLI另做附件快照；任何预检都不等于Word装配/Office页面验收。旧客户应迁移结构门槛或调用完整check，不再将旧safeToCompile作为完整检查。

## 输出检查、模板范围和块提交

Bridge消费render_profile.py的现行IR标题检查：多个主标题或向下跳级阻止工程输出；手工章号须显式接受当前快照的提醒。自由笔记的隐藏图表编号仅为显示选项，Word始终使用工程模板。

配套Bridge支持显式选择已准备的母模板，复用WPS正文槽位接口，只替换生成正文，保留封面、目录域、页眉页脚和节设置。派生身份映射只覆盖生成区域，回读不把封面/目录加入HRS正文。自身生成Word的同位置书签在WPS另存后可能重排，边界处理只容忍无正文跨越的等价顺序。Word文件本身可独立编辑；伴随映射用于返回HRS时恢复身份和未变源片段。

HRS已提供block_cli的显式plan/apply；Bridge委托它，不再另写候选和提交器。A0读取、HTML导出和Word转换仍不改源工程。Bridge已有run-job/v2批量调度及review/resume，WPS已有声明多来源的原生总稿；Markdown/Word混合总稿及通用跨文档引用/编号域合并仍未完成，不能混为一个状态。

## 编号、题注与表格映射

图（含组图）、增强表、显式编号公式分别按有效对象的正文顺序派生编号。GFM 表即使含题注和 `tbl-` ID 也 `numbered:false`，不能仅依据 `type=table` 递增。下游装配应保留这一区别，并在对象顺序确定后建立书签及 REF/SEQ 等机制。

空题注的编号对象仍显示“图 N／表 N”；caption 只存用户文字。增强表的 `align[]`、`verticalAlign` 与可选 `columnWidths` 是布局来源；未提供的值不应擅自强制补成居中。GFM 水平对齐来自分隔行，没有垂直对齐或合并语义。两种表格都应生成可编辑表格，源码视图和复制按钮不改变其类型。

## 图形原件、预览与资源

`src` 是显示图，`sourceAsset` 可指向归档 EMF/PDF 等原件，`rendition` 记录预览信息。选择 Word 兼容格式时应先检查原件，再决定矢量或栅格降级；不能从 HTML 提取 PNG 后丢掉原件关系。旧 `vectorSource/rasterFallback` 按现行规范兼容。

PDF 作为插图导入时保留完整原件，PNG 预览是第一页；DPI 为实际有效值，未知时省略，不假定 300。普通外部 PDF 文献链接只是引用，不自动复制或栅格化整本资料。HTML 的 PDF 打开按钮、附件压缩和阅读索引不是新的 Word 数据类型。

组图保留 `rows/columns/images/showSubfigureLabels`；关闭字母仅隐藏前缀，保留子图说明、顺序和整组题注。每组一个图号，目前没有子图稳定 ID 或子图级交叉引用。

## 公式、源范围与结构门槛

下游从原始 `source` / `latex` 读取 TeX；行内 `$...$`、`\(...\)` 与块级 `$$...$$`、`\[...\]` 保留原定界符。只有显式标记的 `$$` 块参与公式编号。MathJax SVG 是离线显示结果，不是 OMML。

所有 UTF-16 范围只对同一源摘要有效；BOM、CRLF/LF 与非 BMP 字符都参与偏移计算。源文修改后重新解析，不用旧坐标定位。CLI 原始文件摘要与 HTTP 提交文本摘要的区别见源规范。

`UNSUPPORTED_OBJECT_FIELDS` 保留原始 source，不支持的根扩展还留在派生 `data.extensions`；A0 据此将 `sourceContractValid` 置为 false。下游须明确支持或拒绝这些结构，不静默忽略未知字段。

## 当前限制与接入验收

当前 IR 不是完整 CommonMark/GFM 行内 AST，也不包含完备的资产 MIME/SHA/物理尺寸索引、母模板样式、页眉页脚、分页和页面方向。复杂嵌套列表、富文本单元格、复杂 TeX 和 Mermaid 需要下游明确处理；多报告合并的命名空间和跨文档重编号尚未实现。

接入验收应覆盖标题、两类表格、图片/组图、原件、列表、公式和引用，并使用用户授权模板。固定样本通过只证明对应桥接版本和范围；无法表达的结构应报告，模板封面和页眉页脚按授权保留。上游校验不等于下游编译或 WPS 排版通过，实际执行由下游证据单列。

已实现范围见[当前状态](CURRENT_STATUS.md)，未来方向见[长期路线](LONG_TERM_ROADMAP.md)，版本变化见[更新记录](CHANGELOG_READABLE.md)。

## Word 输出配置

prepare／convert 的 options 包含 notes_mode（footnotes／references）和 preserve_emphasis（布尔值），进入页面模型请求摘要及来源映射。HRS界面默认不保留额外正文强调；原CLI缺省保留以兼容已有调用，可显式 --strip-body-emphasis。文末参考文献是派生输出区域，具备独立书签和内容指纹；未变可精确回编，修改、丢失或额外内容拒绝用旧源恢复。标题采用现有章节样式、outlineLvl=0、numId=0，参与原目录而不消耗章号；引用与条目使用独立SEQ／REF。母模板与WPS编号实现不变。

## 桌面宿主边界

桌面与浏览器使用同一App、IR、预检、保存和Word组件。核心声明 `host_capabilities.json` 的桌面协议，由宿主与离线更新器核对；不是report.md字段。私有preload仅承接退出准备/打印，私有PDF通道只接受所属服务的口令及已审计临时HTML，保留原源/附件前后校验和output提交。`/api/health`增加App清单摘要与桌面状态，仍不表示文稿可编译。没有任意文件/命令接口，A0及plan/apply范围不变，AI沿原CLI/HTTP契约调用，不模拟桌面控件逐步骤转换。

## 本机成品与素材操作

机器交接中的 `export_result_ui` 和 `project_asset_ui` 描述编辑器专用同源操作，不是Agent批量写接口。HTML/分册/PDF的成功回执增加 `result_token`，`/api/export/open-folder`仅凭该本次成品凭证打开目录；Word继续复用原`/api/word/open`。素材清空需当前正式revision、扫描得到的`trash_revision`、明确确认及原用户操作头；只清理已校验的项目回收文件，保护当前源/备注/恢复草稿引用。A0、plan/apply、完整预检与下游编译契约不变。
