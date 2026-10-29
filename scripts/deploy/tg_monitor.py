#!/usr/bin/env python3
"""tg_monitor.py - read-only status reports / alerts for the two dry-run bots,
sent to Telegram. It never talks to the bots' APIs and never changes anything:
it reads systemd/docker status, log tails and the sqlite DBs (read-only).

Credentials: /root/.tg_monitor.env (chmod 600), written by the user:
    TG_TOKEN=123456:ABC...        (from @BotFather)
    TG_CHAT_ID=123456789          (optional; discovered from getUpdates and saved)

Usage (run by systemd timers, see tg-monitor-*.timer):
    tg_monitor.py report          send the summary if >= 3 days since the last one
    tg_monitor.py report --force  send the summary now
    tg_monitor.py alert           send only new alerts / notes (deduplicated)
    tg_monitor.py test            send a one-line test message
    tg_monitor.py dry             print the summary and what `alert` would send now;
                                  sends nothing, saves nothing

Two kinds of message:
    alerts  something looks wrong: bot down, stale heartbeat, a new error type,
            a loss no stop rule explains, an N25 exchange stop not at x0.75.
            Problems that persist are repeated every 6 h; one-off events go once.
    notes   things that happened by design, e.g. a doom stop at -8%. Sent once.

Plan and thresholds: reports/MONITORING_PLAN.md in the project repo.
Fixes of 2026-10-29: reports/TG_MONITOR_ISSUES_2026-10-29.md.
"""

import glob
import gzip
import json
import os
import sqlite3
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

ENV_FILE = "/root/.tg_monitor.env"
STATE_FILE = "/var/lib/tg_monitor/state.json"
NFI_DB = "/opt/nfi/user_data/tradesv3.dryrun.sqlite"
NFI_LOG = "/opt/nfi/user_data/logs/dryrun.log"
V3_DB = "/home/root/combined-v2-dryrun/user_data/tradesv3_dryrun_v2.sqlite"
V3_LOG = "/home/root/combined-v2-dryrun/user_data/logs/freqtrade.log"
N25_SINCE = "2026-10-25 07:15:20"  # DEPLOY_LOG #3/#4 effective time (UTC)
NFI_WALLET = 10000.0
BIG_LOSS = -100.0
REPORT_EVERY = timedelta(days=3)
ALERT_REPEAT = timedelta(hours=6)
EVENT_OVERLAP = timedelta(minutes=5)  # alert runs re-scan a little; keys dedupe
SENT_MEMORY = timedelta(days=4)  # > REPORT_EVERY, so once-per-period keys stay once
KNOWN_NOISE = ("Task was destroyed but it is pending",)
# ccxt websocket unsubscribe/reconnect errors: freqtrade falls back to REST
# candles by itself and carries on (up to ~1000 a day in the log history).
# Counted in the report, never alerted.
WS_NOISE = "Exception in continuously_async_watch_ohlcv"
REBUY = {"61", "62", "63", "64", "65", "68"}
GRIND = {"120"}
BJT = timezone(timedelta(hours=8))


# --------------------------------------------------------------------------- helpers
def sh(cmd: str) -> str:
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60).stdout.strip()
    except Exception:
        return ""


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def ts_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def load_env() -> dict:
    env = {}
    if os.path.exists(ENV_FILE):
        for line in open(ENV_FILE, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def save_env_value(key: str, value: str) -> None:
    lines = open(ENV_FILE, encoding="utf-8").read().splitlines() if os.path.exists(ENV_FILE) else []
    lines = [ln for ln in lines if not ln.strip().startswith(key + "=")] + [f"{key}={value}"]
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(ENV_FILE, 0o600)


def load_state() -> dict:
    try:
        return json.load(open(STATE_FILE, encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


def tg_call(token: str, method: str, params: dict) -> dict:
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/{method}", data=data)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def chat_id(env: dict) -> str:
    if env.get("TG_CHAT_ID"):
        return env["TG_CHAT_ID"]
    upd = tg_call(env["TG_TOKEN"], "getUpdates", {})
    for u in reversed(upd.get("result", [])):
        msg = u.get("message") or u.get("channel_post") or {}
        if msg.get("chat", {}).get("id"):
            cid = str(msg["chat"]["id"])
            save_env_value("TG_CHAT_ID", cid)
            return cid
    raise SystemExit("No chat found: send any message to your bot in Telegram first, then run again.")


def send(text: str) -> None:
    env = load_env()
    if not env.get("TG_TOKEN"):
        raise SystemExit(f"TG_TOKEN missing in {ENV_FILE}")
    cid = chat_id(env)
    for i in range(0, len(text), 3900):  # Telegram limit is 4096 chars
        tg_call(env["TG_TOKEN"], "sendMessage", {"chat_id": cid, "text": text[i:i + 3900], "disable_web_page_preview": "true"})


def is_rebuy(tag) -> bool:
    t = (tag or "").split()
    return bool(t) and (all(c in REBUY for c in t) or (any(c in REBUY for c in t) and all(c in REBUY | GRIND for c in t)))


def db(path: str):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def pf(rows) -> str:
    w = sum(r for r in rows if r > 0)
    l = -sum(r for r in rows if r < 0)
    return f"{w / l:.2f}" if l else ("∞" if w else "—")


# --------------------------------------------------------------------------- checks
def log_tail(path: str, n: int = 4000) -> str:
    """Last n lines of a log, continuing into the rotated <path>.1 when the live
    file is shorter. logrotate empties dryrun.log at 00:00 UTC (copytruncate);
    for about a minute after that the live file has no heartbeat yet."""
    lines = sh(f"tail -n {n} {path}").splitlines()
    if len(lines) < n:
        lines = sh(f"tail -n {n - len(lines)} {path}.1").splitlines() + lines
    return "\n".join(lines)


def last_heartbeat_age(log_text: str):
    for line in reversed(log_text.splitlines()):
        if "Bot heartbeat" in line:
            try:
                ts = datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                return (now_utc() - ts).total_seconds() / 60
            except ValueError:
                return None
    return None


def new_error_types(log_text: str, since: datetime) -> tuple:
    """({message: count} of ERROR/CRITICAL lines since `since`, websocket-noise count)."""
    seen, ws = {}, 0
    for line in log_text.splitlines():
        if (" - ERROR - " in line or " - CRITICAL - " in line or "Traceback" in line) and not any(n in line for n in KNOWN_NOISE):
            try:
                ts = datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if ts < since:
                continue
            if WS_NOISE in line:
                ws += 1
                continue
            key = line[26:].split(" - ", 2)[-1][:80]
            seen[key] = seen.get(key, 0) + 1
    return seen, ws


def health(since: datetime) -> dict:
    nfi_log = log_tail(NFI_LOG)
    v3_log = log_tail(V3_LOG)
    nfi_err, nfi_ws = new_error_types(nfi_log, since)
    v3_err, v3_ws = new_error_types(v3_log, since)
    mem = {k: int(v.split()[0]) for k, v in (ln.split(":", 1) for ln in open("/proc/meminfo")) if k in ("MemAvailable", "MemTotal")}
    return {
        "nfi_active": sh("systemctl is-active nfi-dryrun"),
        "nfi_pid": sh("systemctl show nfi-dryrun -p MainPID --value"),
        "nfi_since": sh("systemctl show nfi-dryrun -p ActiveEnterTimestamp --value"),
        "nfi_nrestarts": sh("systemctl show nfi-dryrun -p NRestarts --value"),
        "nfi_hb_min": last_heartbeat_age(nfi_log),
        "nfi_errors": nfi_err,
        "nfi_ws": nfi_ws,
        "v3_running": sh("docker inspect -f '{{.State.Running}}' combined_v3_dryrun"),
        "v3_restarts": sh("docker inspect -f '{{.RestartCount}}' combined_v3_dryrun"),
        "v3_hb_min": last_heartbeat_age(v3_log),
        "v3_errors": v3_err,
        "v3_ws": v3_ws,
        "mem_avail_mb": mem.get("MemAvailable", 0) // 1024,
        "disk_pct": int((sh("df --output=pcent / | tail -1").strip().rstrip("%") or "0")),
    }


def trades(path: str, since: str, by: str = "close_date") -> dict:
    """Closed trades with `by` (close_date or open_date) >= since, plus totals and open trades."""
    c = db(path)
    closed = c.execute(
        f"select id, pair, trim(enter_tag), close_profit_abs, close_profit, exit_reason, close_date from trades "
        f"where is_open=0 and {by}>=? order by close_date",
        (since,),
    ).fetchall()
    allc = c.execute("select count(*), coalesce(sum(close_profit_abs),0) from trades where is_open=0").fetchone()
    opn = c.execute("select pair, trim(enter_tag), stake_amount from trades where is_open=1").fetchall()
    return {"closed": closed, "all_n": allc[0], "all_pnl": allc[1], "open": opn}


def n25_stop_check() -> list:
    """NFI trades opened under N25, open or closed: (id, pair, tag, is_open, close_date,
    DB stop / first entry, latest exchange stop order / first entry).
    Non-rebuy should be 0.75, rebuy 0.85."""
    c = db(NFI_DB)
    first = ("(select coalesce(o2.average,o2.price) from orders o2 where o2.ft_trade_id=t.id "
             "and o2.ft_order_side='buy' and o2.status='closed' order by o2.id limit 1)")
    q = (f"select t.id, t.pair, trim(t.enter_tag), t.is_open, t.close_date, round(t.stop_loss/{first},3), "
         f"(select round(o.stop_price/{first},3) from orders o where o.ft_trade_id=t.id and o.ft_order_side='stoploss' "
         f"and o.stop_price is not null order by o.id desc limit 1) from trades t where t.open_date>=? order by t.id")
    return c.execute(q, (N25_SINCE,)).fetchall()


def hard_stop_set_lines() -> int:
    """HARD-STOP-SET lines since N25 in the live and the rotated NFI logs."""
    since_ts = datetime.strptime(N25_SINCE, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
    n = 0
    for path in glob.glob(NFI_LOG + "*"):
        if os.path.getmtime(path) < since_ts:
            continue
        with (gzip.open if path.endswith(".gz") else open)(path, "rt", encoding="utf-8", errors="replace") as f:
            n += sum(1 for line in f if "HARD-STOP-SET" in line and line[:19] >= N25_SINCE)
    return n


def loss_rule(reason, ratio: float, tag):
    """The X7Safe rule behind a losing exit, if the loss stays within that rule's
    limit (+2 points for fees and slippage); None if no rule explains it."""
    reason = reason or ""
    hard = 0.15 if is_rebuy(tag) else 0.25
    if "stoploss_doom" in reason and ratio >= -0.10:
        return "doom 止损（亏 8% 离场）"
    if reason in ("stop_loss", "stoploss_on_exchange") and ratio >= -(hard + 0.02):
        return f"硬止损（首仓价 −{hard:.0%}）"
    if reason.startswith("exit_time_stop") and ratio >= -(hard + 0.02):
        return "30 天时间止损"
    return None


def collect(state: dict, events_since: datetime = None) -> dict:
    """Everything the report and the alerts need. alerts / notes are (key, text, repeat):
    one-off events (losses, errors, a closed trade's stop) are looked for from
    `events_since` (default: the last report); repeat=True ones are re-sent every 6 h."""
    last = state.get("last_report_utc")
    since_dt = datetime.fromisoformat(last) if last else now_utc() - REPORT_EVERY
    ev_dt = events_since or since_dt
    since, ev = ts_str(since_dt), ts_str(ev_dt)
    h = health(ev_dt)
    nfi = trades(NFI_DB, since)
    v3 = trades(V3_DB, since)
    n25 = trades(NFI_DB, N25_SINCE, by="open_date")
    stops = n25_stop_check()

    alerts, notes = [], []
    if h["nfi_active"] != "active":
        alerts.append(("health:nfi_active", f"X7Safe 服务状态是 {h['nfi_active']}（不是 active）", True))
    if h["v3_running"] != "true":
        alerts.append(("health:v3_running", "Combined_V3 容器没有在运行", True))
    for name, key in (("X7Safe", "nfi"), ("Combined_V3", "v3")):
        hb = h[f"{key}_hb_min"]
        if hb is None:
            alerts.append((f"health:{key}_hb", f"{name} 日志里找不到心跳记录（机器人可能没在运行）", True))
        elif hb > 10:
            alerts.append((f"health:{key}_hb", f"{name} 心跳已经 {hb:.0f} 分钟没更新（机器人可能卡住了）", True))
        for msg, n in h[f"{key}_errors"].items():
            alerts.append((f"health:{key}_err:{msg}", f"{name} 新报错：{n}× {msg}", True))
    if h["mem_avail_mb"] < 200:
        alerts.append(("health:mem", f"服务器可用内存只剩 {h['mem_avail_mb']} MB", True))
    if h["disk_pct"] > 85:
        alerts.append(("health:disk", f"服务器磁盘已用 {h['disk_pct']}%", True))
    for name, t in (("X7Safe", nfi), ("Combined_V3", v3)):
        for tid, pair, tag, pnl, ratio, reason, closed_at in t["closed"]:
            if closed_at < ev or pnl is None or pnl >= BIG_LOSS:
                continue
            ratio = ratio or 0.0
            rule = loss_rule(reason, ratio, tag) if name == "X7Safe" else None
            if rule:
                notes.append((f"loss:{name}:{tid}", f"{name} {pair} 亏损 {pnl:.2f} USDT（{ratio:.2%}）：{rule}，在规则范围内", False))
            else:
                alerts.append((f"loss:{name}:{tid}", f"{name} 单笔亏损 {pnl:.2f} USDT（{pair}，{ratio:.2%}，出场原因 {reason}），止损规则解释不了", False))
    nfi_3d = sum(r[3] or 0 for r in nfi["closed"])
    if nfi_3d < -0.02 * NFI_WALLET:
        alerts.append((f"pnl3d:{since}", f"X7Safe 本期合计亏损 {nfi_3d:.2f} USDT（超过 2%）", False))
    for tid, pair, tag, is_open, closed_at, db_ratio, ex_ratio in stops:
        if is_rebuy(tag) or ex_ratio is None or ex_ratio <= 0.8:
            continue
        if is_open or closed_at >= ev:
            alerts.append((f"n25:{tid}", f"N25 可能没生效：{pair}（普通交易）交易所止损在首仓价 ×{ex_ratio}（应为 ×0.75）", bool(is_open)))
    return {"h": h, "nfi": nfi, "v3": v3, "n25": n25, "stops": stops, "alerts": alerts, "notes": notes}


def fmt_trades(name: str, t: dict) -> str:
    rows = [r[3] or 0 for r in t["closed"]]
    if not rows:
        part = "无新平仓"
    else:
        wins = sum(1 for r in rows if r > 0)
        part = f"{len(rows)} 笔，{sum(rows):+.2f} USDT（{wins} 胜 {len(rows) - wins} 负），最大单笔亏损 {min(rows):+.2f}"
    op = "、".join(f"{p}({'rebuy' if is_rebuy(g) else '普通'})" for p, g, _ in t["open"]) or "无"
    return f"{name} 本期：{part}；当前持仓：{op}；累计 {t['all_n']} 笔 {t['all_pnl']:+.2f} USDT"


def build_report(c: dict, hs_set: int) -> str:
    h, alerts, notes = c["h"], c["alerts"], c["notes"]
    ts = now_utc().astimezone(BJT).strftime("%Y-%m-%d %H:%M")
    ok = "⚠️" if any(k.startswith("health:") for k, _, _ in alerts) else "✅"
    hb = f"心跳 {h['nfi_hb_min']:.0f} 分钟前" if h["nfi_hb_min"] is not None else "找不到心跳"
    health_line = (f"{ok} 健康：X7Safe {h['nfi_active']}（PID {h['nfi_pid']}，{hb}）；"
                   f"Combined_V3 {'运行中' if h['v3_running'] == 'true' else '未运行'}；内存可用 {h['mem_avail_mb']} MB，磁盘 {h['disk_pct']}%")
    if h["nfi_ws"] or h["v3_ws"]:
        health_line += f"；近期日志里行情连接报错 {h['nfi_ws'] + h['v3_ws']} 次（会自动改用 REST，常见，不用管）"
    n25_closed = c["n25"]["closed"]
    n25_rows = [r[3] or 0 for r in n25_closed]
    n25_rebuy = sum(1 for r in n25_closed if is_rebuy(r[2]))
    lines = [
        f"【交易机器人 3 日报】{ts}（北京时间）",
        health_line,
        "📈 " + fmt_trades("X7Safe", c["nfi"]),
        "📈 " + fmt_trades("Combined_V3", c["v3"]),
        f"📊 N25 新规则累计（{N25_SINCE} UTC 后开仓、已平仓）：{len(n25_rows)} 笔（普通 {len(n25_rows) - n25_rebuy}、rebuy {n25_rebuy}），"
        f"{sum(n25_rows):+.2f} USDT，盈亏比 {pf(n25_rows)}",
    ]
    normal = [s for s in c["stops"] if not is_rebuy(s[2])]
    bad = [s for s in normal if s[6] is not None and s[6] > 0.8]
    missing = [s for s in normal if s[6] is None]
    if not normal:
        lines.append(f"🔍 N25 止损检查：新规则下还没有普通交易（HARD-STOP-SET 日志 {hs_set} 条）")
    else:
        verdict = ("⚠️ 止损不在 ×0.75：" + "、".join(f"{s[1]} ×{s[6]}" for s in bad)) if bad else "交易所止损都挂在首仓价 ×0.75 ✅"
        if missing:
            verdict += "；没找到交易所止损单：" + "、".join(s[1] for s in missing)
        lines.append(f"🔍 N25 止损检查：新规则下普通交易 {len(normal)} 笔（持仓中 {sum(1 for s in normal if s[3])}），"
                     f"HARD-STOP-SET 日志 {hs_set} 条；{verdict}")
    if notes:
        lines.append("ℹ️ 提示：" + "；".join(t for _, t, _ in notes))
    lines.append("⚠️ 异常：" + ("；".join(t for _, t, _ in alerts) if alerts else "无"))
    lines.append("👉 " + ("需要看一下，可以把这条消息转给 Claude 处理" if alerts or bad else "无需操作"))
    return "\n".join(lines)


def alert_since(state: dict) -> datetime:
    last = state.get("last_alert_utc")
    return datetime.fromisoformat(last) - EVENT_OVERLAP if last else now_utc() - timedelta(minutes=15)


def alert_message(state: dict, c: dict, now: datetime) -> tuple:
    """(Telegram text, or "" if nothing is due; updated alerts_sent)."""
    sent = dict(state.get("alerts_sent", {}))

    def due(key: str, repeat: bool) -> bool:
        return key not in sent or (repeat and now - datetime.fromisoformat(sent[key]) > ALERT_REPEAT)

    fresh = [(k, t) for k, t, r in c["alerts"] if due(k, r)]
    info = [(k, t) for k, t, r in c["notes"] if due(k, r)]
    parts = []
    if fresh:
        parts.append("🚨 交易机器人告警\n" + "\n".join(f"• {t}" for _, t in fresh)
                     + "\n👉 需要看一下，可以把这条消息转给 Claude 处理（问题一直没消失的话，每 6 小时提醒一次）")
    if info:
        parts.append("ℹ️ 交易机器人提示\n" + "\n".join(f"• {t}" for _, t in info) + "\n👉 按策略规则发生的，无需操作")
    for k, _ in fresh + info:
        sent[k] = now.isoformat()
    return "\n\n".join(parts), sent


# --------------------------------------------------------------------------- main
def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "dry"
    force = "--force" in sys.argv
    state = load_state()
    if mode == "test":
        send(f"✅ tg_monitor 测试消息（{now_utc().astimezone(BJT):%Y-%m-%d %H:%M} 北京时间）。以后每 3 天推送一次状态，有异常会另外提醒。")
        return 0
    if mode == "dry":
        print(build_report(collect(state), hard_stop_set_lines()))
        text, _ = alert_message(state, collect(state, alert_since(state)), now_utc())
        print("\n--- alert 模式现在会发：\n" + (text or "（无）"))
        return 0
    if mode == "report":
        last = state.get("last_report_utc")
        if not force and last and now_utc() - datetime.fromisoformat(last) < REPORT_EVERY - timedelta(hours=1):
            return 0
        send(build_report(collect(state), hard_stop_set_lines()))
        state["last_report_utc"] = now_utc().isoformat()
        save_state(state)
        return 0
    if mode == "alert":
        started = now_utc()
        text, sent = alert_message(state, collect(state, alert_since(state)), started)
        if text:
            send(text)
        state["alerts_sent"] = {k: v for k, v in sent.items() if started - datetime.fromisoformat(v) < SENT_MEMORY}
        state["last_alert_utc"] = started.isoformat()
        save_state(state)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
