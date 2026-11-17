# 首店地图的营业状态与预约入口对照

这是首店地图资料的本地演练门户与目录采集器。演练数据仅在环回地址提供，不会操作真实用户、订单或商户。当前 `app.capture.read_catalog` 读取目录；`app.capture.capture_observations` 在浏览器里逐范围巡查详情页，把目录卡片、视口选项、地图浮层、被复用的门店标记、品牌详情与缩放状态的可见内容留为逐条观察；`app.domain` 并列比较各来源而不选真值；`app.records.save_observations` 追加会话与观察收据；`app.review.build_report` 输出带门店、页面、地图范围与时间的核对报告。

站点约定见 `docs/portal.md`；测试时从本地任意空闲端口启动演练站点。安装锁定依赖并准备 Chromium 后：

- `python -m unittest discover -s tests -v`：运行基线浏览器测试与观察测试。
- `python -m compileall -q app tests`：检查代码。
- `python -m app.site`：启动本地演练站点。
- `python -m app.cli`：自动启动演练站点，巡查全部目录项并打印逐条观察、未取舍的来源对比、身份错位与覆盖范围；`--json` 输出完整报告，`--database` 指定观察收据路径，`--item` 只巡查某一项。

上述命令都只访问本地环回页面，自动测试不依赖固定端口。
