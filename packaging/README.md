# 标准安装与构建

HRS以同一app核心提供Python/浏览器形式。基础wheel包含原服务、网页、离线前端资源、许可和当前帮助，不包含解释器、Node、浏览器、测试、历史或用户工程。Python>=3.12，服务只监听127.0.0.1；noarch不代表已经完成跨平台实机验收。

## 安装与使用

从本仓库Release下载wheel，在独立环境中安装，运行hrs。尚未上传PyPI、个人conda频道或conda-forge，不要用远端同名包代替本项目。

```text
python -m pip install /path/to/html_report_studio-<version>-py3-none-any.whl
hrs --version
hrs info
hrs start
```

无浏览器调试用hrs start --no-browser --keep-alive，同一数据根用hrs status/stop。python -m html_report_studio是同一入口。info/license不创建数据；Windows默认用户状态根为%LOCALAPPDATA%/HTMLReportStudio，可用HRS_DATA_DIR或--data-dir指定安装资源之外的目录。用户工程仍在所选位置，升级/卸载不主动删除。

浏览器便携包自带Python3.13和匹配Word组件，普通使用最方便。标准包没有捆绑Word组件；Release可选组件中的cp313原生库只适配Windows x64 Python3.13，其他解释器须安装匹配依赖并配置对应源码。原生公式仍需按提示选择Pandoc。程序化check/HTML需可选Playwright和明确的本机浏览器；普通GUI不依赖测试环境。

## 从同一源码构建

版本只来自app/release.json，R1使用基础版本，后续R2派生.post2。setuptools构建原app，不复制第二份编辑/保存/转换代码。

```text
python -m pip wheel . --no-deps --no-build-isolation --wheel-dir /new/output
python setup.py sdist --dist-dir /new/output
```

浏览器便携包由tools/build_release.py在明确基础ZIP与SHA上生成，原Python/启动器/vendor/CSS保持；公开Word组件仅替换通用封面示例并附许可与源码入口，变更须通过精确指纹策略。tools/verify_release.py独立检查清单、组件和同核字节。构建/测试输出必须放源码树之外。

桌面宿主已做可行性及本机专项，当前封存。保留desktop及统一构建/离线更新代码，恢复时先核对固定运行库与宿主协议，再运行受影响宿主/目标机验收；本次公开Release不提供新桌面二进制。

## conda准备

packaging/conda配方从同一release.json派生版本，当前source.path用于本地构建。公开GitHub归档固定后，可在单独发布任务中改为不可变source.url/sha256并准备频道CI；本次没有构建或上传conda成品，也未提交conda-forge PR。

测试入口见README_TESTS.txt；当前能力/未测范围、许可和对应源码分别见app/docs/CURRENT_STATUS.md、app/LICENSING.md、components/README.md。
