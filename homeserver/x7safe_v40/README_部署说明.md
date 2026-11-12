# 第三个家用模拟盘：X7Safe 副本 + 只开前 40 个币（草稿，还没启动）

依据：`reports/PLAN_V40_SPEEDUP_2026-11-10.md` 第三节第 ③ 条。
目的：在同一台电脑上，实测「101 个币」和「40 个币」时，每根 5 分钟 K 线各要算多少秒；顺便看每天选出的 40 个币和回测是否一致。

**不动云服务器，也不动家用机上现有的两个机器人。** 只跑模拟盘，不填任何 key。

## 这个文件夹里有什么

| 文件 | 作用 |
|---|---|
| `docker-compose.yml` | 新容器 `x7safe_v40_home_dryrun`。配置链和 `n7_x7safe_dryrun` 完全相同，只多了一个 `pairlist-volume40.json`，放在静态币种名单后面 |
| `configs/pairlist-volume40.json` | 在 101 个币后面加一层成交额过滤：取过去 30 天成交额前 40 |
| `configs/homeserver-x7safe-v40.json` | 名字、独立数据库 `tradesv3.x7safe-v40-home.sqlite`；本金 10000；Telegram 和网页接口都关 |

已在本机检查：
- 配置合并后：模拟盘、本金 10000、4 个仓位、没有 key、接口关闭。
- 2026-11-10 用这套配置短跑了一次本地模拟盘，日志显示 `Whitelist with 40 pairs`。
- 每日名单检查脚本 `tools/v40_list_check.py` 核对了这 40 个币，和回测排名表**完全一致（差 0 个）**。

## 给家用电脑 AI 的提示词（你同意后再复制过去）

---

在家用服务器上加第三个模拟盘机器人，**不要动现有的 `n7_original_dryrun`、`x7safe_home_dryrun`、`ft-bot1`、`ft-bot2`**。

1. 新建 `%USERPROFILE%\nfi\NFI_homeserver_20261110\n7_x7safe_v40\`，按下面复制：
   - 从 `n7_x7safe_dryrun\` 复制 `configs\` 整个文件夹，以及 `user_data\strategies\` 整个文件夹。**不要**复制 `user_data` 里的 `.sqlite` 和 `logs`。
   - 再把移动盘 `x7safe_v40\` 里的 `docker-compose.yml` 和 `configs\` 下的两个 json 复制进去，同名的覆盖。
   - 新建空文件夹 `user_data\logs\`。
2. 核对策略文件：去掉 `\r` 之后，`NostalgiaForInfinityX7.py` 的 sha256 开头应是 `bfe78d11c156`，`NostalgiaForInfinityX7Safe.py` 的应是 `5cd599e272d1`。对不上就停下来报告。
3. **启动前**确认 `x7safe_home_dryrun` 当前没有持仓（`healthcheck.ps1` 里看开仓数）。有持仓就等它卖完再启动，让两个副本从同样的空仓状态开始。
4. 启动：`cd ...\n7_x7safe_v40; docker compose up -d`。在日志里确认这几行：
   - `Dry run is enabled`；
   - `Using volume range of 30 candles, timeframe: 1d`；
   - `Whitelist with 40 pairs: [...]`；
   - 没有 ERROR。
5. 观察 1 小时，用之前的 `cpu_sampler.py` 和同样的方法（K 线开始后最长一段连续 ≥80%），同一根 K 线同时测三个机器人，至少测 3 根。
6. **每天** UTC 00:05 之后（北京时间 08:05 之后），把日志里当天第一条 `Whitelist with 40 pairs` 那一行抄进报告。
7. 把结果加进 `~/nfi/HOMESERVER_REPORT.md` 新的一节，写清楚：
   - 三个机器人每根 K 线各要算几秒；
   - 内存占用；
   - 每天的 40 个币名单；
   - 遇到的问题。

规则和上次一样：
- 只跑模拟盘，不填任何 key 或 token；
- 不改策略和配置；
- 不升级镜像；
- 不开放端口；
- 不删除数据库；
- 不确定的地方先问。

---

## 回退

```powershell
cd $env:USERPROFILE\nfi\NFI_homeserver_20261110\n7_x7safe_v40; docker compose stop
```

数据库和日志都会留着。另外两个机器人不受影响。
