# 维护事项

开发约束见AGENTS.md，测试入口见README_TESTS.txt，功能计划见app/docs/SHORT_TERM_PLAN.md。

## 预览图片复用

预览提交时复用身份和资源未变化的图片节点，减少输入后的重复解码和绘制。资源实际变化时仍应更新；验证尺寸、懒加载、引用定位与文稿切换保持正确。

## 发行一致性

浏览器和标准Python分发使用同一app核心，身份来自app/release.json。模板工具的共用WPS源码位于template-tool，Bridge源码位于components。按改动选择测试，核对生成帮助、源码及发行清单。
