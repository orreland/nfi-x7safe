# 部署 dry-run 到云服务器

目标机器：Public IP `<你的服务器公网IP>`（假定 Ubuntu 22.04/24.04；如果不是，`server_setup.sh` 里的包管理器命令要换）。

**密码/密钥全程只在你自己的终端里输入，不要发给我，我也不会替你登录。**

---

## 0. 先在服务器上做两件安全的事（比部署本身更重要）

云服务器公网 IP 直接暴露，下面两件事不做，dry-run 还没启动风险就已经先来了：

1. **改掉你刚才发我的密码**，并改用 SSH 密钥登录，禁用密码登录：
   ```bash
   ssh-keygen -t ed25519          # 在你本机执行，不是服务器
   ssh-copy-id root@<你的服务器公网IP>
   # 登录服务器后：
   sudo sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
   sudo systemctl restart sshd
   ```
2. **防火墙**：dry-run 不需要对公网开放任何端口。只留 SSH：
   ```bash
   ufw allow OpenSSH
   ufw enable
   ```

`configs/exampleconfig_secret.json` 里 `api_server.listen_ip_address` 现在是 `0.0.0.0`，`username`/`password` 是空的——这个组合如果真开了 API server 且防火墙没挡住，等于任何人都能通过公网 IP:8080 操作你的 bot（下单、改配置）。两条路二选一：

- **简单**：把 `api_server.enabled` 设为 `false`（dry-run 不需要 FreqUI 也能跑，看日志/Telegram 就够）。
- **要用 FreqUI**：`listen_ip_address` 改成 `127.0.0.1`，设置真实的 `username`/`password` 和随机的 `jwt_secret_key`（不要用配置里那个占位符），然后本地用 SSH 隧道访问：
  ```bash
  ssh -L 8080:127.0.0.1:8080 root@<你的服务器公网IP>
  # 之后浏览器打开 http://127.0.0.1:8080
  ```

我不会帮你改这两个值——`exampleconfig_secret.json` 顾名思义是要填真实密钥的文件，理应只由你在服务器上编辑，不经过我或聊天记录。

---

## 1. 服务器基础环境

把 `scripts/deploy/server_setup.sh` 传到服务器（用你自己的终端）：

```bash
scp scripts/deploy/server_setup.sh root@<你的服务器公网IP>:/root/
ssh root@<你的服务器公网IP> "bash /root/server_setup.sh"
```

这一步装 Python 3.12、freqtrade 2026.7（和你本地验证过的版本一致）、拉取上游策略仓库到 `/opt/nfi/nfi_repo`。

---

## 2. 同步你本地的修改（这一步不能跳，upstream 仓库里没有你的修复）

以下文件只存在于你本机 `D:\NostalgiaForInfinity\`，服务器上没有，必须手动同步：

| 本地路径 | 服务器路径 | 内容 |
|---|---|---|
| `user_data/strategies/NostalgiaForInfinityX7.py` | `/opt/nfi/user_data/strategies/` | 已验证与 `nfi_repo` 一致的基类副本 |
| `user_data/strategies/NostalgiaForInfinityX7Safe.py` | `/opt/nfi/user_data/strategies/` | 止损修复 + 百分比仓位 |
| `configs/local-overrides-safe.json` | `/opt/nfi/configs/` | 槽位数、tradable_balance_ratio |
| `configs/local-overrides-dryrun.json` | `/opt/nfi/configs/` | dry_run 强制 true、stoploss_on_exchange |
| `configs/blacklist-binance.json` | `/opt/nfi/configs/` | 真实黑名单——**不要传 `blacklist-survivorship-test.json`** |
| `configs/exampleconfig.json` `exampleconfig_secret.json` `trading_mode-spot.json` `pairlist-backtest-static-binance-spot-usdt.json` | `/opt/nfi/configs/` | 基础配置 |
| `scripts/preflight.py` `scripts/nfi_backtest_lib.py` | `/opt/nfi/scripts/` | 启动前检查、周度对账要用 |

一次性传（在本机 Git Bash 里跑，`scp` 会自己提示你输密码或用密钥）：

```bash
cd /d/NostalgiaForInfinity
scp user_data/strategies/NostalgiaForInfinityX7.py \
    user_data/strategies/NostalgiaForInfinityX7Safe.py \
    root@<你的服务器公网IP>:/opt/nfi/user_data/strategies/

scp configs/local-overrides-safe.json configs/local-overrides-dryrun.json \
    configs/blacklist-binance.json configs/exampleconfig.json \
    configs/trading_mode-spot.json configs/pairlist-backtest-static-binance-spot-usdt.json \
    root@<你的服务器公网IP>:/opt/nfi/configs/

scp scripts/preflight.py scripts/nfi_backtest_lib.py \
    root@<你的服务器公网IP>:/opt/nfi/scripts/
```

传完之后**必须在服务器上编辑 `configs/exampleconfig_secret.json`**：填交易所 API key（建议先用只读/无提现权限的 key 起步，dry-run 阶段甚至可以留空 key，因为 dry-run 不实际下单）、按上面第 0 步处理 `api_server` 那几行。

---

## 3. 启动前检查（服务器上跑，和本机一样）

```bash
ssh root@<你的服务器公网IP>
cd /opt/nfi
.venv/bin/python scripts/preflight.py --wallet <你计划投入的本金>
```

0 阻断才继续。

---

## 4. 常驻启动

用 `systemd`（比 `nohup`/`tmux` 更稳，服务器重启能自动拉起）：

```bash
scp scripts/deploy/nfi-dryrun.service root@<你的服务器公网IP>:/etc/systemd/system/
ssh root@<你的服务器公网IP> <<'EOF'
useradd -r -s /usr/sbin/nologin nfi || true
chown -R nfi:nfi /opt/nfi/user_data
systemctl daemon-reload
systemctl enable --now nfi-dryrun
systemctl status nfi-dryrun --no-pager
journalctl -u nfi-dryrun -f
EOF
```

---

## 5. 之后怎么看

- 日志：`journalctl -u nfi-dryrun -f` 或 `/opt/nfi/user_data/logs/dryrun.log`
- 每周对账：把 dry-run 产生的成交记录拉回本机（或直接在服务器上跑），用 `nfi_backtest_lib.compute_daily_metrics()` 重建真实盯市回撤，别只看 freqtrade 自带的已实现口径——这是本项目吃过两次亏的教训（见 `reports/SAFE_ONLY.md` 度量口径更正记录）。
- 想停：`systemctl stop nfi-dryrun`。想改配置：改完 `configs/` 里的文件后 `systemctl restart nfi-dryrun`。

需要的话我可以再写一个"周度对账"脚本，自动从服务器拉 `user_data/logs`/成交数据库回本机、跑重建、追加到 `reports/`。
