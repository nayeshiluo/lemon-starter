# 🤖 Hermes Agent 自动化一键安装套件 (含 Web UI 网页管理面板)

本套件提供 Hermes Agent 的自动化一键安装脚本、完整技能树（Skills）以及 **Web UI 网页控制台（端口 8648）**。支持自定义任何 OpenAI 兼容的模型 URL 端点与 API Key，并可快速绑定 Telegram Bot。

---

## 🚀 极速一键安装指令

在任何全新的 Ubuntu / Debian 服务器上，只需复制粘贴并执行下面一行命令：

```bash
curl -fsSL https://raw.githubusercontent.com/nayeshiluo/lemon-starter/main/install.sh | bash
```

或者使用 `bash <(...)` 执行：

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/nayeshiluo/lemon-starter/main/install.sh)
```

---

## 🌐 Web UI 网页管理面板

安装脚本会自动部署并启动 **Hermes Web UI** 控制台：

- **面板地址**：`http://<你的服务器IP>:8648`
- **默认管理员账号**：`admin`
- **默认管理员密码**：`123456` *(首次登录后请在后台安全设置中修改)*
- **功能特性**：网页端实时多轮对话、技能市场与配置管理、会话历史树、模型网关状态监控等。

> ⚠️ **注意**：如果使用的是云服务器（如 AWS、阿里云、腾讯云等），请在云控制台的安全组规则中**放行入站 TCP 8648 端口**。

---

## 🛠️ 安装过程交互说明

运行安装脚本后，终端会自动进入配置向导：

1. **模型名称**（如 `deepseek-chat` / `gpt-4o` / `claude-3-5-sonnet`）
2. **模型 Base URL**（如 `https://api.deepseek.com/v1` 或你自己的中转站 / OpenAI 兼容端点）
3. **模型 API Key**（`sk-xxxxxxxx`）
4. **Telegram Bot Token**（可选，直接在终端/网页使用可回车跳过）
5. **Telegram 管理员 User ID**（可选）

---

## ⚙️ 自动化非交互式批量安装

可以通过预设环境变量实现无人值守静默安装：

```bash
export MODEL_NAME="deepseek-chat"
export BASE_URL="https://api.deepseek.com/v1"
export API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxx"
export TELEGRAM_BOT_TOKEN="123456789:ABCdefGHIjklMNOpqrSTUvwxYZ"
export TELEGRAM_ADMIN_ID="123456789"

curl -fsSL https://raw.githubusercontent.com/nayeshiluo/lemon-starter/main/install.sh | bash
```

---

## 💬 常用运维命令

- **进入终端交互**：`hermes`
- **重启 Web UI 面板**：`hermes-web-ui restart`
- **重启 Telegram 网关**：`sudo systemctl restart hermes-gateway`
- **查看网关运行日志**：`sudo journalctl -u hermes-gateway -f`
- **系统健康体检**：`hermes doctor`
