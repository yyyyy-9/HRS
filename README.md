# HRS · HTML Report Studio

Local Markdown report editor with offline HTML, structured figures/tables, equations and template-based Word export. Includes a standalone DOCX template style tool.

HRS 是本地运行的 Markdown 文档工作台，面向自由笔记和工程报告。文稿与图片保存在你自己的目录；编辑、阅读、HTML 导出和恢复共用一套结构规则。项目自有代码、文档与合成示例采用 GPL-3.0-or-later，署名 yyyyy-9。

![HRS 编辑界面](app/docs/guide-assets/editor-highlighting.png)

## 下载与启动

Windows 用户从 [Releases](https://github.com/yyyyy-9/HRS/releases) 下载浏览器便携包，完整解压后双击`启动编辑器.vbs`。自带Python和基础Word组件，使用本机浏览器。当前发行提供浏览器形式，桌面宿主源码也包含在仓库中。

已有 Python 3.12+ 环境时，从源码安装：

```powershell
git clone https://github.com/yyyyy-9/HRS.git
cd HRS
python -m pip install .
hrs
```

也可从Release下载wheel后本地安装。当前没有向PyPI或conda-forge上传，不把同名远端包当作本项目。标准包不含Python、浏览器或可选Word组件；资源与用户数据分开，服务只监听127.0.0.1。

## 可以做什么

- 自由笔记与工程报告：章节/图表编号、目录、引用、脚注、表格、图片、完整Mermaid、LaTeX公式与内置全文搜索。
- Markdown和相对图片导入、对象复制、草稿恢复、专题聚焦、可回编HTML与分册阅读。
- 明确检查后导出Word；复用对应Bridge/WPS组件和准备好的封面模板，保留原生公式/脚注/题注及引用。原生公式需按提示选择Pandoc。
- 只读接口、完整预检和快照绑定的plan/apply。程序没有模型API客户端，不执行文稿中的任意代码。

详细操作见[使用手册](app/docs/USER_GUIDE.md)、[当前能力与限制](app/docs/CURRENT_STATUS.md)、[源格式](app/工程报告源格式_v1_规范.md)和[下游接口](app/docs/WORD_COMPILER_HANDOFF.md)。

## 模板样式工具

[template-tool](template-tool/README.md)可以把格式母模板的样式设置到带封面、目录和页眉的DOCX中，生成新模板供HRS选择。既有Windows EXE和同源Python代码一起提供，工具自带的母模板只含通用占位文字，不含用户报告。

## 开发与测试

测试选择统一在`tools/test_catalog.py`，按改动选择功能，夹具使用项目合成数据。

```powershell
python tools/run_checks.py --contracts-only --evidence ../hrs-checks
python -m pip install -r template-tool/requirements.txt
python -m unittest discover -s template-tool/tests -p "test_template_*.py" -v
```

HRS契约/Node/生成门禁需要Node；浏览器测试另外需要`requirements-dev.txt`和显式浏览器路径，不自动下载浏览器。见[测试入口](README_TESTS.txt)与[贡献约定](CONTRIBUTING.md)。可选Word组件源码见[components](components/README.md)，固定运行库放Release，源码仓库不包含解释器或浏览器二进制。

## 验证边界

首验Windows11；旧Chrome112/Edge92、Win10人工系统窗口/IME、打印和Office页面仍按实际结果单列。输入时图片节点重建可能在旧浏览器上闪烁，列为后续显示优化；章节/资源/复杂回编等边界见当前状态。不宣称任意Word或HTML完全无损双向转换。

## 许可

见根[LICENSE](LICENSE)、[版权声明](COPYRIGHT)、[许可范围](app/LICENSING.md)与[第三方清单](app/RIGHTS.json)。依赖保留各自许可；使用HRS处理的用户文稿和图片仍由其权利人决定授权。问题可通过[Issues](https://github.com/yyyyy-9/HRS/issues)提交，请使用可公开的最小示例。
