#!/usr/bin/env bash
# Hermes Agent 纯净自动化一键安装部署套件 (含 Web UI 面板 + Telegram 网关)
set -euo pipefail

TARGET_USER="${SUDO_USER:-$(whoami)}"
USER_HOME="$(eval echo ~$TARGET_USER)"
WORKDIR="$(mktemp -d /tmp/hermes_install_XXXXXX)"

trap 'rm -rf "$WORKDIR"' EXIT

echo "=========================================================="
echo "      🤖 Hermes Agent 自动化一键部署套件 (带 Web UI 面板)"
echo "=========================================================="
echo "系统当前用户: $TARGET_USER ($USER_HOME)"

if [ "$(id -u)" -ne 0 ]; then
  SUDO="sudo"
else
  SUDO=""
fi

# 1. 自动为低内存机器创建 Swap (防止 512MB/1GB NAT 小鸡 OOM 崩溃)
TOTAL_MEM="$(free -m | awk '/Mem:/ {print $2}')"
if [ "$TOTAL_MEM" -lt 1500 ] && [ ! -f /swapfile ] && [ "$(free -m | awk '/Swap:/ {print $2}')" -eq 0 ]; then
  echo ">> 检测到内存较小 (${TOTAL_MEM}MB)，正在创建 1GB 虚拟内存 (Swap)..."
  $SUDO fallocate -l 1G /swapfile 2>/dev/null || $SUDO dd if=/dev/zero of=/swapfile bs=1M count=1024 2>/dev/null
  $SUDO chmod 600 /swapfile
  $SUDO mkswap /swapfile >/dev/null 2>&1
  $SUDO swapon /swapfile >/dev/null 2>&1
  echo '/swapfile none swap sw 0 0' | $SUDO tee -a /etc/fstab >/dev/null
  echo "  ✓ 1GB Swap 启用成功"
fi

# 2. 安装基础依赖与 xz-utils, Node.js
echo ">> [1/6] 安装系统依赖 (curl, git, xz-utils, sqlite3, systemd)..."
$SUDO apt-get update -y
$SUDO apt-get install -y curl git tar gzip xz-utils sqlite3 ca-certificates jq systemd openssl

if ! command -v node &>/dev/null || [ "$(node -v | cut -d. -f1 | tr -d 'v')" -lt 20 ]; then
  echo "安装 Node.js 22.x..."
  curl -fsSL https://deb.nodesource.com/setup_22.x | $SUDO bash -
  $SUDO apt-get install -y nodejs
fi

# 3. 安装 Hermes Agent 官方核心
echo ">> [2/6] 安装 Hermes Agent 核心与 Python/uv 环境..."
if [ "$TARGET_USER" = "root" ]; then
  curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
else
  su - "$TARGET_USER" -c 'curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash'
fi

# 确保环境变量
export PATH="$USER_HOME/.local/bin:/usr/local/bin:$PATH"

H="$USER_HOME/.hermes"
mkdir -p "$H" "$H/skills"

# 4. 安装 Hermes Web UI 网页控制台
echo ">> [3/6] 安装 Hermes Web UI 网页控制台..."
$SUDO npm install -g --allow-scripts=agent-browser,node-pty,vue-demi hermes-web-ui@latest || true

# 5. 部署全量扩展技能树
echo ">> [4/6] 部署扩展技能树 (Skills)..."
SKILLS_URL="https://raw.githubusercontent.com/nayeshiluo/lemon-starter/main/skills_bundle.tar.gz"
if curl -fsSL "$SKILLS_URL" -o "$WORKDIR/skills.tar.gz" 2>/dev/null; then
  tar xzf "$WORKDIR/skills.tar.gz" -C "$H" 2>/dev/null || true
  echo "  ✓ 技能树注入完成"
fi

# 6. 交互式配置向导 (支持从 /dev/tty 读取，兼容 curl | bash)
echo ""
echo "=========================================================="
echo "          🛠️ 大模型、网页端与通信渠道配置"
echo "=========================================================="

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

CFG_MODEL="${MODEL_NAME:-}"
CFG_BASE_URL="${BASE_URL:-}"
CFG_API_KEY="${API_KEY:-}"
CFG_TG_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
CFG_TG_ADMIN="${TELEGRAM_ADMIN_ID:-}"

if [ -z "$CFG_MODEL" ]; then
  prompt_input "1. 请输入模型名称 (如 deepseek-chat, gpt-4o, claude-3-5-sonnet)" "deepseek-chat" CFG_MODEL
fi

if [ -z "$CFG_BASE_URL" ]; then
  prompt_input "2. 请输入模型 API Base URL (如 https://api.deepseek.com/v1 或中转站地址)" "https://api.deepseek.com/v1" CFG_BASE_URL
fi

if [ -z "$CFG_API_KEY" ]; then
  prompt_secret "3. 请输入该模型的 API Key (sk-...)" CFG_API_KEY
fi

echo ""
echo "--- Telegram 机器人配置 (可选，若无需 TG 可直接回车跳过) ---"
if [ -z "$CFG_TG_TOKEN" ]; then
  prompt_input "4. 请输入 Telegram Bot Token (若无需 TG 请直接回车)" "" CFG_TG_TOKEN
fi

if [ -n "$CFG_TG_TOKEN" ] && [ -z "$CFG_TG_ADMIN" ]; then
  prompt_input "5. 请输入你的 Telegram 纯数字 User ID (作为管理员)" "" CFG_TG_ADMIN
fi

# 7. 生成配置文件
echo ">> [5/6] 写入配置与环境变量..."

API_SERVER_KEY="$(openssl rand -hex 16)"

cat <<EOF > "$H/.env"
CUSTOM_API_KEY=$CFG_API_KEY
OPENAI_API_KEY=$CFG_API_KEY
API_SERVER_KEY=$API_SERVER_KEY
EOF

if [ -n "$CFG_TG_TOKEN" ]; then
  echo "TELEGRAM_BOT_TOKEN=$CFG_TG_TOKEN" >> "$H/.env"
  [ -n "$CFG_TG_ADMIN" ] && echo "TELEGRAM_ALLOWED_USERS=$CFG_TG_ADMIN" >> "$H/.env"
fi
chmod 600 "$H/.env"

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

platforms:
  api_server:
    enabled: true
    key: "$API_SERVER_KEY"
    cors_origins: ["*"]

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

chown -R "$TARGET_USER:$TARGET_USER" "$H"
chmod 700 "$H"

# 8. 配置守护进程并启动 (Gateway + Web-UI)
echo ">> [6/6] 注册 Systemd 守护进程并启动服务..."

cat <<EOF | $SUDO tee /etc/systemd/system/hermes-gateway.service >/dev/null
[Unit]
Description=Hermes Agent Gateway
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$TARGET_USER
WorkingDirectory=$USER_HOME
ExecStart=/usr/local/bin/hermes gateway
Restart=always
RestartSec=5
Environment=HOME=$USER_HOME
Environment=PATH=$USER_HOME/.local/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin

[Install]
WantedBy=multi-user.target
EOF

$SUDO systemctl daemon-reload
if [ -n "$CFG_TG_TOKEN" ]; then
  $SUDO systemctl enable --now hermes-gateway 2>/dev/null || true
fi

# 启动 Web UI 控制面板
if [ "$TARGET_USER" = "root" ]; then
  hermes-web-ui stop 2>/dev/null || true
  hermes-web-ui start 2>/dev/null || true
else
  su - "$TARGET_USER" -c 'hermes-web-ui stop 2>/dev/null || true'
  su - "$TARGET_USER" -c 'hermes-web-ui start 2>/dev/null || true'
fi

SERVER_IP="$(curl -s --connect-timeout 3 https://api.ipify.org || echo "103.69.129.103")"

echo ""
echo "=========================================================="
echo "  🎉 Hermes Agent & Web UI 面板已成功部署！"
echo "=========================================================="
echo "  🌐 网页管理面板地址:  http://$SERVER_IP:8648"
echo "  👤 默认超管登录账号:  admin"
echo "  🔑 默认超管登录密码:  123456  (首次登录后请在后台修改)"
echo "----------------------------------------------------------"
echo "  🤖 模型端点: $CFG_BASE_URL ($CFG_MODEL)"
if [ -n "$CFG_TG_TOKEN" ]; then
  echo "  📱 Telegram Bot: 已自动连线上线"
fi
echo "  💻 终端交互: 在服务器终端直接输入 'hermes' 即可交谈"
echo "=========================================================="
