# 可选Word组件的对应源码

来源与升级范围统一声明于`SOURCES.json`。它列出本仓库固定的Bridge/WPS源码、模板资源和生成副本；版本从对应源码读取，实际快照由Git及发行SHA清单确定。独立HRS选择自己的组件快照，不自动跟随其他项目更新。

`app/tools/audit_modules.py --write`会从声明的组件源同步浏览器模型副本并生成接口类型，`--check`核对派生文件。原Word组件构建与完整包构建核对源码/安装位置的文件集合及字节；完整包清单列出相对基线变化的组件文件和受影响契约。独立发行检查另行核对，不以版本号相同代替兼容确认。

`hrs-wps-bridge/hrs_bridge`是独立Word组件中的Bridge源码；WPS共用源码与母模板唯一放在`../template-tool`。HRS普通编辑和HTML不需要这些Python依赖。构建组件沿原`tools/build_word_support.py`，明确`--bridge components/hrs-wps-bridge --wps template-tool --wheels 本地固定wheel目录 --output 新ZIP`；固定依赖SHA和许可证随组件保留。Pandoc按需另选，不自动下载。这里不包含用户报告、办公软件或历史运行结果。

公开组件的封面示例由项目现场生成，源与脚本见template-tool；原外来封面保留本地，不再分发。组件内LICENSE、COPYRIGHT、SOURCE.txt说明自有源码及依赖的许可边界。Release中的Word组件使用Windows x64 CPython3.13，与浏览器便携包自带Python匹配；其他Python版本应按当前解释器安装依赖并从源码配置，不能直接加载cp313的原生库。
