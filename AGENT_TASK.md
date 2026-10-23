# 维护事项

## NUMBERING-02 / PASTE-MATH-01：统一编号模型与公式混合粘贴（2.0.0 R1 本机功能验收完成）

用户已批准替换早期按插入类型选择编号的模型。基线v1.1.4；开发分支codex/hrs-unified-numbering-v2，目标2.0.0 R1。块公式、Markdown/增强表格、普通/对象Mermaid统一进入公共对象编号；工程章节/图表强制编号，自由模式按文档开关，公式两模式均由文档开关。行内数学不编号，稳定ID与数字显示分离。移除旧入口/互斥编号分支；输入旧语法仍可读取，不隐式改写原稿。

公式粘贴从本机WPS实际剪贴板验证结构载体，优先MathML/OMML/明确LaTeX；外部式号与数学内容分离，不能删除表达式中的数字。沿原粘贴事务、资源/快照/撤销机制，拒绝无法完整转换的嵌入公式，不以图片冒充可编辑数学。Word出口补原生公式SEQ/REF及关闭编号时的定位引用。独立WPS三表和旧发行不改。

验收复用统一测试入口，增加/修改受影响Python、Node及真实浏览器反例，包含编号开关、原Markdown输入、代码字面保护、引用、保存/归档/恢复及Word。实机WPS与剪贴板单列，未知目标机NOT_RUN。详细执行放外层reports，精确token/API数不可得记null，转换程序不新增模型API。

开发约束见AGENTS.md，测试入口见README_TESTS.txt，功能计划见app/docs/SHORT_TERM_PLAN.md。

当前实现已完成：文档级公式开关、全部原生/对象图表序列、匿名对象显式补身份引用、阅读/归档、KSEE3与OMML/MathML粘贴、Word原生公式SEQ/REF及隐藏编号时定位。配套Bridge0.3.0，旧Word组件须同步更新。Word编译的临时图形ID避让原稿已有ID；源文不写入派生编号或临时身份。

验收入口仍为原catalog；numbering选择普通专项，report_word显式选择原生依赖。实际WPS复制及编辑/域刷新/保存重开、WPS导出页面检查已执行。原完整目录保留Windows net::ERR_NO_BUFFER_SPACE造成的启动失败，受影响模块单独13项通过；不将原full票据改成PASS。最终包与标准安装的证据在外层，不在源码中夹带运行结果。MathType MTEF5/自定义字体或未知模板明确拒绝；Microsoft Word原生复制及旧目标机本轮NOT_RUN。四份目标/状态文档已检查，长期边界和既有短期事项仍适用；帮助与技术规范已同步，GPL许可保持。

## PASTE-01：Word混合内容粘贴（已验收，1.1.4发布）

目标：一次Ctrl+V按原顺序接收文字、图片和表格；正文只保留文字，图表复用现有对象、资源、草稿和提交事务。已复现行首Tab经Marked展开而原SourceMap未映射，引发“Markdown块无法可靠定位”。先修共用范围映射，再增加受限剪贴板适配；原Markdown/HRS富剪贴板和代码块字面粘贴保持。资源不能完整取得或处理期间文稿变化时整段拒绝，不静默丢图。

已实现并完成本地专项：原Tab/CRLF/emoji定位反例；真实浏览器Ctrl+V混合段落、多图、合并表格、草稿暂存及首次保存、HTML归档恢复、单步撤销/重做；源变化／缺图失败原稿保留、无外部资源请求及旧HRS对象粘贴。实际本机WPS复制两图一表／正文及普通代码块字面粘贴通过，RTF原PNG字节相同。Microsoft Word和旧浏览器本轮未实测。开发基线v1.1.3，用户确认当前范围足够并授权同步发布为1.1.4 R1，不扩展复杂结构推断。新增专项已纳入objects组，Source/Portable同核心和最终包专项单列验证；标准Python与Conda复用相同核心，频道可用性以公开PR和频道结果为准。

## 预览图片复用

预览提交时复用身份和资源未变化的图片节点，减少输入后的重复解码和绘制。资源实际变化时仍应更新；验证尺寸、懒加载、引用定位与文稿切换保持正确。

## 发行一致性

浏览器和标准Python分发使用同一app核心，身份来自app/release.json。模板工具的共用WPS源码位于template-tool，Bridge源码位于components。按改动选择测试，核对生成帮助、源码及发行清单。

### DIST-02：Conda 分发身份

安装分发名使用hrstudio，启动命令仍为hrs，Python模块保持html_report_studio。公开版本与Python/Conda元数据一致。v1配方由tools/build_conda_recipe.py读取原身份和pyproject生成，本地source.path与提交用URL/SHA只改变来源。旧meta.yaml及独立构建脚本由同一v1脚本替代。导入测试覆盖最低及最新Python；验收覆盖配方生成、无效摘要拒绝、实际wheel/sdist/Conda安装、CLI/资源/版本及同核清单；公开频道状态须以实际PR/发布结果为准。

### DIST-03：Windows产物清单编码

Windows的cp1252控制台列出中文资源文件名时会失败，构建和包内测试通过后仍会中断CI。源规范资源统一为source_format_v1.md，release_info.SOURCE_SPEC供服务和文档检查共用；旧中文HTTP入口映射到同一文件。所有格式使用同一App，不保留第二份规范。回归覆盖cp1252路径输出、真实文档HTTP及旧地址兼容，并实际重跑发行与Conda CI；1.1.2标签保持，修复使用新版本1.1.3。
