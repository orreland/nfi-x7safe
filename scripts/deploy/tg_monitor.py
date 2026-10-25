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
    tg_monitor.py alert           send only new anomalies (deduplicated, 6 h)
    tg_monitor.py test            send a one-line test message
    tg_monitor.py dry             print the summary and alerts, send nothing

Plan and thresholds: reports/MONITORING_PLAN.md in the project repo.
"""

import json
import os
import sqlite3
import subprocess
import sys
import time
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
REPORT_EVERY = timedelta(days=3)
ALERT_REPEAT = timedelta(hours=6)
KNOWN_NOISE = ("Task was destroyed but it is pending",)
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
def last_heartbeat_age(log_text: str):
    for line in reversed(log_text.splitlines()):
        if "Bot heartbeat" in line:
            try:
                ts = datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                return (now_utc() - ts).total_seconds() / 60
            except ValueError:
                return None
    return None


def new_error_types(log_text: str, since: datetime) -> list:
    seen = {}
    for line in log_text.splitlines():
        if (" - ERROR - " in line or " - CRITICAL - " in line or "Traceback" in line) and not any(n in line for n in KNOWN_NOISE):
            try:
                ts = datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if ts >= since:
                key = line[26:].split(" - ", 2)[-1][:80]
                seen[key] = seen.get(key, 0) + 1
    return [f"{n}× {k}" for k, n in seen.items()]


def health(since: datetime) -> dict:
    nfi_log = sh(f"tail -n 4000 {NFI_LOG}")
    v3_log = sh(f"tail -n 4000 {V3_LOG}")
    mem = {k: int(v.split()[0]) for k, v in (ln.split(":", 1) for ln in open("/proc/meminfo")) if k in ("MemAvailable", "MemTotal")}
    return {
        "nfi_active": sh("systemctl is-active nfi-dryrun"),
        "nfi_pid": sh("systemctl show nfi-dryrun -p MainPID --value"),
        "nfi_since": sh("systemctl show nfi-dryrun -p ActiveEnterTimestamp --value"),
        "nfi_nrestarts": sh("systemctl show nfi-dryrun -p NRestarts --value"),
        "nfi_hb_min": last_heartbeat_age(nfi_log),
        "nfi_errors": new_error_types(nfi_log, since),
        "v3_running": sh("docker inspect -f '{{.State.Running}}' combined_v3_dryrun"),
        "v3_restarts": sh("docker inspect -f '{{.RestartCount}}' combined_v3_dryrun"),
        "v3_hb_min": last_heartbeat_age(v3_log),
        "v3_errors": new_error_types(v3_log, since),
        "mem_avail_mb": mem.get("MemAvailable", 0) // 1024,
        "disk_pct": int((sh("df --output=pcent / | tail -1").strip().rstrip("%") or "0")),
    }


def trades(path: str, since: str) -> dict:
    c = db(path)
    closed = c.execute(
        "select pair, trim(enter_tag), close_profit_abs, close_profit, exit_reason from trades where is_open=0 and close_date>=?",
        (since,),
    ).fetchall()
    allc = c.execute("select count(*), coalesce(sum(close_profit_abs),0) from trades where is_open=0").fetchone()
    opn = c.execute("select pair, trim(enter_tag), stake_amount from trades where is_open=1").fetchall()
    return {"closed": closed, "all_n": allc[0], "all_pnl": allc[1], "open": opn}


def n25_stop_check() -> list:
    """For open non-rebuy NFI trades: DB stop / first entry and exchange stop / first entry."""
    c = db(NFI_DB)
    first = ("(select coalesce(o2.average,o2.price) from orders o2 where o2.ft_trade_id=t.id "
             "and o2.ft_order_side='buy' and o2.status='closed' order by o2.id limit 1)")
    q = (f"select t.pair, trim(t.enter_tag), t.open_date, round(t.stop_loss/{first},3), "
         f"(select round(o.stop_price/{first},3) from orders o where o.ft_trade_id=t.id and o.ft_order_side='stoploss' "
         f"and o.status='open' order by o.id desc limit 1) from trades t where t.is_open=1")
    return [r for r in c.execute(q).fetchall()]


def collect(state: dict) -> tuple:
    last = state.get("last_report_utc")
    since_dt = datetime.fromisoformat(last) if last else now_utc() - REPORT_EVERY
    since = since_dt.strftime("%Y-%m-%d %H:%M:%S")
    h = health(since_dt)
    nfi = trades(NFI_DB, since)
    v3 = trades(V3_DB, since)
    n25 = trades(NFI_DB, N25_SINCE)
    stops = n25_stop_check()
    hs_set = int(sh(f"grep -c 'HARD-STOP-SET' {NFI_LOG}") or 0)

    alerts = []
    if h["nfi_active"] != "active":
        alerts.append(f"X7Safe 服务状态是 {h['nfi_active']}（不是 active）")
    if h["nfi_hb_min"] is None or h["nfi_hb_min"] > 10:
        alerts.append(f"X7Safe 心跳 {h['nfi_hb_min'] if h['nfi_hb_min'] is not None else '找不到'} 分钟未更新")
    if h["v3_running"] != "true":
        alerts.append("Combined_V3 容器没有在运行")
    if h["v3_hb_min"] is None or h["v3_hb_min"] > 10:
        alerts.append(f"Combined_V3 心跳 {h['v3_hb_min'] if h['v3_hb_min'] is not None else '找不到'} 分钟未更新")
    for e in h["nfi_errors"]:
        alerts.append(f"X7Safe 新报错：{e}")
    for e in h["v3_errors"]:
        alerts.append(f"Combined_V3 新报错：{e}")
    if h["mem_avail_mb"] < 200:
        alerts.append(f"服务器可用内存只剩 {h['mem_avail_mb']} MB")
    if h["disk_pct"] > 85:
        alerts.append(f"服务器磁盘已用 {h['disk_pct']}%")
    for name, t in (("X7Safe", nfi), ("Combined_V3", v3)):
        for pair, tag, pnl, ratio, reason in t["closed"]:
            if pnl is not None and pnl < -100:
                alerts.append(f"{name} 单笔亏损 {pnl:.2f} USDT（{pair}，{reason}）")
    nfi_3d = sum(r[2] or 0 for r in nfi["closed"])
    if nfi_3d < -0.02 * NFI_WALLET:
        alerts.append(f"X7Safe 本期合计亏损 {nfi_3d:.2f} USDT（超过 2%）")
    for pair, tag, opened, db_ratio, ex_ratio in stops:
        if not is_rebuy(tag) and opened >= N25_SINCE and ex_ratio is not None and ex_ratio > 0.8:
            alerts.append(f"N25 可能没生效：{pair}（普通交易）交易所止损在首仓价 ×{ex_ratio}（应为 ×0.75）")
    return h, nfi, v3, n25, stops, hs_set, alerts


def fmt_trades(name: str, t: dict) -> str:
    rows = [r[2] or 0 for r in t["closed"]]
    if not rows:
        part = "无新平仓"
    else:
        wins = sum(1 for r in rows if r > 0)
        part = f"{len(rows)} 笔，{sum(rows):+.2f} USDT（{wins} 胜 {len(rows) - wins} 负），最大单笔亏损 {min(rows):+.2f}"
    op = "、".join(f"{p}({'rebuy' if is_rebuy(g) else '普通'})" for p, g, _ in t["open"]) or "无"
    return f"{name} 本期：{part}；当前持仓：{op}；累计 {t['all_n']} 笔 {t['all_pnl']:+.2f} USDT"


def build_report(h, nfi, v3, n25, stops, hs_set, alerts) -> str:
    ts = now_utc().astimezone(BJT).strftime("%Y-%m-%d %H:%M")
    ok = "✅" if not alerts else "⚠️"
    n25_rows = [r[2] or 0 for r in n25["closed"]]
    lines = [
        f"【交易机器人 3 日报】{ts}（北京时间）",
        f"{ok} 健康：X7Safe {h['nfi_active']}（PID {h['nfi_pid']}，心跳 {h['nfi_hb_min']:.0f} 分钟前）；"
        f"Combined_V3 {'运行中' if h['v3_running'] == 'true' else '未运行'}；内存可用 {h['mem_avail_mb']} MB，磁盘 {h['disk_pct']}%"
        if h["nfi_hb_min"] is not None else f"{ok} 健康：X7Safe {h['nfi_active']}（找不到心跳）",
        "📈 " + fmt_trades("X7Safe", nfi),
        "📈 " + fmt_trades("Combined_V3", v3),
        f"📊 N25 新规则累计（{N25_SINCE} UTC 起）：{len(n25_rows)} 笔，{sum(n25_rows):+.2f} USDT，盈亏比 {pf(n25_rows)}",
    ]
    non_rebuy = [s for s in stops if not is_rebuy(s[1]) and s[2] >= N25_SINCE]
    if non_rebuy:
        lines.append("🔍 N25 止损检查：" + "；".join(f"{p} 交易所止损 ×{ex}" for p, _, _, _, ex in non_rebuy))
    else:
        lines.append(f"🔍 N25 止损检查：当前没有新规则下的普通交易持仓（HARD-STOP-SET 日志累计 {hs_set} 条）")
    lines.append("⚠️ 异常：" + ("；".join(alerts) if alerts else "无"))
    lines.append("👉 " + ("需要看一下，可以把这条消息转给 Claude 处理" if alerts else "无需操作"))
    return "\n".join(lines)


# --------------------------------------------------------------------------- main
def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "dry"
    force = "--force" in sys.argv
    state = load_state()
    if mode == "test":
        send(f"✅ tg_monitor 测试消息（{now_utc().astimezone(BJT):%Y-%m-%d %H:%M} 北京时间）。以后每 3 天推送一次状态，有异常会另外提醒。")
        return 0
    h, nfi, v3, n25, stops, hs_set, alerts = collect(state)
    if mode == "dry":
        print(build_report(h, nfi, v3, n25, stops, hs_set, alerts))
        return 0
    if mode == "report":
        last = state.get("last_report_utc")
        if not force and last and now_utc() - datetime.fromisoformat(last) < REPORT_EVERY - timedelta(hours=1):
            return 0
        send(build_report(h, nfi, v3, n25, stops, hs_set, alerts))
        state["last_report_utc"] = now_utc().isoformat()
        save_state(state)
        return 0
    if mode == "alert":
        sent = state.get("alerts_sent", {})
        fresh = [a for a in alerts if a not in sent or now_utc() - datetime.fromisoformat(sent[a]) > ALERT_REPEAT]
        if fresh:
            send("🚨 交易机器人告警\n" + "\n".join(f"• {a}" for a in fresh) + "\n（同一条告警 6 小时内不重复发）")
            for a in fresh:
                sent[a] = now_utc().isoformat()
            state["alerts_sent"] = {k: v for k, v in sent.items() if now_utc() - datetime.fromisoformat(v) < timedelta(days=2)}
            save_state(state)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
