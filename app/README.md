# HTML Report Studio

当前产品版本与包修订见 [`release.json`](release.json)，实际验证范围见[当前状态](docs/CURRENT_STATUS.md)。以 Markdown 和 assets 为内容真源，支持自由笔记与工程报告、原生 HTML 导出/回编和显式块 plan/apply。默认蓝色，可选六套配色，界面使用大纲树标志；自由笔记的章节号与图表号可独立开关，默认不显示程序章节号；标题数字保留为文字。普通和增强表使用题注或表头摘要命名，任务编辑仍只改源文状态字符。自由 HTML 的勾选仅保存本机阅读状态，归档源稿不变。帮助保留原蓝色视觉与原 Markdown 生成程序。旧版、原主题候选及用户工程保留，新包解压到新目录。API、界面徽标和构建清单的版本来自 app/release.json（便携目录内为 release.json）。实际验证范围见当前状态。

Mermaid使用本地官方12.2.0完整引擎，普通围栏、正式图形和阅读包共用；节点`<br/>`换行和完整图种不受简易编辑模型限制。HTML输出静态SVG，回编保留原源码；简单图可改节点，复杂图直接改源码。

自由台账支持连续空行留白、目录处H1专题聚焦和勾选专题分册HTML。源码和预览同时聚焦，底层仍是全文；保留全篇编号/引用，整篇导出始终取完整源稿；分册可选仅阅读或可回编，多个以ZIP交付。图片预览按需加载，原件不改写。当前范围见使用手册与源规范。

## 使用入口

普通编辑使用同版本Win64便携包：桌面版双击 `HRS.exe`，自带渲染内核；浏览器版双击 `启动编辑器.vbs`，默认Chrome。两种形式共用同一App，均无需额外安装Python/Node。源码测试包不含Windows runtime，可作为独立桥接的 `HRS_ROOT`。三合一Full另提供离线命令和测试依赖；桌面构建及更新见源码packaging/README.md，当前使用见手册。

- [使用手册](web/help.html) / [手册 Markdown](docs/USER_GUIDE.md)：当前操作与排错。
- [模块说明](web/MODULE_OVERVIEW.html)：当前职责与数据流。
- [源格式规范](source_format_v1.md)：唯一对象、编号、引用、资源及程序接口契约。
- [Word/WPS 下游接口](docs/WORD_COMPILER_HANDOFF.md)：可提供的数据及边界。
- [更新记录](docs/CHANGELOG_READABLE.html) / [技术 CHANGELOG](CHANGELOG.md)：按版本保存演进。

## 独立 Word 导出 beta（支持页底脚注和文末参考文献）

工程模式直接配置Word输出；单个主标题或没有主标题的自由稿先就地切换工程检查，不创建临时稿；多主标题台账仍选择整篇/专题进入临时工程稿。“独立工程预览”可按需建立副本或管理已有临时稿。副本默认不回写，用户查看差异后可显式同步源稿；来源变化时拒绝。工程模式直接配置默认或已准备的封面模板；临时稿产物优先放原工程 output/。完整便携版自带基础 Word 组件，复用自带 Python 和当前页面，无需 Full／Node／额外浏览器。原生公式按需选择 Pandoc；配套 Full 仍可复用。复用 Bridge／WPS，所有模式按工程规则预检。操作与限制见[使用手册](docs/USER_GUIDE.md#导出-wordbeta)。

## 导入普通 Markdown

从“打开 ▾ → 导入 Markdown / HTML…”选择一份MD，本机入口按这份MD所在目录一次读取实际引用的相对图片，支持子目录、中文及带空格路径。成功后形成未保存草稿，首次保存再创建独立HRS工程；原MD和图片不修改。缺失或越出所选MD目录的图片集中提示，取消/失败保留当前稿。这是单篇编辑导入，阅读包仍用于只读多文档浏览。

## 程序化 HTML

在源码根目录使用已有 `requirements-dev.txt` 安装可选 Playwright，并指定本机 Chrome/Chromium/Edge；命令不下载浏览器。普通图形界面不需要这项可选依赖。

```powershell
python app/html_cli.py export D:\Reports\demo --output D:\Reports\demo.html --theme blue --browser "C:\Program Files\Google\Chrome\Application\chrome.exe"
python app/html_cli.py recover D:\Reports\demo.html --output D:\Reports\restored --browser "C:\Program Files\Google\Chrome\Application\chrome.exe"
```

导出输入为包含 `report.md` 及所需 `assets/` 的工程，输出必须是新路径且父目录已存在。默认原生画质、可回编归档；`--source-mode reading` 生成不能恢复源工程的纯阅读版。GUI默认文件名区分“笔记／报告”；CLI显式--output路径不加前缀、不覆盖已有目标。可用--theme临时指定配色，回编保留模式、编号选项和配色；这些配置不写入report.md。回执为 UTF-8 JSON，失败非零退出。程序在私有快照上调用原服务、渲染、预检及归档读取，不正式保存原件、不模拟点击、不调用转换模型。三合一离线包的 `run.cmd hrs-html ...` 调用同一入口。

## 程序化块操作

先通过 A0 取得实际源 SHA-256，再把替换块写入 UTF-8 文件。plan 只生成同目录的计划与候选，stdout 返回计划 SHA-256；apply 的摘要参数绑定已检查的那份计划。

```powershell
python app/block_cli.py plan D:\Reports\demo --id tbl-results --expect-sha256 <源SHA-256> --text-file D:\Reports\replacement.md --output D:\Reports\edit-plan.json
python app/block_cli.py apply D:\Reports\edit-plan.json --expect-plan-sha256 <plan返回的SHA-256>
```

支持 replace、insert-before、insert-after；匿名块用绑定同一快照的 --index。正式写回只接受工程 report.md，自动备份到 .history/。旧快照、被修改的计划/候选、范围不符、附件变化和文件占用均失败；不自动整链重试，不开放附件批量写入。

## 能力与边界

源码区Ctrl+V可接收Word/WPS的文字、图片和普通／合并表格：正文去掉Word排版，图表进入既有对象和附件链，按原顺序一次插入／撤销。Windows从显式剪贴板快照取得图片；不猜题注或标题，不自动下载外链图片，嵌套表／表内图等明确提示，详见使用手册。

CodeMirror Markdown 编辑、GFM/增强表、图片/组图/流程图、公式、稳定引用、快照定位、revision 冲突、保存/草稿、素材回收、HTML 与安全回编沿用原实现。安全 HTML 是显示扩展；普通 HTML 图表不自动取得工程 ID 或编号。HTML 支持范围及源码编辑方式见源规范。

A0 七种查询仍只读。HRS 的 app/block_cli.py 提供显式 plan/apply，Bridge 委托同一实现；apply 重新定位并复核源、候选、资源和范围，复用编辑器备份及原子提交。未显式执行 apply 不写原工程。Word、模板和 OMML 属于独立下游，专业参数含义不由编辑器解释。唯一主标题居中仍是待考虑项。

自有代码采用GPL-3.0-or-later，署名yyyyy-9；第三方许可与样本权利分别保留，见[许可范围](LICENSING.md)。

## 开发接续

[当前状态](docs/CURRENT_STATUS.md)、[项目目标](docs/PROJECT_GOALS.md)、[短期计划](docs/SHORT_TERM_PLAN.md)、[长期路线](docs/LONG_TERM_ROADMAP.md)分别维护事实、方向和批准条件。[文档维护规则](docs/DOC_MAINTENANCE.md)管理职责与生成，帮助 HTML 仍由现有 Markdown 构建。源码根 AGENTS/AGENT_TASK 为规则与 Issue，tests/tools 提供实际检查和发布工具；普通便携包不附测试。

发行文件由包内清单及摘要核对，下载见[发行记录](docs/HISTORY_INDEX.md)。独立解压包可脱离Git阅读。

标准Python/conda基础安装分发名为hrstudio，通过hrs命令复用同一服务，模块名html_report_studio保持；用户数据默认在安装环境外，可用hrs info/hrs license只读查看。基础包不含独立Word编译器或解释器，继续使用明确选择的原配套组件。源码根packaging/README.md说明本地安装/升级/卸载；PyPI尚未上传，conda-forge公开安装须等配方审核及频道构建完成。

## 安装命令

hrs capabilities显示命令能力；hrs read summary PROJECT只读，hrs check PROJECT --render-profile engineering --browser BROWSER完成文本与附件预检。check与HTML CLI需可选Playwright/本机浏览器；GUI仍无需它们。hrs plan/hrs apply和hrs html分别委托原提交/HTML引擎，参数见各自--help。源码契约通过不等于完整输出或办公软件页面通过，详细范围见源规范和当前状态。
