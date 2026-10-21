# 前端依赖来源

精确运行文件与notice的SHA256由app/RIGHTS.json记录，仓库保留实际分发文件。

- Marked：web/vendor/marked.js是可读UMD完整分发文件，保留作者notice；原文件未嵌入包版本，按SHA固定。上游源码：https://github.com/markedjs/marked 。
- CodeMirror/Lezer：包名和精确版本见RIGHTS.json的bundled_packages；上游源码分别为https://github.com/codemirror、https://github.com/lezer-parser及各MIT组件。HRS仅在原bundle尾部导出现有原语，变更前后完整字节与摘要由tools/expose_editor_api.py及发布策略核对，上游运行负载不替换。
- MathJax：3.2.1，源码https://github.com/mathjax/MathJax-src/tree/3.2.1，发行文件https://github.com/mathjax/MathJax/tree/3.2.1；boldsymbol扩展同接口，官方分发摘要另核对。
- Mermaid：12.2.0，源码https://github.com/mermaid-js/mermaid/tree/mermaid%4012.2.0，保留原MIT许可；本地完整引擎与静态SVG导出保持。

这些链接用于定位依赖，不要求编辑器运行时联网。运行文件与许可在仓库内，构建不会自动下载依赖或替换已验证vendor。
