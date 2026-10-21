# 模拟项目（数据只为演示）

## 结果 {#sec-results}

强度为 $I=|E|^2$。请见 @fig:fig-beam、@tbl:tbl-sample 和 @sec:sec-results。

<!-- hrs:eq id=eq-energy -->
$$
E=mc^2
$$

由 @eq:eq-energy 可得。

<!-- hrs:list style=paren-decimal -->
1. 建立模型
1. 记录参数

```report-figure
{
  "schema": "report-figure-v1",
  "kind": "image",
  "id": "fig-beam",
  "caption": "原波前强度图",
  "src": "assets/0123456789abcdef.png",
  "sourceAsset": "assets/0123456789abcdef.emf",
  "alt": "光斑强度分布",
  "rendition": {
    "format": "png",
    "dpi": 300,
    "page": 1,
    "engine": "win-gdi"
  }
}
```

```report-table
{
  "schema": "report-table-v1",
  "id": "tbl-sample",
  "caption": "实验条件",
  "rows": [
    [
      {
        "text": "参数",
        "rowspan": 1,
        "colspan": 1
      },
      {
        "text": "数值",
        "rowspan": 1,
        "colspan": 1
      }
    ],
    [
      {
        "text": "波长",
        "rowspan": 1,
        "colspan": 1
      },
      {
        "text": "193.35 nm",
        "rowspan": 1,
        "colspan": 1
      }
    ]
  ],
  "columnWidths": [
    45,
    55
  ]
}
```

::: {#fig-comparison layout-ncol=2 layout-nrow=1 subfig-labels=off}

![情形 A](assets/sample-a.png)

![情形 B](assets/sample-b.png)

两个情形的对比

:::

```python
print("hello")
```
