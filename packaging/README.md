# 安装与运行

HRS提供Windows浏览器便携包及标准Python安装形式，使用同一应用核心。

## Windows便携包

完整解压后，双击“启动编辑器.vbs”。程序自带Python和匹配的Word组件，日常编辑无需另外安装Python或Node。升级前退出旧程序，保留工程、附件和data目录。

Word原生组件适配Windows x64 / CPython 3.13；使用其他Python环境时，需要匹配的原生依赖。原生公式可按提示选择已有Pandoc。

## 标准Python安装

Python要求3.12及以上。分发名为hrstudio，启动命令为hrs，Python模块为html_report_studio。

```text
python -m pip install /path/to/hrstudio-<version>-py3-none-any.whl
hrs --version
hrs info
hrs start
```

也可在源码目录中执行`python -m pip install .`。pyproject.toml与setup.py提供安装所需的元数据和资源声明。

服务只监听127.0.0.1。同一数据根可使用`hrs status`与`hrs stop`管理。`hrs info`、`hrs license`不创建用户数据；Windows默认应用状态目录为`%LOCALAPPDATA%/HTMLReportStudio`，可用`HRS_DATA_DIR`或`--data-dir`指定安装目录之外的位置。工程保存在用户选择的位置，升级或卸载不主动删除。

程序化检查和HTML导出需要可选Playwright及本机浏览器，普通界面不需要安装测试依赖。Word导入与导出的组件配置见使用手册。

源码测试入口见README_TESTS.txt，产品能力与限制见app/docs/CURRENT_STATUS.md，许可见app/LICENSING.md。
