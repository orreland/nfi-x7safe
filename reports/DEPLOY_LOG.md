# 服务器部署记录（dry-run 机器人）

服务器 `<服务器IP>`（云服务器）。这里按时间记录对服务器上运行代码或配置的每一次改动。
**分析 dry-run 数据时，以每条记录的「生效时间」为界分段，不要把不同规则下的交易混在一起统计。**
同一份记录也放在服务器上：`/opt/nfi/DEPLOY_LOG.md`。

## 当前状态（随每次部署更新）

| 项 | 值 |
|---|---|
| 运行中的策略文件 | `/opt/nfi/user_data/strategies/NostalgiaForInfinityX7Safe.py` |
| 加载进内存的版本 | **#4（N25 + E10），2026-10-25 07:15:20 UTC 起**（07:28 演练时重启过一次，当前 PID 1141453） |
| 每周重启 | `nfi-dryrun-restart.timer`，周日 03:17 UTC（随机延迟 ≤ 5 分钟）；**有持仓时跳过**，顺延一周 |
| 确认当前加载的是哪版 | 重启时间 `systemctl show nfi-dryrun -p ActiveEnterTimestamp` 晚于该版的部署时间，即已加载 |

## X7Safe（`nfi-dryrun.service`）

| # | 部署时间（UTC） | 生效时间（UTC） | 改动 | 文件 sha256 | 部署前备份 |
|---|---|---|---|---|---|
| 0 | 2026-08-24 | 2026-08-30 23:50 首笔 | dry-run 启动：X7Safe（doom 止损接线、30 天时间止损、grind 预算 0.5、百分比仓位） | `eb879d…` | — |
| 1 | 2026-09-30 05:27 | 2026-09-30 05:28（手动重启） | confirm_trade_exit 放行 stoploss_on_exchange 的止损，修 emergency_exit 竞态；同时加了每周受控重启 | `7852fb…` | `.bak-20260930052733` |
| 2 | 2026-10-17 12:04 | 2026-10-18 03:19（每周重启） | 只改统计和日志：SAFE-TRIGGER 汇总改为每小时从 trades 表统计，重启不清零 | `de52d5…` | `.bak-20261017120411` |
| 3 | 2026-10-18 15:48 | **2026-10-25 07:15:20（空仓时手动重启）** | MaxDrawdown 保护改为按账户权益计算（`calculation_mode: equity`，E10），去掉误报 | `150278…` | `.bak-20261018154834` |
| 4 | 2026-10-18 16:47 | **2026-10-25 07:15:20（与 #3 同时）** | **N25：非 rebuy 交易的硬止损从首仓价 −15% 放宽到 −25%**，rebuy 仍为 −15%；新增 `HARD-STOP-SET` 日志行 | `5cd599…` | `.bak-20261018164737` |

各次改动的依据与回测，见 `reports/REBUY_AB_PARITY_2026-10-17.md`：#1 见文件内第 9 节注释，#2 见第 18.3 节，#3 见第十九、二十节，#4 见第十四~十七、二十一节。

回滚通用命令（把 `<备份>` 换成上表的备份文件名，然后等下次重启，或手动 `systemctl restart nfi-dryrun`）：

```bash
install -o nfi -g nfi -m 644 /opt/nfi/user_data/strategies/NostalgiaForInfinityX7Safe.py.<备份> /opt/nfi/user_data/strategies/NostalgiaForInfinityX7Safe.py
```

### 生效情况追记

- **2026-10-25 03:17 UTC：** 每周重启**被跳过**。`nfi_safe_restart: 1 open trade(s) - skipping restart`，当时持有 AVA/USDT（tag 64，03:55 以 +1.92% 平仓）。
  #3、#4 仍未加载，进程仍是 10-18 03:19 起的 PID 977055；下次自动尝试是 2026-11-01 03:17 UTC。
  07:13 UTC 检查时已空仓。
- **2026-10-25 07:15:20 UTC：用户确认后手动重启，#3（E10）与 #4（N25）生效。**
  - 重启前三重确认空仓：DB 持仓 0、未完成订单 0、API `count` 返回 current 0；线上文件 sha256 为 `5cd599…`；
  - 用服务器自带的 `/opt/nfi/scripts/nfi_safe_restart.py` 重启，它会再检查一次持仓（输出 `no open trades - restarting`）；
  - 重启后：新 PID 1140593，`ActiveEnterTimestamp` 为 07:15:20，NRestarts 0；
  - 启动日志：`Strategy using use_custom_stoploss: True`（只有 #4 的代码会打开它）、`stoploss: -0.15`、
    MaxDrawdown / Cooldown / StoplossGuard 三个保护都已加载，`Dry run is enabled`；
    `__pycache__` 里的 X7Safe 字节码在 07:15:32 重新编译，确认加载的是新文件；
  - 07:16:44 心跳 `state='RUNNING'`；SAFE-TRIGGER 汇总正常输出
    （doom 4 / emergency_exit 4 / 交易所侧止损 6 / 补丁放行 2）；重启后没有任何 ERROR 或 Traceback；
    服务内存 791 MB，系统可用 692 MB。
  - **dry-run 新样本从 2026-10-25 07:15:20 UTC 开始**：此后新开的交易适用 N25 + E10，之前的 72 笔（−756.31 USDT）属于旧规则。
  - **还没完成的验证：** 交易所侧止损单是否直接挂在 −25%。要等第一笔非 rebuy 交易成交后，按 #4 第 1~3 点检查。
- **2026-10-25 07:27~07:30 UTC：应急手册演练**（`scripts/deploy/RUNBOOK_EMERGENCY.md` 第 6 节），两个机器人都空仓。
  NFI 与 Combined_V3 各停一次、启动一次；代码没有改动，仍是 #4。NFI 新 PID 1141453（07:28:12 启动），
  Combined_V3 容器重启一次。演练期间没有任何交易，dry-run 新样本的起点仍是 07:15:20。

### #4 N25 详细记录

- **部署前校验（本地）：**
  - 新 X7Safe 在 W1 上与预注册测过的 `X7SafeOtherStop25` **逐笔完全相同**（同为 E10 底座，479 笔，13620.39 USDT）；
  - 止损价 / 首仓价：非 rebuy 0.750，rebuy 0.850；`HARD-STOP-SET` 日志 299 行，等于非 rebuy 交易数；
  - 与 #3 合并后的 18 个月回测：+135.45%，回撤 10.29%，收益/回撤 13.2，Sharpe 2.87
    （只有 #3 时为 +126.15% / 10.75% / 11.7 / 2.79）。
- **部署前校验（服务器）：** 线上文件为 #3 的 `150278…`；上传文件 hash 一致；服务器 venv 编译通过；
  `stoploss_from_absolute` 导入可用；diff 只有 N25 逻辑和注释更正。
- **部署后：** 新文件 `5cd599…`，属主 nfi:nfi 644；服务未重启（PID 977055），心跳正常。
  部署时持有 GTC/USDT（tag 65，rebuy 交易，不受 N25 影响）。
- **dry-run 样本分段：** 生效重启之后**新开的**非 rebuy 交易才适用 −25%；重启前已开的仓位止损不变。
  统计 N25 的 dry-run 表现，只看 `open_date` 晚于生效重启时间的交易。
- **生效后要盯的（回测验证不了的部分）：** 交易所侧止损单能否在首仓成交后直接挂在 −25%。
  1. 日志里出现 `HARD-STOP-SET [...] other -25% of first entry X -> stop Y`：
     `grep HARD-STOP-SET /opt/nfi/user_data/logs/dryrun.log | tail`
  2. 每笔持仓的「DB 止损价 / 首仓价」和「交易所止损单价 / 首仓价」（已在服务器上实测可用，2026-10-18 部署时
     GTC rebuy 单两项都是 0.85）。生效后，非 rebuy 交易两项都应为 **0.75**，rebuy 为 0.85：

     ```bash
     python3 - <<'EOF'
     import sqlite3
     c = sqlite3.connect('file:/opt/nfi/user_data/tradesv3.dryrun.sqlite?mode=ro', uri=True)
     first = "(select coalesce(o2.average,o2.price) from orders o2 where o2.ft_trade_id=t.id and o2.ft_order_side='buy' and o2.status='closed' order by o2.id limit 1)"
     q = f"""select t.pair, t.enter_tag, round(t.stop_loss/{first},3),
       (select round(o.stop_price/{first},3) from orders o where o.ft_trade_id=t.id and o.ft_order_side='stoploss' and o.status='open' order by o.id desc limit 1)
       from trades t where t.is_open=1"""
     for r in c.execute(q): print(r)
     EOF
     ```
  3. 如果非 rebuy 交易的第二项（交易所止损单）停在 0.85 而不是 0.75，说明 freqtrade 没有按预期撤单重挂，
     需要回滚到 `.bak-20261018164737`。
- **回滚：** `install -o nfi -g nfi -m 644 /opt/nfi/user_data/strategies/NostalgiaForInfinityX7Safe.py.bak-20261018164737 /opt/nfi/user_data/strategies/NostalgiaForInfinityX7Safe.py`
  （回到只有 #3 的版本），然后重启。

## Combined_V3（Docker `combined_v3_dryrun`）

| # | 时间（UTC） | 改动 |
|---|---|---|
| 0 | 2026-09-06 08:49 | 容器启动（Combined_V3，钱包 1000，max_open_trades 5）。此后没有改动 |
| — | 2026-10-25 07:28 | 应急手册演练：`docker stop` / `docker start` 各一次，代码和配置没有改动 |
