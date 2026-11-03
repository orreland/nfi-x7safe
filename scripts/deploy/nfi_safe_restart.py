#!/usr/bin/env python3
"""Restart nfi-dryrun.service only if it has no open position right now.

needrestart used to bounce this service unpredictably whenever an unattended
security upgrade touched a library it had loaded (see
/etc/needrestart/conf.d/nfi-dryrun.conf, which now blocks that). This script
replaces that with a controlled weekly restart (see nfi-dryrun-restart.timer)
that skips the bounce while a trade is open, so library patches still get
picked up without cutting an open position's monitoring window.
"""

import sqlite3
import subprocess
import sys

DB_PATH = "/opt/nfi/user_data/tradesv3.dryrun.sqlite"


def open_trade_count() -> int:
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM trades WHERE is_open=1")
        return cur.fetchone()[0]
    finally:
        con.close()


def main() -> int:
    try:
        open_count = open_trade_count()
    except sqlite3.Error as exc:
        print(f"nfi_safe_restart: could not read {DB_PATH}: {exc} - skipping restart this cycle")
        return 0

    if open_count > 0:
        print(f"nfi_safe_restart: {open_count} open trade(s) - skipping restart, will retry next cycle")
        return 0

    print("nfi_safe_restart: no open trades - restarting nfi-dryrun.service")
    return subprocess.call(["systemctl", "restart", "nfi-dryrun.service"])


if __name__ == "__main__":
    sys.exit(main())
