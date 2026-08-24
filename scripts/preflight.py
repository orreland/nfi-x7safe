#!/usr/bin/env python
"""preflight.py - run this before starting (or restarting) a dry-run / live bot.

Every check here exists because the audit on 2026-08-23 found a way the setup
could be silently wrong. Exit code is non-zero if any BLOCKER fails, so this
can gate a startup script.

USAGE
  .venv\\Scripts\\python.exe scripts\\preflight.py
  .venv\\Scripts\\python.exe scripts\\preflight.py --wallet 3000
"""

from __future__ import annotations

import argparse
import filecmp
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BLOCKERS: list[str] = []
WARNINGS: list[str] = []


def ok(msg: str) -> None:
  print(f"  [OK]    {msg}")


def block(msg: str) -> None:
  BLOCKERS.append(msg)
  print(f"  [BLOCK] {msg}")


def warn(msg: str) -> None:
  WARNINGS.append(msg)
  print(f"  [WARN]  {msg}")


def _strip_jsonc(text: str) -> dict:
  """Strip `//` line comments, but not `//` inside JSON string values.

  A naive `re.sub(r"//.*", "", text)` also truncates any string value that
  legitimately contains "//" (e.g. "sqlite:///user_data/x.sqlite"), turning
  it into invalid JSON. Track string-literal state instead.
  """
  out = []
  in_string = False
  escape = False
  i = 0
  n = len(text)
  while i < n:
    c = text[i]
    if in_string:
      out.append(c)
      if escape:
        escape = False
      elif c == "\\":
        escape = True
      elif c == '"':
        in_string = False
      i += 1
      continue
    if c == '"':
      in_string = True
      out.append(c)
      i += 1
      continue
    if c == "/" and i + 1 < n and text[i + 1] == "/":
      while i < n and text[i] != "\n":
        i += 1
      continue
    out.append(c)
    i += 1
  return json.loads("".join(out))


def check_base_class_sync() -> None:
  """freqtrade loads user_data/strategies/, but `git pull` updates nfi_repo/.

  The upstream strategy exists in BOTH places. If they drift, the bot keeps
  running the stale copy with no warning at all.
  """
  print("\n[1] 上游基类是否与 git 仓库同步")
  live = ROOT / "user_data" / "strategies" / "NostalgiaForInfinityX7.py"
  repo = ROOT / "nfi_repo" / "NostalgiaForInfinityX7.py"
  if not live.exists():
    block(f"缺少 {live.relative_to(ROOT)} —— freqtrade 从这里加载基类")
    return
  if not repo.exists():
    warn(f"缺少 {repo.relative_to(ROOT)}，无法比对")
    return
  if filecmp.cmp(live, repo, shallow=False):
    ok("user_data/strategies 与 nfi_repo 的 X7 基类一致")
  else:
    block(
      "X7 基类不一致！freqtrade 跑的是 user_data/strategies 那份，"
      "而 git pull 更新的是 nfi_repo。执行 "
      "cp nfi_repo/NostalgiaForInfinityX7.py user_data/strategies/ 后重新验证回测"
    )


def check_dryrun_config() -> None:
  print("\n[2] dry-run 配置")
  safe = _strip_jsonc((ROOT / "configs" / "local-overrides-safe.json").read_text(encoding="utf-8"))
  dry = _strip_jsonc((ROOT / "configs" / "local-overrides-dryrun.json").read_text(encoding="utf-8"))

  if dry.get("dry_run") is True:
    ok("dry_run = true")
  else:
    block("local-overrides-dryrun.json 里 dry_run 不是 true")

  if dry.get("order_types", {}).get("stoploss_on_exchange") is True:
    ok("stoploss_on_exchange = true")
  else:
    warn("stoploss_on_exchange 未开启 —— 止损只在 bot 侧，bot 挂掉即失效")

  slots = safe.get("max_open_trades")
  tbr = safe.get("tradable_balance_ratio", 1.0)
  print(f"          槽位 {slots} / tradable_balance_ratio {tbr}")
  ok("槽位与资金比例已读取")


def check_sizing_vs_wallet(wallet: float) -> None:
  """Percent sizing is fine at $10k. Small accounts hit exchange minimums.

  The strategy's finest grind sub-entry is 5% of the first entry; Binance
  spot minimum notional is typically $5-10.
  """
  print(f"\n[3] 仓位规模 vs 实际本金 (${wallet:,.0f})")
  sys.path.insert(0, str(ROOT / "user_data" / "strategies"))
  sys.path.insert(0, str(ROOT / "nfi_repo"))
  try:
    from NostalgiaForInfinityX7Safe import NostalgiaForInfinityX7Safe as S

    pct, cap, mode = S.stake_pct_of_equity, S.stake_pct_cap, S.stake_sizing_mode
  except Exception as exc:  # noqa: BLE001
    warn(f"无法导入策略读取仓位参数: {exc}")
    return

  print(f"          模式 {mode} / 比例 {pct:.0%} / 上限 ${cap:,.0f}")
  first = min(wallet * pct, cap)
  finest = first * 0.05
  print(f"          首仓 ${first:,.2f} / 最细 grind 档 ${finest:,.2f}")
  if finest < 12:
    warn(
      f"最细 grind 档 ${finest:.2f} 贴近交易所最小下单额($5~10)，"
      "摊薄阶梯会被强制放大变粗（机制仍可运行，不算故障）"
    )
  else:
    ok("grind 阶梯各档均高于交易所最小下单额")

  exposure = pct * (
    _strip_jsonc((ROOT / "configs" / "local-overrides-safe.json").read_text(encoding="utf-8")).get(
      "max_open_trades", 0
    )
  )
  tbr = _strip_jsonc(
    (ROOT / "configs" / "local-overrides-safe.json").read_text(encoding="utf-8")
  ).get("tradable_balance_ratio", 1.0)
  print(f"          满仓敞口 {exposure:.0%} vs 可交易额度 {tbr:.0%}")
  if exposure >= tbr:
    block(f"满仓敞口 {exposure:.0%} >= tradable_balance_ratio {tbr:.0%} —— 最后一个槽位会被拒单")
  else:
    ok("满仓敞口低于可交易额度")


def check_blacklist_not_experimental() -> None:
  """The survivorship blacklist deliberately lets DELISTED pairs through.

  It exists for one backtest experiment. A live bot loading it would try to
  trade coins Binance has removed.
  """
  print("\n[4] 黑名单来源")
  exp = ROOT / "configs" / "blacklist-survivorship-test.json"
  if exp.exists():
    warn(
      "configs/blacklist-survivorship-test.json 存在（实验用，故意放行已下架币）。"
      "dry-run/实盘启动命令里绝不能包含它 —— 请核对启动命令用的是 blacklist-binance.json"
    )
  real = ROOT / "configs" / "blacklist-binance.json"
  if real.exists():
    ok("blacklist-binance.json 存在（真实黑名单）")
  else:
    block("缺少 configs/blacklist-binance.json")


def check_known_upstream_defect() -> None:
  """OBV_change_pct divides by cumulative OBV, whose level depends on where
  the data window starts. Backtest and live cumulate over different histories.
  """
  print("\n[5] 已知上游缺陷：OBV_change_pct 起点依赖")
  warn(
    "入场条件 47 / 65 使用 obv_change_pct，其分母是从数据起点累计的 OBV，"
    "回测与实盘的累计起点不同 → 该指标值不可比。回测中这两个 tag 占 12.2% 交易、"
    "合计 -770 USDT。dry-run 对账时若这两个 tag 的行为与回测不符，属于已知原因，"
    "不要误判为其他 bug"
  )


def main() -> int:
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--wallet", type=float, default=10000, help="实际投入的本金，用于检查仓位是否撞交易所下限")
  args = ap.parse_args()

  print("=" * 68)
  print("dry-run 启动前检查")
  print("=" * 68)

  check_base_class_sync()
  check_dryrun_config()
  check_sizing_vs_wallet(args.wallet)
  check_blacklist_not_experimental()
  check_known_upstream_defect()

  print("\n" + "=" * 68)
  if BLOCKERS:
    print(f"结果：{len(BLOCKERS)} 项阻断、{len(WARNINGS)} 项提醒 —— 不要启动")
    for b in BLOCKERS:
      print(f"  阻断: {b}")
    return 1
  print(f"结果：无阻断项，{len(WARNINGS)} 项提醒 —— 可以启动")
  for w in WARNINGS:
    print(f"  提醒: {w}")
  return 0


if __name__ == "__main__":
  sys.exit(main())
