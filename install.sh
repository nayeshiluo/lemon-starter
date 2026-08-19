#!/usr/bin/env bash
# Hermes Agent 纯净自动化一键安装部署套件
# 支持交互式输入模型 URL、API Key 与 Telegram 配置，全自动开机自启
set -euo pipefail

TARGET_USER="${SUDO_USER:-$(whoami)}"
USER_HOME="$(eval echo ~$TARGET_USER)"
WORKDIR="$(mktemp -d /tmp/hermes_install_XXXXXX)"

trap 'rm -rf "$WORKDIR"' EXIT

echo "=========================================================="
echo "      🤖 Hermes Agent 自动化一键部署套件"
echo "=========================================================="
echo "系统当前用户: $TARGET_USER ($USER_HOME)"

if [ "$(id -u)" -ne 0 ]; then
  SUDO="sudo"
else
  SUDO=""
fi

# 1. 安装基础依赖
echo ">> [1/5] 安装系统依赖 (curl, git, python3, sqlite3, systemd)..."
$SUDO apt-get update -y
$SUDO apt-get install -y curl git tar gzip sqlite3 ca-certificates jq systemd

# 2. 安装 Hermes Agent 核心
echo ">> [2/5] 正在安装 Hermes Agent 核心与 Python/uv 运行环境..."
su - "$TARGET_USER" -c 'curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash'

H="$USER_HOME/.hermes"
mkdir -p "$H" "$H/skills"

# 3. 部署全量扩展技能树
echo ">> [3/5] 部署扩展技能树 (Skills)..."
SKILLS_URL="https://raw.githubusercontent.com/nayeshiluo/lemon-starter/main/skills_bundle.tar.gz"
if curl -fsSL "$SKILLS_URL" -o "$WORKDIR/skills.tar.gz" 2>/dev/null; then
  tar xzf "$WORKDIR/skills.tar.gz" -C "$H" 2>/dev/null || true
  echo "  ✓ 技能树解压完成"
fi

# 4. 交互式配置向导 (支持从 /dev/tty 读取，兼容 curl | bash)
echo ""
echo "=========================================================="
echo "          🛠️  大模型与通信渠道配置向导"
echo "=========================================================="

# 读取终端输入的辅助函数
prompt_input() {
  local prompt_text="$1"
  local default_val="$2"
  local var_name="$3"
  local input=""

  if [ -t 0 ]; then
    read -r -p "$prompt_text [$default_val]: " input
  elif [ -e /dev/tty ]; then
    read -r -p "$prompt_text [$default_val]: " input </dev/tty
  fi

  input="${input:-$default_val}"
  eval "$var_name=\"\$input\""
}

prompt_secret() {
  local prompt_text="$1"
  local var_name="$2"
  local input=""

  if [ -t 0 ]; then
    read -r -s -p "$prompt_text: " input; echo ""
  elif [ -e /dev/tty ]; then
    read -r -s -p "$prompt_text: " input </dev/tty; echo ""
  fi

  eval "$var_name=\"\$input\""
}

# 默认环境变量覆盖或交互读取
CFG_MODEL="${MODEL_NAME:-}"
CFG_BASE_URL="${BASE_URL:-}"
CFG_API_KEY="${API_KEY:-}"
CFG_TG_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
CFG_TG_ADMIN="${TELEGRAM_ADMIN_ID:-}"

if [ -z "$CFG_MODEL" ]; then
  prompt_input "1. 请输入模型名称 (例如 deepseek-chat, gpt-4o, claude-3-5-sonnet)" "deepseek-chat" CFG_MODEL
fi

if [ -z "$CFG_BASE_URL" ]; then
  prompt_input "2. 请输入模型 API Base URL (例如 https://api.deepseek.com/v1 或中转站地址)" "https://api.deepseek.com/v1" CFG_BASE_URL
fi

if [ -z "$CFG_API_KEY" ]; then
  prompt_secret "3. 请输入该模型的 API Key (sk-...)" CFG_API_KEY
fi

echo ""
echo "--- Telegram 渠道配置 (可选，若仅在终端 CLI 使用可直接回车跳过) ---"
if [ -z "$CFG_TG_TOKEN" ]; then
  prompt_input "4. 请输入 Telegram Bot Token (若无需 TG 请直接回车)" "" CFG_TG_TOKEN
fi

if [ -n "$CFG_TG_TOKEN" ] && [ -z "$CFG_TG_ADMIN" ]; then
  prompt_input "5. 请输入你的 Telegram 纯数字 User ID (作为管理员)" "" CFG_TG_ADMIN
fi

# 5. 生成配置文件与守护进程
echo ">> [4/5] 写入配置与环境变量..."

# 写入 .env 密钥文件
cat <<EOF > "$H/.env"
CUSTOM_API_KEY=$CFG_API_KEY
OPENAI_API_KEY=$CFG_API_KEY
EOF

if [ -n "$CFG_TG_TOKEN" ]; then
  echo "TELEGRAM_BOT_TOKEN=$CFG_TG_TOKEN" >> "$H/.env"
  [ -n "$CFG_TG_ADMIN" ] && echo "TELEGRAM_ALLOWED_USERS=$CFG_TG_ADMIN" >> "$H/.env"
fi
chmod 600 "$H/.env"

# 写入 config.yaml 基础配置
cat <<EOF > "$H/config.yaml"
model:
  default: "$CFG_MODEL"
  provider: "custom"
  base_url: "$CFG_BASE_URL"
  api_key: "$CFG_API_KEY"

network:
  force_ipv4: true

display:
  tool_progress: false

agent:
  max_turns: 30
  session_reset:
    mode: "token"
    token_limit: 24000

EOF

if [ -n "$CFG_TG_TOKEN" ]; then
  cat <<EOF >> "$H/config.yaml"
telegram:
  enabled: true
  rich_messages: true
  rich_messages_allow_cjk: true
EOF
  if [ -n "$CFG_TG_ADMIN" ]; then
    cat <<EOF >> "$H/config.yaml"
  allow_admin_from:
    - $CFG_TG_ADMIN
EOF
  fi
fi

# 设置文件归属
chown -R "$TARGET_USER:$TARGET_USER" "$H"
chmod 700 "$H"

# 6. 配置 Systemd 开机自启守护
echo ">> [5/5] 配置 Systemd 守护进程..."

cat <<EOF | $SUDO tee /etc/systemd/system/hermes-gateway.service >/dev/null
[Unit]
Description=Hermes Agent Gateway
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$TARGET_USER
WorkingDirectory=$USER_HOME
ExecStart=$USER_HOME/.local/bin/hermes gateway
Restart=always
RestartSec=5
Environment=HOME=$USER_HOME
Environment=PATH=$USER_HOME/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

[Install]
WantedBy=multi-user.target
EOF

$SUDO systemctl daemon-reload
if [ -n "$CFG_TG_TOKEN" ]; then
  $SUDO systemctl enable --now hermes-gateway 2>/dev/null || true
fi

echo ""
echo "=========================================================="
echo "  🎉 Hermes Agent 部署完成！"
echo "  - 模型: $CFG_MODEL"
echo "  - 端点: $CFG_BASE_URL"
if [ -n "$CFG_TG_TOKEN" ]; then
  echo "  - Telegram Bot: 已启动并设置开机自启"
else
  echo "  - 终端交互: 在终端直接输入 'hermes' 即可开始聊天"
fi
echo "=========================================================="
