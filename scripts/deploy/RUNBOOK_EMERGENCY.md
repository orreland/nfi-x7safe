# 出事了怎么办：一键停止手册（2026-10-17）

适用于服务器 `<服务器IP>` 上的两个 dry-run 机器人。上实盘后同样适用，另见第 5 节的实盘附加步骤。
**先止血，再查原因。** 判断不了严重程度时，直接按 L2 → L3 走，dry-run 阶段没有任何代价。

| 机器人 | 运行方式 | 本地 API | API 凭据所在文件（不要复制到别处） |
|---|---|---|---|
| X7Safe（NFI） | systemd `nfi-dryrun.service` | `127.0.0.1:8082` | `/opt/nfi/configs/local-overrides-dryrun.json` 的 `api_server` |
| Combined_V3 | Docker `combined_v3_dryrun` | `127.0.0.1:8081` | `/home/root/combined-v2-dryrun/user_data/config-dryrun-v2-server.json` 的 `api_server` |

两个 API 都只监听服务器本机，必须先 SSH 上去再操作。

## 0. 准备：登录并定义一个 `ftapi` 命令（每次 SSH 会话执行一次）

```bash
ssh root@<服务器IP>
```

```bash
ftcred() { python3 -c "import json,re,sys;c=json.loads(re.sub(r'(?m)^\s*//.*$','',open(sys.argv[1]).read()));a=c['api_server'];print(a['username']+':'+a['password'])" "$1"; }
NFI_U=$(ftcred /opt/nfi/configs/local-overrides-dryrun.json)
V3_U=$(ftcred /home/root/combined-v2-dryrun/user_data/config-dryrun-v2-server.json)
ftapi() { local who=$1 method=$2 path=$3 body=${4:-}; local u port; if [ "$who" = nfi ]; then u=$NFI_U; port=8082; else u=$V3_U; port=8081; fi; curl -s -u "$u" -X "$method" -H 'Content-Type: application/json' ${body:+-d "$body"} "http://127.0.0.1:$port/api/v1/$path"; echo; }
```

凭据只存在于这个 shell 会话的变量里，不写入任何文件，也不会出现在屏幕上。

## 1. 先看现状（只读）

```bash
ftapi nfi GET count; ftapi nfi GET status
ftapi v3  GET count; ftapi v3  GET status
systemctl is-active nfi-dryrun; docker ps --filter name=combined_v3_dryrun --format '{{.Status}}'
```

`count` 返回 `{"current": 持仓数, "max": 槽位, "total_stake": 占用资金}`。

## 2. 分级处置

| 级别 | 什么时候用 | 效果 | 可逆性 |
|---|---|---|---|
| **L1 停止开新仓** | 行情异常、怀疑策略 / 数据有问题，但现有仓位还想让策略自己管 | 不再开新仓，已有仓位照常止盈止损 | 完全可逆 |
| **L2 平掉所有仓位** | 确定要离场；交易所 / 币种出问题；回撤超出底线 | 全部市价平仓 | 不可逆（已成交） |
| **L3 停止机器人** | 机器人行为异常（重复下单、报错刷屏）、要改代码或配置 | 进程停止，不再做任何事 | 可逆（重新启动） |

### L1 停止开新仓

```bash
ftapi nfi POST stopentry
ftapi v3  POST stopentry
```

恢复：`ftapi nfi POST start` / `ftapi v3 POST start`（重启进程也会恢复）。

### L2 平掉所有仓位（先做 L1，避免平完又开新仓）

```bash
ftapi nfi POST stopentry; ftapi nfi POST forceexit '{"tradeid":"all"}'
ftapi v3  POST stopentry; ftapi v3  POST forceexit '{"tradeid":"all"}'
```

确认：几秒后 `ftapi nfi GET count` / `ftapi v3 GET count` 的 `current` 应为 0。

### L3 停止机器人

```bash
ftapi nfi POST stop; systemctl stop nfi-dryrun
systemctl stop nfi-dryrun-restart.timer     # 否则周日 03:17 的定时器可能把它重新拉起
docker stop combined_v3_dryrun              # 重启策略是 unless-stopped，手动 stop 后不会自启
```

确认：`systemctl is-active nfi-dryrun` 显示 `inactive`，`docker ps` 里没有 `combined_v3_dryrun`。

恢复：

```bash
systemctl start nfi-dryrun && systemctl start nfi-dryrun-restart.timer
docker start combined_v3_dryrun
```

## 3. API 不响应时（进程卡死、内存耗尽）

服务器只有 1 核 / 2 GB，内存余量很小，卡死是现实风险。

```bash
systemctl kill -s SIGKILL nfi-dryrun; systemctl stop nfi-dryrun nfi-dryrun-restart.timer
docker kill combined_v3_dryrun
```

强杀不会平仓。dry-run 下仓位只是数据库记录，重新启动后机器人会接着管。实盘下见第 5 节。

## 4. 事后

1. 留证据：
   - 日志：`/opt/nfi/user_data/logs/dryrun.log`、`/home/root/combined-v2-dryrun/user_data/logs/freqtrade.log`；
   - DB 快照（用 sqlite backup，不要直接复制正在写的文件）：
     `python3 -c "import sqlite3;s=sqlite3.connect('file:/opt/nfi/user_data/tradesv3.dryrun.sqlite?mode=ro',uri=True);d=sqlite3.connect('/root/nfi-incident.sqlite');s.backup(d)"`
2. 记下时间线：发现时间、处置级别、每一步命令的时间。
3. 原因查清之前不要恢复 L1 / L3。

## 5. 实盘附加步骤（上实盘前必须先读一遍）

1. **交易所侧挂着的止损单。** 配置了 `stoploss_on_exchange=True`，每个持仓在币安上都挂着一张止损单。
   - L2 `forceexit` 会先撤掉止损单再市价卖出，正常；
   - L3 停机器人**不会**撤掉这些止损单。它们会继续在交易所保护仓位，但机器人不在线，止损成交后也没人接手。
     停机超过几小时，就到币安 App 里确认挂单和仓位。
2. **机器人完全失控时**（API 和 SSH 都进不去），到币安 App / 网页上：
   - 撤销该 API key，或者暂时关闭它的交易权限。这是让机器人立即失去下单能力的最快办法；
   - 手动撤单、手动平仓。
3. **API key 本身的约束**（建 key 时就要做好）：只开现货交易、禁止提现、IP 白名单只放 `<服务器IP>`。
4. **`force_entry_enable` 目前在 NFI 的配置里是 `true`**（`exampleconfig.json`、`exampleconfig_secret.json`），
   意味着拿到 API 凭据就能强制开仓。上实盘前建议改成 `false`。Combined_V3 已经是 `false`。

## 6. 演练（dry-run 阶段做一次，约 10 分钟）

在两个机器人**都空仓**时做（`count` 的 `current` 为 0），以免 L2 平掉正在跑的仓位、打乱 dry-run 样本：

1. 第 0 节定义 `ftapi`，第 1 节查看状态；
2. L1：`stopentry` → 日志出现 `Changing state ... to: STOPENTRY` 或同类提示 → `start` 恢复；
3. L3：`systemctl stop nfi-dryrun` → 确认 inactive → `systemctl start nfi-dryrun` → 等心跳日志恢复；
   V3 同理用 `docker stop` / `docker start`；
4. L2 在空仓时执行一次 `forceexit all`，只验证命令能用（返回空结果即可）；
5. 记录每一步实际耗时，写回本文件末尾。

演练会改变机器人状态，需要你在场时进行。
