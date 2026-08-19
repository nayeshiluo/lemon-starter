# 🤖 Hermes Agent 自动化一键安装套件 (Starter Edition)

本仓库提供 Hermes Agent 的纯净、自动化一键安装脚本与完整扩展技能树，支持自定义任何 OpenAI 兼容的模型 URL 端点与 API Key，并可快速接入 Telegram Bot。

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

## 🛠️ 安装过程配置说明

运行安装脚本后，会自动完成环境依赖安装与技能树注入，并进入交互式配置向导：

1. **模型名称**（如 `deepseek-chat` / `gpt-4o` / `claude-3-5-sonnet`）
2. **模型 Base URL**（如 `https://api.deepseek.com/v1` 或你自己的中转站 / OpenAI 兼容端点）
3. **模型 API Key**（`sk-xxxxxxxx`）
4. **Telegram Bot Token**（可选，直接在终端使用可回车跳过）
5. **Telegram 管理员 User ID**（可选）

---

## ⚙️ 非交互式（静默自动化安装）

如果你想通过脚本批量部署，可以在运行前注入环境变量：

```bash
export MODEL_NAME="deepseek-chat"
export BASE_URL="https://api.deepseek.com/v1"
export API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxx"
export TELEGRAM_BOT_TOKEN="123456789:ABCdefGHIjklMNOpqrSTUvwxYZ"
export TELEGRAM_ADMIN_ID="123456789"

curl -fsSL https://raw.githubusercontent.com/nayeshiluo/lemon-starter/main/install.sh | bash
```

---

## 💬 常用指令

- 启动终端交互：`hermes`
- 检查系统状态：`hermes doctor`
- 单次查询提问：`hermes chat -q "你好，请介绍一下你自己"`
- 重启 Telegram 网关：`sudo systemctl restart hermes-gateway`
- 查看网关日志：`sudo journalctl -u hermes-gateway -f`
