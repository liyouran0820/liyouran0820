# 主页统计维护

此文件记录统计口径、生成方式与更新流程。可见主页内容维护在 `README.md`，项目卡片维护在 `assets/project-liaoxi*.svg`，本统计区的布局与配色统一维护在 `scripts/update_metrics.py`；不要手改生成文件。

## 数据口径

- Stars：公开、自有、非 Fork 仓库当前收到的星标总数。
- Commits：当年 GitHub 贡献统计收录的公开仓库提交；按 `commitCount` 求和，包含向他人公开仓库作出的贡献。GitHub 是否收录提交取决于账号、邮箱及默认分支等规则。
- PRs / Issues：账号创建的公开 PR / Issue 累计数量。
- 评级：使用 [github-readme-stats](https://github.com/anuraghazra/github-readme-stats/blob/master/src/calculateRank.js) 的公式；输入为上述公开统计、当年的公开审查贡献及公开关注者数量。该评级不是 GitHub 官方评级。算法 MIT 许可保留在 `scripts/rank-LICENSE.txt`。
- Top Languages：公开、自有、非 Fork 仓库的 GitHub 语言字节数；所有语言参与分母，超过六种时显示前五种并将其余合并为 Other。与熟练程度无关。
- Activity：最近 31 个完整 UTC 自然日，结束于昨天。数据来自**未登录访问**的 GitHub 贡献日历；若本人在 GitHub 开启显示私有贡献，曲线可包含其已公开的匿名计数。不会从登录凭据提取私有日历数据。
- Languages & Tools：已确认的技术与工具列表，不随语言字节排名自动增删，也不表示熟练程度。

仅保存汇总值、语言字节数及日期计数到 `assets/dashboard/data.json`。不保存凭据、私有仓库名、文件路径或提交内容。年度提交目前支持最多 100 个贡献仓库，单仓库最多 100 种语言；触及限制时更新失败并保留原统计，不静默截断。仓库、提交和审查连接按需分页。

## 更新与验证

GitHub Actions 的 **Update profile metrics** 每六小时运行，可手动触发。使用仓库现成的 `GITHUB_TOKEN`，无需额外 PAT 或第三方统计服务。失败时保留上一版图片；通过 Actions 日志排查，勿把访问令牌写入日志或仓库。

本地需要 Python 3 与已登录的 GitHub CLI：

```sh
python3 -m unittest discover -s scripts -p 'test_*.py' -v
python3 scripts/update_metrics.py
git diff --check
```

桌面统计为两列，手机版为纵向排列；曲线和工具区同样各有一版。修改排版后预览两种尺寸，并检查图表轴线、文字、百分比及零活动状态。视觉结构参考 [Hej28 的主页](https://github.com/Hej28/Hej28)，SVG 渲染代码在本仓库单独实现，沿用现有深蓝与深绿项目卡的配色。
