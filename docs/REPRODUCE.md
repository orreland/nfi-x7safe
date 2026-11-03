# 复现回测

目标：在一台新机器上跑出和 `reports/baselines/` **逐笔相同**的结果。下面的命令在 Windows 的 Git Bash 和 Linux 上都能用；Linux 上把 `.venv/Scripts/python.exe` 换成 `.venv/bin/python`。

## 1. 环境

需要 Python 3.11（我们用 3.11.9）、git、约 3 GB 磁盘。跑长窗口（约 20 个月）需要约 19 GB 空闲虚拟内存，**一次只跑一个回测**。

```bash
git clone https://github.com/orreland/nfi-x7safe.git
cd nfi-x7safe
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-lock.txt
```

## 2. 取上游策略

文件不放在本仓库，脚本按固定提交取回并校验 sha256。上游以后怎么改都不影响这一步。

```bash
bash scripts/fetch_upstream.sh
```

## 3. 取行情数据

不用账户和 API key。Binance 的公开接口在某些网络环境下可能要代理。

```bash
bash scripts/download_data.sh all
```

- 已下架币取不到实时接口的数据，脚本会用 `fetch_delisted_data.py` 从 `data.binance.vision` 的月度存档恢复。
- `reports/baselines/data_manifest.csv` 记录了我们用的每个数据文件的行数、起止时间和 hash。**下载时间不同，文件 hash 和末尾时间会不同，这不一定影响结果**，以第 4 步的逐笔核对为准。
- 如果只想验证流程，运行 `bash scripts/download_data.sh main`，只下载 14 个主流币，然后跑 `main-*` 基准。

## 4. 跑基准并核对

名字的格式是 `{comm|main}-{P|R|L}-{OURS|X7|X8}`：

| 部分 | 含义 |
|---|---|
| `comm` / `main` | 全币种 / 14 个主流币 |
| `P` / `R` / `L` | 20261025-20261103 / 20260830-20261103 / 20250216-20261103 |
| `OURS` / `X7` / `X8` | 我们的版本 / 社区 X7 v17.5.206 / 社区 X8 v18.0.195 |

`comm-L` 用的是含 40 个已下架币的 survB 币种范围；其他 `comm` 窗口和服务器一致。

```bash
bash scripts/run_baseline.sh comm-L-OURS
PYTHONUTF8=1 .venv/Scripts/python.exe scripts/check_baseline.py comm-L-OURS
```

应该输出 `PASS comm-L-OURS: baseline 525 trades, re-run 525, 0 differ`。约 10 分钟（视机器而定）。

`reports/baselines/metrics.csv` 是 18 组结果的汇总（freqtrade 自带的口径）。报告里的「收益 / 最大回撤」是逐日盯市口径，来自 `scripts/eval_grid.py` 的 `analyse()`，数字略有不同。

## 5. 对账：回测和模拟盘是否一致

```bash
PYTHONUTF8=1 .venv/Scripts/python.exe scripts/compare_parity.py comm-P-OURS --db dryrun_backups/nfi-dryrun-20261103.sqlite --tolerance 15
```

先把结果 zip 解压：`eval_grid` 和 `compare_parity.py` 只读解压后的 json（`tools/experiments/unzip_results.py` 可以解压，它的路径写死了，需要改）。
这个脚本比较快照里的全部已平仓交易；只比较当前规则时，只看 `open_date` 在 2026-10-25 07:15:20 UTC 之后的交易。结论见 `reports/PARITY_COMMUNITY_2026-11-03.md`。

## 6. 回测里要注意的坑

- **硬止损：** 回测要用 `X7SafeStopHonored`，不是 `NostalgiaForInfinityX7Safe`。服务器靠交易所止损单，回测没有这种单，变体类让止损直接执行。
- **必须开 `--enable-protections`，并带上 `configs/local-overrides-safe.json`。**
- **币种范围决定结果：** 排除已下架币，收益会虚高。见 `scripts/fetch_delisted_data.py` 头部的说明。
- **`FT_LOWMEM=1`** 只省内存，开不开结果逐笔一样。
- **配置文件里有中文注释**，Windows 上要设 `PYTHONUTF8=1`。
- **回测按 K 线开盘价成交，没有滑点。** 模拟盘在开盘后几十秒才成交，价格可能已经变了。

## 验证记录

2026-11-03，在全新克隆、全新虚拟环境（Windows 11 + Python 3.11.9）里按本文操作：

| 数据来源 | 基准 | 结果 |
|---|---|---|
| `download_data.sh main` 新下载 | `main-R-OURS`、`main-L-OURS`、`main-L-X8` | 逐笔一致（3、56、48 笔） |
| 本机已有的完整数据 | `comm-P-OURS`、`comm-L-OURS` | 逐笔一致（7、525 笔） |

**没有验证的：** `download_data.sh all` 的完整下载（已下架币只试了 WING 一个币）、Linux 环境、其他 13 组基准的重跑。

## 什么情况复现不了

- **模拟盘本身：** 它用当时的实时价格，只能对账，不能完全重跑。快照放在 `dryrun_backups/`。
- **行情存档：** Binance 如果删除或修改了存档，尤其是已下架币，就可能出现差异。
- **操作系统或依赖版本不同：** 我们只在 Windows 11 + Python 3.11.9 上验证过逐笔一致。其他环境如果对不上，请先检查版本和数据。
