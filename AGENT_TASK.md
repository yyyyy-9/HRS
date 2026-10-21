# 维护事项

开发约束见AGENTS.md，测试入口见README_TESTS.txt，功能计划见app/docs/SHORT_TERM_PLAN.md。

## 预览图片复用

预览提交时复用身份和资源未变化的图片节点，减少输入后的重复解码和绘制。资源实际变化时仍应更新；验证尺寸、懒加载、引用定位与文稿切换保持正确。

## 发行一致性

浏览器和标准Python分发使用同一app核心，身份来自app/release.json。模板工具的共用WPS源码位于template-tool，Bridge源码位于components。按改动选择测试，核对生成帮助、源码及发行清单。

### DIST-02：Conda 分发身份

安装分发名使用hrstudio，启动命令仍为hrs，Python模块保持html_report_studio。1.1.2公开版本与Python/Conda元数据一致。v1配方由tools/build_conda_recipe.py读取原身份和pyproject生成，本地source.path与提交用URL/SHA只改变来源。旧meta.yaml及独立构建脚本由同一v1脚本替代。验收覆盖配方生成、无效摘要拒绝、实际wheel/sdist/Conda安装、CLI/资源/版本及同核清单；公开频道状态须以实际PR/发布结果为准。

### DIST-03：Windows产物清单编码

Windows的cp1252控制台列出中文资源文件名时会失败，构建和包内测试通过后仍会中断CI。源规范资源统一为source_format_v1.md，release_info.SOURCE_SPEC供服务和文档检查共用；旧中文HTTP入口映射到同一文件。所有格式使用同一App，不保留第二份规范。回归覆盖cp1252路径输出、真实文档HTTP及旧地址兼容，并实际重跑发行与Conda CI；1.1.2标签保持，修复使用新版本1.1.3。
