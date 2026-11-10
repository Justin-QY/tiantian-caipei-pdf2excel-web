#!/usr/bin/env bash
# 裸机部署：Linux + systemd（不装 Docker 时用这个）
# 用法：sudo bash deploy.sh
# 会自动安装到 /opt/pdf2xlsx，建 venv，生成随机访问口令，注册并启动 pdf2xlsx.service
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/pdf2xlsx}"
PORT="${PORT:-8765}"
RUN_USER="${SUDO_USER:-$(id -un)}"
RUN_GROUP="$(id -gn "$RUN_USER")"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> 目标目录 $APP_DIR · 服务账号 $RUN_USER · 端口 $PORT"

sudo mkdir -p "$APP_DIR"
tar --exclude='.git' --exclude='__pycache__' --exclude='.env' \
    --exclude='.env.example' --exclude='.venv' --exclude='*.pdf' \
    --exclude='*.xlsx' --exclude='*.png' --exclude='*.zip' \
    -C "$SRC_DIR" -cf - . | sudo tar -C "$APP_DIR" -xf -
sudo chown -R "$RUN_USER:$RUN_GROUP" "$APP_DIR"

if [ ! -f "$APP_DIR/.env" ]; then
  CODE=$(python3 -c 'import secrets; print(secrets.token_urlsafe(12))')
  sudo tee "$APP_DIR/.env" > /dev/null <<EOF
PORT=$PORT
HOST=127.0.0.1
THREADS=4
MAX_UPLOAD_MB=50
CHANNEL_TIMEOUT=300
ACCESS_CODE=$CODE
EOF
  sudo chmod 600 "$APP_DIR/.env"
  sudo chown "$RUN_USER:$RUN_GROUP" "$APP_DIR/.env"
  echo "==> 访问口令：$CODE （只显示这一次，请保存）"
else
  echo "==> 已有 .env，保持原口令不变"
fi

sudo -u "$RUN_USER" python3 -m venv "$APP_DIR/.venv"
sudo -u "$RUN_USER" "$APP_DIR/.venv/bin/pip" install --no-cache-dir -r "$APP_DIR/requirements.txt"

sudo tee /etc/systemd/system/pdf2xlsx.service > /dev/null <<EOF
[Unit]
Description=Tiantian Caipei PDF2Excel Web
After=network.target

[Service]
Type=simple
User=$RUN_USER
Group=$RUN_GROUP
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/.venv/bin/python $APP_DIR/app.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now pdf2xlsx.service
sleep 1
sudo systemctl --no-pager status pdf2xlsx.service | head -n 12

echo ""
echo "==> 服务已启动，仅监听 127.0.0.1:$PORT"
echo "==> 下一步（宝塔面板，两个文件都要放）："
echo "    nginx-limits.conf.example -> /www/server/panel/vhost/nginx/0.ttqd-limits.conf"
echo "    nginx.conf.example        -> /www/server/panel/vhost/nginx/extension/<你的域名>/ttqd.conf"
echo "    然后执行：sudo nginx -t && sudo nginx -s reload"
echo "==> 第一个文件定义 IP 限流 zone，必须在 http 上下文；少放它 nginx -t 会报错"
echo "==> 证书用宝塔面板现成站点证书即可，不需要 certbot 单独签"
