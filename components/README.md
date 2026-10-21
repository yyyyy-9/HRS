# 可选Word组件的对应源码

`hrs-wps-bridge/hrs_bridge`是独立Word组件中的Bridge源码；WPS共用源码与母模板唯一放在`../template-tool`。HRS普通编辑和HTML不需要这些Python依赖。构建组件沿原`tools/build_word_support.py`，明确`--bridge components/hrs-wps-bridge --wps template-tool --wheels 本地固定wheel目录 --output 新ZIP`；固定依赖SHA和许可证随组件保留。Pandoc按需另选，不自动下载。这里不包含用户报告、办公软件或历史运行结果。

公开组件的封面示例由项目现场生成，源与脚本见template-tool；原外来封面保留本地，不再分发。组件内LICENSE、COPYRIGHT、SOURCE.txt说明自有源码及依赖的许可边界。Release中的Word组件使用Windows x64 CPython3.13，与浏览器便携包自带Python匹配；其他Python版本应按当前解释器安装依赖并从源码配置，不能直接加载cp313的原生库。
