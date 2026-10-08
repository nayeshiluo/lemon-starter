# Hermes Agent 开源安装套件

全新安装用脚本、112 个技能的公开模板和 Hermes Web UI。私人配置、会话、数据库及恢复密钥须另行加密备份，公开套件不能替代它们。

## 安装前审核

只在全新 Ubuntu / Debian 上安装，使用专用普通用户配合 sudo，拒绝让 Agent 以 root 身份运行。脚本会拒绝已有配置、Web UI 数据、服务与覆盖配置，以及相关符号链接。推荐先在一次性隔离主机上使用测试凭据。

先克隆仓库，选择并审核一个完整提交，包括 `install.sh`、`tools/public_skills_guard.py`、`tools/bootstrap_webui.py`、`tools/sync_telegram_menu.py` 以及技能包内容。审核之后固定该提交，不要把“选择最新提交”当作审核。

```bash
git clone https://github.com/nayeshiluo/lemon-starter.git
cd lemon-starter
git checkout <已审核的完整提交SHA>
```

NodeSource 与 Hermes 官方安装器仍属于第三方代码。先下载、阅读，再记录自己审核版本的 SHA-256；也可使用可信维护者另行提供的摘要。对同一次下载自动计算摘要再自动执行，只能证明一致性，不能证明可信。

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh -o /tmp/hermes-official.review.sh
curl -fsSL https://deb.nodesource.com/setup_24.x -o /tmp/nodesource.review.sh
# 阅读两个脚本及其后续下载/执行行为后，记录审核摘要：
sha256sum /tmp/hermes-official.review.sh /tmp/nodesource.review.sh
```

将上一步的审核摘要填入下面命令；已有 Node.js >=24 时无需 NodeSource 摘要。脚本缺少固定提交或必要摘要就会在系统修改前停止；上游内容变化时停止，须重新审核。

```bash
export HERMES_INSTALLER_SHA256='<已审核Hermes安装器的64位SHA256>'
export NODESOURCE_SETUP_SHA256='<已审核NodeSource脚本的64位SHA256>'
STARTER_REVISION="$(git rev-parse HEAD)" bash install.sh
```

仓库资源由固定提交的本地 Git 对象读取，安装器自身必须与指定提交完全一致；不会回退最新 main，也不会在运行时重新下载仓库 Python 后执行。运行需预先具备 git、curl、python3、sha256sum；由 git clone 准备代码的主机通常已经具备 git。

**信任边界：** 包、清单、扫描器来自同一审核快照，摘要和扫描是完整性及已知风险检查，不是独立签名或无后门证明。第三方安装器的后续下载、软件仓库内容和 npm 传递依赖仍未全部固定。Web UI 固定 `0.6.44`，npm 明确允许 agent-browser、node-pty、protobufjs、vue-demi 四个包的安装脚本以支持实际构建；这些脚本及后续网络行为仍需信任上游。本项目没有声称实现完全可复现的依赖供应链。

## 配置与权限

向导需要模型名称、兼容 API Base URL 和 Key。Telegram 可跳过；填写 Bot Token 后必须填写自己的正整数管理员 ID。配置值不允许换行。无人值守可设 `MODEL_NAME`、`BASE_URL`、`API_KEY`、`TELEGRAM_BOT_TOKEN`、`TELEGRAM_ADMIN_ID`；无可用终端时可选项使用默认值，缺少 API Key 明确失败。不要把真实密钥写进公开日志或 shell 历史。

模型 Key 仅写入权限 600 的 `config.yaml`，保留 Hermes 自定义端点实际支持的 `model.api_key`，不再同时复制到 `.env` 的 CUSTOM/OPENAI 两个字段。Telegram 与本机 API 凭据写在权限 600 的 `.env`。两个服务设置 `UMask=0077`、`NoNewPrivileges=true`；Agent 从服务内执行 sudo 等提权会被拒绝，需由人类在 SSH 终端单独完成系统管理。

私聊和群聊的普通用户命令均仅 `help,whoami`。模型切换、重置、终止、总结仍由管理员授权逻辑控制；完整菜单只注册到指定所有者的私聊，普通群菜单只列两个查询命令。菜单可见性本身不授予权限。Telegram 中非命令消息的授权仍取决于 Hermes 网关版本和配置，必须另做实际集成验证。

技能、网页和群消息均是可能含不可信指令的输入。提示词、普通用户身份及 NoNewPrivileges 无法隔离该用户可读写的所有数据；应让专用服务用户没有其他业务秘密，不授予它额外管理权限。技能包安装只写文件，不自动执行技能脚本。

## Web UI 和本机 API

Web UI 显式监听 `127.0.0.1:8648`；Hermes API 在配置、环境及服务中显式固定 `127.0.0.1:8642`，无需开放这些公网端口。CORS 仅允许本机面板来源。

Web UI 首次启动用本机 API 将初始账号改为随机强密码并验证登录。初始化工具禁用环境代理、拒绝重定向，只接受数值回环地址，防止凭据被转发。随机密码先保存为 600 并落盘；失败后复用已有密码，不覆盖或丢弃。初始化失败停止面板，保留现场，不报安装成功。

账号为 `admin`，初始随机密码保存在 `~/.hermes/webui-initial-login.json`；通过自己的 SSH 终端读取，不转发。用 SSH 通道访问：

```bash
ssh -L 8648:127.0.0.1:8648 用户名@服务器地址
```

iPhone / iPad 可用支持本地转发的 SSH 客户端建立本地 8648 → 服务器 `127.0.0.1:8648`，保持连接后由 Safari 访问。需要域名访问时另行配置 HTTPS、鉴权和访问限制。

安装结束检查服务状态，但进程存活不等于模型调用、Telegram 收发已验收。安装后必须检查实际监听和功能：

```bash
ss -tlnp | grep -E ':(8642|8648)\b'
hermes doctor
```

确认没有 `0.0.0.0` / `[::]` 监听，验证面板新密码、实际模型调用、自己的 Telegram 私聊，以及普通群成员无法执行 model/clear/stop/summary。不要在有生产配置的主机上运行安装器做这种测试。

## 失败恢复

脚本不允许用重跑覆盖既有实例。菜单同步移到核心服务初始化之后；失败明确显示 `FAILED` 并写入 `~/.hermes/starter-tools/telegram-menu-status`，不会阻止核心服务注册。以服务用户重试菜单即可，不需要删除配置：

```bash
python3 ~/.hermes/starter-tools/sync_telegram_menu.py --env-file ~/.hermes/.env
```

面板初始化失败后，以服务用户运行保留的初始化工具；面板仅回环监听，可先启动，初始化失败必须再次停止：

```bash
sudo systemctl start hermes-web-ui
if ! python3 ~/.hermes/starter-tools/bootstrap_webui.py --credentials ~/.hermes/webui-initial-login.json; then
  sudo systemctl stop hermes-web-ui
fi
```

其余安装失败保留 700 临时目录和已有配置，依据具体阶段诊断、备份后恢复；没有任意阶段自动续装或自动清理功能。初始化工具只适用于本次安装产生的凭据，不重置既有面板账号。

## 公开快照、检查与恢复边界

`skills_bundle.manifest.json` 记录审核公开文件摘要，`SHA256SUMS` 记录包摘要。112 是技能数量，不等于全部技能、外部 API 或依赖已经功能验收。

生产端另有受保护审批清单，未知文件、未审核变更、敏感格式、路径异常或扫描错误会阻止发布；候选仍由所有者确认。更新安装器时也需协调远端提交和仓库文件基线。私人全量同步暂停状态不得由公开安装器改变。

```bash
python3 -m unittest discover -s tests -v
python3 tools/public_skills_guard.py skills_bundle.tar.gz skills_bundle.manifest.json
```

曾发现的公开凭据须按泄露处理。清理当前文件、重写可见分支无法撤回第三方副本或 GitHub 缓存；凭据轮换和全历史处理仍须分别验证，不能因这轮安装器修复宣称旧风险全部消除。

低于 1500 MB 内存且未自定义 NODE_OPTIONS 时，Node 构建堆上限设为 512 MB；自定义设置不覆盖。公共 npm 程序以 022 掩码安装，秘密配置保持 600。既有实例升级、数据库迁移、模型接入与私人灾难恢复须另行备份和验收。
