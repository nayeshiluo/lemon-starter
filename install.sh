#!/usr/bin/env bash
# Hermes Agent 纯净自动化一键安装部署套件 (含 Web UI 面板 + Telegram 网关)
set -euo pipefail
umask 077

TARGET_USER="${SUDO_USER:-$(whoami)}"
USER_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
[[ -n "$USER_HOME" && "$TARGET_USER" != root ]] || { echo 'FAILED: 请使用专用普通用户配合 sudo 安装，拒绝以 root 运行 Agent。' >&2; exit 1; }

assert_reviewed_revision() {
  [[ "${STARTER_REVISION:-}" =~ ^[0-9a-f]{40}$ ]] || { echo 'FAILED: 必须指定已审核的完整 STARTER_REVISION。' >&2; return 1; }
  git -C "$SCRIPT_DIR" cat-file -e "$STARTER_REVISION^{commit}" 2>/dev/null || { echo 'FAILED: 本地缺少指定提交。' >&2; return 1; }
  git -C "$SCRIPT_DIR" show "$STARTER_REVISION:install.sh" | cmp -s - "$SCRIPT_DIR/install.sh" || { echo 'FAILED: 正在运行的安装器与指定提交不一致。' >&2; return 1; }
}
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
assert_reviewed_revision

assert_dependency_pins() {
  [[ "${HERMES_INSTALLER_SHA256:-}" =~ ^[0-9a-f]{64}$ ]] || { echo 'FAILED: 必须提供已审核 Hermes 官方安装器的 HERMES_INSTALLER_SHA256。' >&2; return 1; }
  if ! command -v node >/dev/null || [ "$(node -v | cut -d. -f1 | tr -d 'v')" -lt 24 ]; then
    [[ "${NODESOURCE_SETUP_SHA256:-}" =~ ^[0-9a-f]{64}$ ]] || { echo 'FAILED: 安装 Node.js 前必须提供已审核的 NODESOURCE_SETUP_SHA256。' >&2; return 1; }
  fi
}
assert_dependency_pins

verify_download() {
  local file="$1" expected="$2" actual
  actual="$(sha256sum "$file")"
  [[ "${actual%% *}" == "$expected" ]] || { echo 'FAILED: 外部安装器摘要不符，未执行。' >&2; return 1; }
}
assert_fresh_install() {
  local home_dir="$1" unit_dir="$2" existing
  for existing in "$home_dir/.hermes/.env" "$home_dir/.hermes/config.yaml" "$home_dir/.hermes-web-ui" \
    "$unit_dir/hermes-web-ui.service" "$unit_dir/hermes-web-ui.service.d" \
    "$unit_dir/hermes-gateway.service" "$unit_dir/hermes-gateway.service.d"; do
    if [ -e "$existing" ] || [ -L "$existing" ]; then
      echo "FAILED: 本脚本仅用于全新安装；检测到已有配置或服务，已停止以防覆盖。" >&2
      return 1
    fi
  done
  if [ -L "$home_dir/.hermes" ]; then
    echo "FAILED: Hermes 配置目录不能为符号链接。" >&2
    return 1
  fi
}
assert_fresh_install "$USER_HOME" /etc/systemd/system
WORKDIR="$(mktemp -d /tmp/hermes_install_XXXXXX)"

installer_exit() {
  local exit_code=$?
  if [ "$exit_code" -eq 0 ]; then
    rm -rf "$WORKDIR"
  else
    echo "FAILED: 安装未完成；临时现场保留在 $WORKDIR（权限700），请勿删除已有配置后盲目重装。" >&2
  fi
}
trap installer_exit EXIT

# 使用固定 Git 对象中的已审核资源，不在运行时下载并执行仓库 Python。
for asset in skills_bundle.tar.gz skills_bundle.manifest.json tools/public_skills_guard.py tools/bootstrap_webui.py tools/sync_telegram_menu.py; do
  git -C "$SCRIPT_DIR" show "$STARTER_REVISION:$asset" > "$WORKDIR/${asset##*/}"
done
python3 "$WORKDIR/public_skills_guard.py" "$WORKDIR/skills_bundle.tar.gz" "$WORKDIR/skills_bundle.manifest.json"
# 外部脚本先完整下载、核验，再运行；摘要须来自使用者审核的版本。
curl -fsSL --proto '=https' --proto-redir '=https' https://hermes-agent.nousresearch.com/install.sh -o "$WORKDIR/hermes-official.sh"
verify_download "$WORKDIR/hermes-official.sh" "$HERMES_INSTALLER_SHA256"
if ! command -v node >/dev/null || [ "$(node -v | cut -d. -f1 | tr -d 'v')" -lt 24 ]; then
  curl -fsSL --proto '=https' --proto-redir '=https' https://deb.nodesource.com/setup_24.x -o "$WORKDIR/nodesource.sh"
  verify_download "$WORKDIR/nodesource.sh" "$NODESOURCE_SETUP_SHA256"
fi

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

# Swap 不会提高 Node 自动计算的堆上限；低内存构建需显式设置。
configure_build_memory() {
  if [ "$TOTAL_MEM" -lt 1500 ] && [ -z "${NODE_OPTIONS:-}" ]; then
    export NODE_OPTIONS="--max-old-space-size=512"
  fi
}
configure_build_memory

# 2. 安装基础依赖与 xz-utils, Node.js
echo ">> [1/6] 安装系统依赖 (curl, git, xz-utils, sqlite3, systemd)..."
$SUDO apt-get update -y
$SUDO apt-get install -y curl git tar gzip xz-utils sqlite3 ca-certificates jq systemd openssl python3 build-essential

if ! command -v node &>/dev/null || [ "$(node -v | cut -d. -f1 | tr -d 'v')" -lt 24 ]; then
  echo "安装 Node.js 24.x（Web UI 0.6.44 要求 Node >=23）..."
  $SUDO bash "$WORKDIR/nodesource.sh"
  $SUDO apt-get install -y nodejs
fi

# 3. 安装 Hermes Agent 官方核心
echo ">> [2/6] 安装 Hermes Agent 核心与 Python/uv 环境..."
if [ "$(whoami)" = "$TARGET_USER" ]; then
  bash "$WORKDIR/hermes-official.sh"
else
  # root 创建的 0700 临时目录不能由目标用户读取；通过 stdin 交给用户运行。
  su --whitelist-environment=NODE_OPTIONS - "$TARGET_USER" -c 'bash -s' < "$WORKDIR/hermes-official.sh"
fi

# 确保环境变量
export PATH="$USER_HOME/.local/bin:/usr/local/bin:$PATH"

H="$USER_HOME/.hermes"
mkdir -p "$H" "$H/skills"

# 4. 安装 Hermes Web UI 网页控制台
echo ">> [3/6] 安装 Hermes Web UI 网页控制台..."
install_webui() {
  (
    # 全局公共程序须供服务用户读取；后续秘密仍使用外层 umask 077。
    umask 022
    $SUDO npm install -g --allow-scripts=agent-browser,node-pty,protobufjs,vue-demi hermes-web-ui@0.6.44
  )
}
install_webui

# 5. 部署全量扩展技能树
echo ">> [4/6] 部署扩展技能树 (Skills)..."
python3 - "$WORKDIR/skills_bundle.tar.gz" "$H" <<'PY'
import pathlib,sys,tarfile
root=pathlib.Path(sys.argv[2]).resolve()
with tarfile.open(sys.argv[1]) as archive:
    for member in archive:
        if not member.isfile():continue
        dest=root/member.name
        if root not in dest.resolve().parents:raise ValueError('unsafe extraction destination')
        if dest.is_symlink():raise ValueError('symlink destination')
        dest.parent.mkdir(parents=True,exist_ok=True)
        with dest.open('wb') as output:output.write(archive.extractfile(member).read())
        dest.chmod(member.mode&0o755)
PY
echo "  ✓ 技能包校验及安装完成：$STARTER_REVISION"

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
  elif ( : </dev/tty ) 2>/dev/null; then
    read -r -p "$prompt_text [$default_val]: " input </dev/tty
  fi

  input="${input:-$default_val}"
  printf -v "$var_name" '%s' "$input"
}

prompt_secret() {
  local prompt_text="$1"
  local var_name="$2"
  local input=""

  if [ -t 0 ]; then
    read -r -s -p "$prompt_text: " input; echo ""
  elif ( : </dev/tty ) 2>/dev/null; then
    read -r -s -p "$prompt_text: " input </dev/tty; echo ""
  fi

  printf -v "$var_name" '%s' "$input"
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

# 7. 生成配置文件与默认人设
echo ">> [5/6] 写入配置、人设与环境变量..."

API_SERVER_KEY="$(openssl rand -hex 16)"
validate_installer_config() {
  local cfg_value
  [ -n "$CFG_API_KEY" ] || { echo "FAILED: 模型 API Key 不能为空" >&2; return 1; }
  for cfg_value in "$CFG_MODEL" "$CFG_BASE_URL" "$CFG_API_KEY" "$CFG_TG_TOKEN" "$CFG_TG_ADMIN"; do
    [[ "$cfg_value" != *$'\n'* && "$cfg_value" != *$'\r'* ]] || { echo "FAILED: 配置值不能包含换行" >&2; return 1; }
  done
  [[ -z "$CFG_TG_ADMIN" || "$CFG_TG_ADMIN" =~ ^[1-9][0-9]*$ ]] || { echo "FAILED: Telegram ID 必须为正整数" >&2; return 1; }
  if [ -n "$CFG_TG_TOKEN" ] && [ -z "$CFG_TG_ADMIN" ]; then
    echo "FAILED: 启用 Telegram 时必须填写自己的管理员 ID。" >&2
    return 1
  fi
}
validate_installer_config
json_scalar() { python3 -c 'import json,sys; print(json.dumps(sys.stdin.read(),ensure_ascii=False))'; }
MODEL_YAML="$(printf '%s' "$CFG_MODEL" | json_scalar)"
BASE_URL_YAML="$(printf '%s' "$CFG_BASE_URL" | json_scalar)"
API_KEY_YAML="$(printf '%s' "$CFG_API_KEY" | json_scalar)"
TG_TOKEN_ENV="$(printf '%s' "$CFG_TG_TOKEN" | json_scalar)"

cat <<EOF > "$H/.env"
API_SERVER_KEY=$API_SERVER_KEY
API_SERVER_HOST=127.0.0.1
API_SERVER_PORT=8642
EOF

if [ -n "$CFG_TG_TOKEN" ]; then
  echo "TELEGRAM_BOT_TOKEN=$TG_TOKEN_ENV" >> "$H/.env"
  [ -n "$CFG_TG_ADMIN" ] && echo "TELEGRAM_ALLOWED_USERS=$CFG_TG_ADMIN" >> "$H/.env"
fi
chmod 600 "$H/.env"

if [ ! -f "$H/SOUL.md" ]; then
  cat <<'EOF' > "$H/SOUL.md"
# 身份与交流准则
你是一个聪明、利落、专业且全能的 AI 个人助理。
你具备高超的代码编写、Linux 运维管理、网络配置与全自动化解决问题的能力。
在与用户沟通时，请始终默认使用流畅自然的中文进行交流，回答直接有力、条理清晰。
EOF
fi

cat <<EOF > "$H/config.yaml"
model:
  default: $MODEL_YAML
  provider: "custom"
  base_url: $BASE_URL_YAML
  api_key: $API_KEY_YAML

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
    host: "127.0.0.1"
    port: 8642
    cors_origins: ["http://127.0.0.1:8648", "http://localhost:8648"]

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
  group_allow_admin_from:
    - $CFG_TG_ADMIN
  user_allowed_commands: help,whoami
  group_user_allowed_commands: help,whoami
EOF
  fi
fi

chmod 600 "$H/config.yaml"
chown -R "$TARGET_USER:$TARGET_USER" "$H"
chmod 700 "$H"

# 保存独立菜单修复工具，失败时无需重新安装或删除配置。
mkdir -p "$H/starter-tools"
cp "$WORKDIR/sync_telegram_menu.py" "$H/starter-tools/sync_telegram_menu.py"
cp "$WORKDIR/bootstrap_webui.py" "$H/starter-tools/bootstrap_webui.py"
chmod 600 "$H/starter-tools/"*.py
chown -R "$TARGET_USER:$TARGET_USER" "$H/starter-tools"

# 8. 配置守护进程并启动 (Gateway + Web-UI)
echo ">> [6/6] 注册 Systemd 守护进程并启动服务..."

# 动态解析 hermes 二进制绝对路径并建立全局软链接
HERMES_BIN="$(command -v hermes 2>/dev/null || true)"
if [ -z "$HERMES_BIN" ] || [ ! -x "$HERMES_BIN" ]; then
  if [ -x "$USER_HOME/.local/bin/hermes" ]; then
    HERMES_BIN="$USER_HOME/.local/bin/hermes"
  elif [ -x "$USER_HOME/.hermes/hermes-agent/venv/bin/hermes" ]; then
    HERMES_BIN="$USER_HOME/.hermes/hermes-agent/venv/bin/hermes"
  else
    HERMES_BIN="/usr/local/bin/hermes"
  fi
fi

if [ -x "$HERMES_BIN" ] && [ ! -f /usr/local/bin/hermes ]; then
  $SUDO ln -sf "$HERMES_BIN" /usr/local/bin/hermes 2>/dev/null || true
fi

cat <<EOF | $SUDO tee /etc/systemd/system/hermes-gateway.service >/dev/null
[Unit]
Description=Hermes Agent Gateway
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
UMask=0077
NoNewPrivileges=true
User=$TARGET_USER
WorkingDirectory=$USER_HOME
ExecStart=$HERMES_BIN gateway
Restart=always
RestartSec=5
Environment=API_SERVER_HOST=127.0.0.1
Environment=API_SERVER_PORT=8642
Environment=HOME=$USER_HOME
Environment=PATH=$USER_HOME/.local/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin

[Install]
WantedBy=multi-user.target
EOF

$SUDO systemctl daemon-reload
# Web UI 同样需要网关；Telegram 仅控制通信渠道，不能控制网关是否启动。
$SUDO systemctl enable --now hermes-gateway

# 启动 Web UI 控制面板 (注册 systemd 守护进程以保障开机自启与崩溃自愈)
NODE_BIN="$(command -v node || echo /usr/bin/node)"
NPM_ROOT="$($SUDO npm root -g 2>/dev/null || echo /usr/local/lib/node_modules)"
WEB_UI_DIR="$NPM_ROOT/hermes-web-ui"

if [ -d "$WEB_UI_DIR" ]; then
  cat <<EOF | $SUDO tee /etc/systemd/system/hermes-web-ui.service >/dev/null
[Unit]
Description=Hermes Web UI Service
After=network-online.target hermes-gateway.service
Wants=network-online.target hermes-gateway.service

[Service]
Type=simple
UMask=0077
NoNewPrivileges=true
User=$TARGET_USER
Group=$TARGET_USER
WorkingDirectory=$WEB_UI_DIR
Environment="HOME=$USER_HOME"
Environment="USER=$TARGET_USER"
Environment="NODE_ENV=production"
Environment="PORT=8648"
Environment="BIND_HOST=127.0.0.1"
Environment="HERMES_WEB_UI_DISABLE_GATEWAY_AUTOSTART=1"
Environment="HERMES_WEB_UI_MANAGED_GATEWAY=0"
Environment="PATH=$USER_HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$NODE_BIN dist/server/index.js
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

  $SUDO systemctl daemon-reload
  $SUDO systemctl enable --now hermes-web-ui
else
  echo "FAILED: Web UI 安装目录不存在，服务未启动" >&2
  exit 1
fi

if ! python3 "$H/starter-tools/bootstrap_webui.py" --credentials "$H/webui-initial-login.json"; then
  # sudo 安装时失败留下的凭据也必须交回服务用户，才能独立恢复。
  if [ -f "$H/webui-initial-login.json" ]; then
    chown "$TARGET_USER:$TARGET_USER" "$H/webui-initial-login.json"
  fi
  $SUDO systemctl stop hermes-web-ui
  echo "FAILED: 初始密码配置失败；面板已停止，凭据已保留，请按 README 独立恢复。" >&2
  exit 1
fi
chown "$TARGET_USER:$TARGET_USER" "$H/webui-initial-login.json"
$SUDO systemctl is-active --quiet hermes-web-ui
$SUDO systemctl is-active --quiet hermes-gateway

# 菜单是可重试的附加步骤，不阻止核心服务注册；失败必须明确显示。
if [ -n "$CFG_TG_TOKEN" ]; then
  if python3 "$H/starter-tools/sync_telegram_menu.py" --env-file "$H/.env"; then
    printf 'SUCCESS\n' > "$H/starter-tools/telegram-menu-status"
  else
    printf 'FAILED\n' > "$H/starter-tools/telegram-menu-status"
    echo "WARNING: Telegram 菜单同步 FAILED，核心服务已启动；请独立重试菜单同步。" >&2
  fi
  chown "$TARGET_USER:$TARGET_USER" "$H/starter-tools/telegram-menu-status"
fi

echo ""
echo "=========================================================="
echo "  🎉 Hermes Agent & Web UI 核心服务部署 SUCCESS"
echo "=========================================================="
echo "  🌐 面板只监听本机: http://127.0.0.1:8648；请通过 SSH 通道访问"
echo "  👤 超管账号: admin；随机密码保存在 $H/webui-initial-login.json（权限600）"
echo "  🔒 无需开放公网 8648；密码不会写入终端日志"
echo "----------------------------------------------------------"
echo "  🤖 模型端点: $CFG_BASE_URL ($CFG_MODEL)"
if [ -n "$CFG_TG_TOKEN" ]; then
  echo "  📱 Telegram 网关进程已启动；真实收发仍需测试，菜单状态见 $H/starter-tools/telegram-menu-status"
fi
echo "  💻 终端交互: 在服务器终端直接输入 'hermes' 即可交谈"
echo "=========================================================="
