# 标准安装与构建

HRS以同一app核心提供Python/浏览器形式。基础wheel包含原服务、网页、离线前端资源、许可和当前帮助，不包含解释器、Node、浏览器、测试、历史或用户工程。Python>=3.12，服务只监听127.0.0.1；noarch不代表已经完成跨平台实机验收。

## 安装与使用

安装分发名为`hrstudio`，启动命令仍为`hrs`，Python模块保持`html_report_studio`。从本仓库Release下载wheel，在独立环境中安装。PyPI尚未上传，conda-forge须等配方PR合并及频道构建完成后才可远端安装；不要用其他同名包代替本项目。

```text
python -m pip install /path/to/hrstudio-<version>-py3-none-any.whl
hrs --version
hrs info
hrs start
```

无浏览器调试用hrs start --no-browser --keep-alive，同一数据根用hrs status/stop。python -m html_report_studio是同一入口。info/license不创建数据；Windows默认用户状态根为%LOCALAPPDATA%/HTMLReportStudio，可用HRS_DATA_DIR或--data-dir指定安装资源之外的目录。用户工程仍在所选位置，升级/卸载不主动删除。

浏览器便携包自带Python3.13和匹配Word组件，普通使用最方便。标准包没有捆绑Word组件；Release可选组件中的cp313原生库只适配Windows x64 Python3.13，其他解释器须安装匹配依赖并配置对应源码。原生公式仍需按提示选择Pandoc。程序化check/HTML需可选Playwright和明确的本机浏览器；普通GUI不依赖测试环境。

## 从同一源码构建

版本只来自app/release.json。公开发行从1.1.2起使用一个公开版本对应一个tag，Python与Conda元数据使用同一版本；旧版R2派生的.post2是有效的Python公开版本，不再作为新发行策略。分发名、入口和依赖来自pyproject.toml。setuptools构建原app，不复制第二份编辑/保存/转换代码。

```text
python -m pip wheel . --no-deps --no-build-isolation --wheel-dir /new/output
python setup.py sdist --dist-dir /new/output
```

浏览器便携包由tools/build_release.py在明确基础ZIP与SHA上生成，原Python/启动器/vendor/CSS保持；公开Word组件仅替换通用封面示例并附许可与源码入口，变更须通过精确指纹策略。tools/verify_release.py独立检查清单、组件和同核字节。构建/测试输出必须放源码树之外。

桌面宿主已做可行性及本机专项，当前封存。保留desktop及统一构建/离线更新代码，恢复时先核对固定运行库与宿主协议，再运行受影响宿主/目标机验收；本次公开Release不提供新桌面二进制。

## Conda构建与提交

packaging/conda/recipe.yaml使用v1格式，由tools/build_conda_recipe.py读取release.json与pyproject.toml生成。仓库配方的source.path供本地构建，构建脚本及入口声明只有这一份；不再并列维护meta.yaml、bld.bat和build.sh。

```text
python tools/build_conda_recipe.py --write
python tools/build_conda_recipe.py --check
rattler-build build --recipe packaging/conda/recipe.yaml --output-dir /new/conda-output --no-include-recipe
```

GitHub tag固定后，下载公开源归档并核对SHA256，以同一生成器产生staged-recipes配方：

```text
python tools/build_conda_recipe.py --source-url 'https://github.com/yyyyy-9/HRS/archive/refs/tags/v${{ version }}.tar.gz' --source-sha256 <64位SHA256> --output /new/recipes/hrstudio/recipe.yaml
```

提交版只替换source为公开HTTPS地址和完整SHA256，避免把本地路径提交到CI；包名、版本、依赖、CLI、许可和安装测试仍来自同一生成器。生成不会上传包或创建PR。升级时重新生成、实际构建并检查版本及资源。PR合并和频道构建完成后，安装命令为`conda install -c conda-forge hrstudio`，启动仍使用`hrs`。noarch仅描述基础包构成，Word原生组件与系统交互的适配范围不变。

公开Conda附件使用`--no-include-recipe`，避免构建器将本地绝对来源路径写入包内配方。统一配方同时排除pip生成的`direct_url.json`，其PEP610来源也可能指向临时目录。应用、许可、版本和依赖不变；公开源码/配方仍随Git提供。构建后检查实际包中的App字节和元数据，不只核对安装成功。

曾安装旧分发`html-report-studio`的环境应先卸载旧分发，再安装hrstudio；两者提供同一个模块及命令，不能共存。卸载不会主动删除环境外的工程及用户数据。

测试入口见README_TESTS.txt；当前能力/未测范围、许可和对应源码分别见app/docs/CURRENT_STATUS.md、app/LICENSING.md、components/README.md。
