# 本地来源行为

首店地图目录列出稳定的 `data-key` 和详情路径；详情需由浏览器导航读取，`视口`选择改变当前页面状态，`地图浮层`和`品牌详情`是分步出现的可见内容。地图平移复用标记且缩放会裁剪区域。详情接口是浏览器页面，不是业务 API；运行时只允许访问环回来源。

`fixtures/portal.json` 提供合成业务资料，不包含真实个人数据。`records.save_catalog` 覆盖同一目录身份；`records.save_detail_entries` 以业务键追加入口访问，不把入口访问等同于资格、授权、可预约或正式提交。测试均只访问本地环回页面。

## 巡查与观察收据

`capture.capture_observations(origin, item_id, checkpoint=None)` 在真实 Chromium 里逐个可见地图范围巡查，并逐条留下观察：

- `catalog_card`：目录卡片上的地址与状态，来源是目录页；
- `map_overlay` / `brand_detail_panel`：`视口`每个选项下的地图浮层与品牌详情面板；
- `map_scope`：进入某个可见范围时页面的范围文字；
- `map_marker`：点击当前标记后它自己的门店键、地址与浮层文字；
- `brand_page`：品牌详情显示的营业状态与地址；
- `map_zoom`：缩放后“部分区域未加载”的可见状态。

每条观察都带 `session_id`、`sequence`、`observed_at`、`source`（页面 URL）、`item_id`（页面身份）、`store`（可见门店键）和 `region` / `scope_visited`（地图范围）。因此每条观察都能回到具体门店、页面和那次地图范围。

约束与已处理的行为：

- **标记复用**：平移后必须在点击标记之后重新读取它的 `data-store`、地址和浮层，不能沿用上一范围的值。
- **部分加载**：缩放只加载部分区域时，隐藏标记记为 `partial`，不推断该范围没有门店。
- **同品牌多店**：按门店键（`store-*`）而不是名称或相似地址归并；页面身份与可见标记不同会单列为身份错位。
- **中途退出**：`checkpoint(payload)` 在每个观察后调用，`status` 为 `running`；中断时保存 `interrupted` 会话，`unvisited_scopes` 明确列出尚未访问的范围。任何未访问范围在覆盖报告中都是 `state='unvisited'`、`absence_claim=False`。
- **冲突**：`domain.compare_observations` 只在同一主体同一字段出现多个取值时并列列出各来源，保留原始文字、页面、范围、会话与时间，不选真值；`review.build_report` / `review.explain_conflicts` 输出可直接核对的报告。

`records.save_observations` 把一次会话与它的逐条观察写入 SQLite（同一 `session_id` 整体替换），`records.read_observations` / `read_sessions` / `read_conflicts` 读回观察与并列冲突。`app.cli` 演示完整流程：自动启动本地站点、巡查全部目录项、打印逐条观察与来源对比。
