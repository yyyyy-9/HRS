# 贡献约定

源码只有一份app核心；浏览器、桌面及标准Python分发共用它。桌面宿主暂时封存。修改前阅读[源格式规范](app/source_format_v1.md)、[模块说明](app/docs/MODULE_OVERVIEW.md)及受影响的使用说明；不要复制解析、编号、资源保存或Word装配规则。

先用可公开的最小合成样本复现，修改后运行受影响专项。tests/tools由原test_catalog统一选择；目标软件的真实交互、调用截获和未执行分别记录，不把测试数量当产品覆盖率。

文稿/图片/模板请勿附带单位内部材料、账号凭据或个人隐私。公开夹具登记在tests/fixtures/RIGHTS.json，新增素材注明来源和许可。第三方依赖保留原notice与精确来源，不修改vendor换取绿灯。

身份从app/release.json派生，帮助由Markdown生成，不手改生成HTML。产品改动同步对应规范、帮助和测试，维护者统一生成发行清单。模板工具src是现有WPS实现，避免在GUI或HRS另写样式迁移。

提交遵守本仓库GPL-3.0-or-later；第三方材料只在有权分发时加入。Issues/PR请说明问题、预期、复现及验证范围，无需提供真实业务报告。
