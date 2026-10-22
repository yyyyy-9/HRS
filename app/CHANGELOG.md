# HRS 发行说明

## v1.1.4

- PASTE-01：源码区支持Word/WPS混合粘贴，正文保留字面内容，图片／合并表格复用原对象、草稿附件、一次提交和撤销；HRS富剪贴板优先，代码围栏保持字面粘贴。失败和过期范围明确拒绝，不保留部分文字。
- 修复Marked展开行首Tab后SourceMap无法定位的根因，保留原Tab／CRLF／UTF-16范围；普通文稿词法和渲染入口不换解析器。
- 浏览器未暴露Word富格式时读取显式本机剪贴板快照，避免整段截图粘贴；可对应时保留RTF原图片，拒绝外链下载及不支持的嵌入结构。测试和边界见PASTE-01。

## v1.1.3

- 源格式规范改为source_format_v1.md，解决Windows产物检查使用cp1252输出时的文件名编码错误；内容保持，旧文档HTTP地址继续指向同一规范。
- 统一服务与维护工具中的规范资源定义，补充路径编码和实际HTTP兼容检查；编辑、渲染和Word规则保持。

## v1.1.2

- Python与Conda安装分发统一为hrstudio，命令hrs和模块html_report_studio保持。已有旧分发应先卸载再安装，工程与环境外用户数据保留。
- 公开tag、Python与Conda元数据统一为1.1.2；版本仍由release.json派生。
- 以同一生成器维护v1 Conda本地配方与绑定URL/SHA256的提交配方，取代旧meta.yaml及重复构建脚本。
- 补充安装身份、命令入口、资源与生成一致性检查。编辑、渲染及Word转换规则保持。

## v1.1.1

- 本地Markdown编辑、阅读与分屏预览。
- 自由笔记与工程报告、专题查看、章节和图表编号。
- 图片、组图、表格、Mermaid流程图、LaTeX公式、脚注及引用。
- 草稿恢复、内置查找、独立HTML导出和恢复。
- Word输出与独立DOCX模板样式工具。
- 快照绑定的读取、预检及plan/apply接口。

使用方式见[手册](docs/USER_GUIDE.md)，功能与支持范围见[当前状态](docs/CURRENT_STATUS.md)，维护计划见[短期计划](docs/SHORT_TERM_PLAN.md)。
