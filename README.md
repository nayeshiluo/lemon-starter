# Hermes Agent 开源安装套件

包含安装脚本、112 个技能的公开模板和 Hermes Web UI。公开套件用于全新安装；完整生产配置、密钥、会话和数据库需要独立的加密备份。

2026-10-04 安全更新：技能包已移除本轮发现的实际部署凭证；历史可见分支已脱敏重写。旧代理密钥已轮换。历史重写无法撤回他人已下载的内容或 GitHub 缓存，发现过的秘密应按已泄露处理。

## 安装

仅在全新 Ubuntu / Debian 主机上使用，推荐普通用户配合 sudo。已有 `.env`、`config.yaml`、Web UI 数据、网关/面板服务或其 systemd 覆盖配置时，脚本会停止；相关路径为符号链接时也会停止，避免覆盖现有配置。

```bash
git clone https://github.com/nayeshiluo/lemon-starter.git
cd lemon-starter
STARTER_REVISION="$(git rev-parse HEAD)" bash install.sh
```

先阅读下载的脚本。安装所用技能包、清单和校验代码全部从这个固定提交获取，Web UI 固定为 `0.6.44`，其声明要求 Node.js `>=23`；套件为较旧环境安装 Node.js 24.x。技能解包前核对文件清单、内容摘要、凭证格式及路径安全。Node.js 与 Hermes 官方安装器仍是外部依赖，应按其发布流程评估；此套件不代表对第三方依赖的全面安全认证。

向导需要模型名称、兼容 API Base URL 和 Key。Telegram 可跳过；填写 Bot Token 后必须填写自己的正整数管理员 ID，留空或格式错误会在写入配置前停止。配置值不允许换行，秘密不作为 Python 命令行参数传递。

无人值守安装可预设 `MODEL_NAME`、`BASE_URL`、`API_KEY`、`TELEGRAM_BOT_TOKEN`、`TELEGRAM_ADMIN_ID`。不要把实际密钥提交到仓库或公开安装日志。

## Web UI 安全访问

面板只监听 `127.0.0.1:8648`，无需在云安全组开放公网 8648。首次启动通过本机 API 将初始账号改为随机强密码，并验证新密码登录。初始化失败会停止面板并明确报错。

Hermes 网关统一由 systemd 启动和管理，即使跳过 Telegram 也会启动，并在安装结束时检查状态。Web UI 的开机启动会同时请求启动网关；Telegram 是可选通信渠道。

账号为 `admin`。初始随机密码保存在 `~/.hermes/webui-initial-login.json`，权限 600；请通过自己的 SSH 终端读取，不要转发此文件。

在电脑建立 SSH 通道后访问 `http://127.0.0.1:8648`：

```bash
ssh -L 8648:127.0.0.1:8648 用户名@服务器地址
```

iPhone / iPad 使用支持本地端口转发的 SSH 客户端，配置本地 8648 → 服务器 `127.0.0.1:8648`，保持连接后用 Safari 访问本机地址。需要域名访问时，另行配置 HTTPS、鉴权与访问限制；不要直接改为默认弱密码的公网 HTTP 面板。

## 公开技能快照与自动检查

`skills_bundle.manifest.json` 列出已审核公开文件的内容摘要；`SHA256SUMS` 提供包摘要。112 是技能数量，不等于全部技能、外部 API 或依赖已经功能验收。

发布端使用私有审批清单：源文件和公开输出必须同时与已审核摘要一致。新增、删除、修改技能，未知文件、私钥、会话文件、嵌套压缩包、无法解码的文件或扫描错误都会阻止任务。日志仅输出位置与类型，不输出秘密原文。未审内容不自动进入公开仓库；需要复审后更新快照及私有审批清单。

正常每日任务会核对源树、公开包和远端提交；没有变化时复用同一个已审核快照，不制造仅时间戳变化的重复发布。生产技能、模型路由和运行中的机器人不受此公开导出策略改变。

安全回归测试：

```bash
python3 -m unittest discover -s tests -v
python3 tools/public_skills_guard.py skills_bundle.tar.gz skills_bundle.manifest.json
```

## 运维与恢复

- `hermes doctor` 检查 Hermes。
- `sudo systemctl status hermes-web-ui` 查看面板；`journalctl -u hermes-web-ui` 查看服务日志。
- 安装器不负责覆盖升级既有实例；先备份配置、数据库和服务，再单独规划迁移。
- 安全历史重写后，旧克隆应重新克隆，避免把旧的敏感历史推回。生产部署与私人备份不应从公开技能包恢复秘密。
