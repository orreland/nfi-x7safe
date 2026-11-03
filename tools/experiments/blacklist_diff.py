"""Which pairs of our static universe would the upstream blacklist add / remove vs ours?"""
import json
import re

ROOT = r"D:\NostalgiaForInfinity"
SP = r"<用户目录>\AppData\Local\Temp\claude\D--NostalgiaForInfinity\2608f246-06da-4924-88ea-ebe2d0b59a5f\scratchpad"


def load(path):
    txt = open(path, encoding="utf-8").read()
    txt = re.sub(r"^\s*//.*$", "", txt, flags=re.M)
    return json.loads(txt)


def blacklist(cfg):
    return cfg["exchange"]["pair_blacklist"]


ours = blacklist(load(rf"{ROOT}\configs\blacklist-binance.json"))
up = blacklist(load(rf"{SP}\blacklist_upstream.json"))
universe = load(rf"{ROOT}\configs\pairlist-backtest-static-binance-spot-usdt.json")["exchange"]["pair_whitelist"]


def blocked(patterns, pair):
    return any(re.fullmatch(p, pair) for p in patterns)


print("patterns: ours", len(ours), "upstream", len(up))
print("new upstream patterns:", [p for p in up if p not in ours])
print("removed upstream patterns:", [p for p in ours if p not in up])
newly = [p for p in universe if blocked(up, p) and not blocked(ours, p)]
unblocked = [p for p in universe if blocked(ours, p) and not blocked(up, p)]
print("universe pairs newly blacklisted by upstream:", newly)
print("universe pairs un-blacklisted by upstream:", unblocked)
