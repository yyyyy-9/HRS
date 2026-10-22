# 维护事项

开发约束见AGENTS.md，测试入口见README_TESTS.txt，功能计划见app/docs/SHORT_TERM_PLAN.md。

## PASTE-01：Word混合内容粘贴（用户授权开发）

目标：一次Ctrl+V按原顺序接收文字、图片和表格；正文只保留文字，图表复用现有对象、资源、草稿和提交事务。已复现行首Tab经Marked展开而原SourceMap未映射，引发“Markdown块无法可靠定位”。先修共用范围映射，再增加受限剪贴板适配；原Markdown/HRS富剪贴板和代码块字面粘贴保持。资源不能完整取得或处理期间文稿变化时整段拒绝，不静默丢图。

已实现并完成本地专项：原Tab/CRLF/emoji定位反例；真实浏览器Ctrl+V混合段落、多图、合并表格、草稿暂存及首次保存、HTML归档恢复、单步撤销/重做；源变化／缺图失败原稿保留、无外部资源请求及旧HRS对象粘贴。实际本机WPS复制两图一表／正文及普通代码块字面粘贴通过，RTF原PNG字节相同。Microsoft Word和旧浏览器本轮未实测。开发基线v1.1.3，独立分支codex/word-mixed-paste，本地1.1.4 R1候选；不自动替换GitHub/Conda提交。新增专项已纳入objects组，Source/Portable同核心和最终包专项单列验证。

## 预览图片复用

预览提交时复用身份和资源未变化的图片节点，减少输入后的重复解码和绘制。资源实际变化时仍应更新；验证尺寸、懒加载、引用定位与文稿切换保持正确。

## 发行一致性

浏览器和标准Python分发使用同一app核心，身份来自app/release.json。模板工具的共用WPS源码位于template-tool，Bridge源码位于components。按改动选择测试，核对生成帮助、源码及发行清单。

### DIST-02：Conda 分发身份

安装分发名使用hrstudio，启动命令仍为hrs，Python模块保持html_report_studio。1.1.2公开版本与Python/Conda元数据一致。v1配方由tools/build_conda_recipe.py读取原身份和pyproject生成，本地source.path与提交用URL/SHA只改变来源。旧meta.yaml及独立构建脚本由同一v1脚本替代。验收覆盖配方生成、无效摘要拒绝、实际wheel/sdist/Conda安装、CLI/资源/版本及同核清单；公开频道状态须以实际PR/发布结果为准。

### DIST-03：Windows产物清单编码

Windows的cp1252控制台列出中文资源文件名时会失败，构建和包内测试通过后仍会中断CI。源规范资源统一为source_format_v1.md，release_info.SOURCE_SPEC供服务和文档检查共用；旧中文HTTP入口映射到同一文件。所有格式使用同一App，不保留第二份规范。回归覆盖cp1252路径输出、真实文档HTTP及旧地址兼容，并实际重跑发行与Conda CI；1.1.2标签保持，修复使用新版本1.1.3。
