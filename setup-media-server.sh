#!/bin/bash
# =============================================================================
# Media Server VPS Setup Script — idempotent, safe to re-run
# Usage: bash setup-media-server.sh
# =============================================================================

set -e

# ── CONFIG — edit before running ─────────────────────────────────────────────
APP_DIR="/data/media-server"
DATA_DIR="/data/minio"
MINIO_USER="minio_user_alpha254x255xx255x255xx255x255"
MINIO_PASS="minio_pass_hfge3et67r346tfdfwtyfydtf2635er"
API_KEY="minio_api_key_hfge3ederhf347yf43t67r346tfdfwtyfydtf263er"
METRICS_TOKEN="minio_metrics_token_hfge3edeyfdguy4t37r6d3g4r746tfdfwtyfydtf263er"
ALLOWED_ORIGINS='["https://aircnc.co.ke"]'
ALLOWED_MEDIA_BASE_URLS='["https://media.aircnc.co.ke"]'
PORT=3010

# ── COLORS ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }
section() { echo -e "\n${GREEN}━━━ $1 ━━━${NC}"; }

# ── CHECKS ───────────────────────────────────────────────────────────────────
section "Preflight checks"
[[ $EUID -ne 0 ]] && error "Run as root: sudo bash setup-media-server.sh"
[[ "$MINIO_PASS" == "changeme_strong" ]] && error "Set MINIO_PASS before running"
[[ "$API_KEY" == "changeme_api_key" ]] && error "Set API_KEY before running"
info "Checks passed"

# ── SYSTEM DEPS ──────────────────────────────────────────────────────────────
section "Installing system dependencies"
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv libmagic1 ffmpeg nginx ufw curl rsync
info "System deps installed"

# ── MINIO ────────────────────────────────────────────────────────────────────
section "Installing MinIO"
if [ ! -f /usr/local/bin/minio ]; then
    curl -sSL https://dl.min.io/server/minio/release/linux-amd64/minio -o /usr/local/bin/minio
    chmod +x /usr/local/bin/minio
    info "MinIO binary installed"
else
    info "MinIO already installed, skipping download"
fi

mkdir -p $DATA_DIR

# Only rewrite config if credentials changed
MINIO_HASH=$(echo "${MINIO_USER}${MINIO_PASS}" | md5sum | cut -d' ' -f1)
MINIO_HASH_FILE="/etc/default/minio.hash"
if [ ! -f /etc/default/minio ] || [ ! -f "$MINIO_HASH_FILE" ] || [ "$(cat $MINIO_HASH_FILE)" != "$MINIO_HASH" ]; then
    cat > /etc/default/minio << EOF
MINIO_ROOT_USER=${MINIO_USER}
MINIO_ROOT_PASSWORD=${MINIO_PASS}
MINIO_VOLUMES=${DATA_DIR}
MINIO_OPTS="--console-address :9001"
EOF
    chmod 600 /etc/default/minio
    echo "$MINIO_HASH" > "$MINIO_HASH_FILE"
    info "MinIO config written"
else
    info "MinIO config unchanged, skipping"
fi

if [ ! -f /etc/systemd/system/minio.service ]; then
    cat > /etc/systemd/system/minio.service << 'EOF'
[Unit]
Description=MinIO Object Storage
After=network.target
Wants=network-online.target

[Service]
User=root
EnvironmentFile=/etc/default/minio
ExecStart=/usr/local/bin/minio server $MINIO_VOLUMES $MINIO_OPTS
Restart=always
RestartSec=5
LimitNOFILE=65536
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF
    info "MinIO service file written"
else
    info "MinIO service file exists, skipping"
fi

systemctl daemon-reload
systemctl enable minio
systemctl restart minio
sleep 3
systemctl is-active --quiet minio && info "MinIO running" || error "MinIO failed — check: journalctl -u minio -n 50"

# ── APP ──────────────────────────────────────────────────────────────────────
section "Setting up Media API"
mkdir -p $APP_DIR

# Sync project files (exclude .env and venv to avoid overwriting)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ "$SCRIPT_DIR" = "$APP_DIR" ]; then
    info "Script running from APP_DIR — skipping file copy"
elif [ -f "$SCRIPT_DIR/main.py" ]; then
    rsync -a --exclude='.env' --exclude='venv' --exclude='__pycache__' "$SCRIPT_DIR/" $APP_DIR/
    info "Project files synced"
else
    warn "main.py not found next to script — assuming files already in $APP_DIR"
fi

cd $APP_DIR

# Virtualenv — only create if missing
if [ ! -d "$APP_DIR/venv" ]; then
    python3 -m venv venv
    info "Virtualenv created"
else
    info "Virtualenv exists, skipping"
fi

source venv/bin/activate

# Only reinstall if requirements.txt changed
REQ_HASH=$(md5sum requirements.txt | cut -d' ' -f1)
REQ_HASH_FILE="$APP_DIR/.req.hash"
if [ ! -f "$REQ_HASH_FILE" ] || [ "$(cat $REQ_HASH_FILE)" != "$REQ_HASH" ]; then
    pip install --quiet --upgrade pip
    pip install --quiet -r requirements.txt
    echo "$REQ_HASH" > "$REQ_HASH_FILE"
    info "Python deps installed"
else
    info "requirements.txt unchanged, skipping pip install"
fi

deactivate

# .env — only write if missing (won't overwrite manual edits on re-run)
if [ ! -f "$APP_DIR/.env" ]; then
    cat > $APP_DIR/.env << EOF
MINIO_ENDPOINT=http://127.0.0.1:9000
MINIO_ACCESS_KEY=${MINIO_USER}
MINIO_SECRET_KEY=${MINIO_PASS}
MINIO_SECURE=false

PORT=${PORT}
WORKERS=2

API_KEY=${API_KEY}
ALLOWED_ORIGINS=${ALLOWED_ORIGINS}
ALLOWED_MEDIA_BASE_URLS=${ALLOWED_MEDIA_BASE_URLS}
METRICS_TOKEN=${METRICS_TOKEN}
EOF
    chmod 600 $APP_DIR/.env
    info ".env written"
else
    info ".env already exists, skipping (edit manually if needed)"
fi

# ── SYSTEMD SERVICE ──────────────────────────────────────────────────────────
section "Creating media-api systemd service"
if [ ! -f /etc/systemd/system/media-api.service ]; then
    cat > /etc/systemd/system/media-api.service << EOF
[Unit]
Description=Media API (FastAPI + Gunicorn)
After=network.target minio.service
Wants=minio.service

[Service]
User=root
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/venv/bin/gunicorn main:app -c gunicorn.conf.py
Restart=always
RestartSec=5
TimeoutStopSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
    info "media-api service file written"
else
    info "media-api service file exists, skipping"
fi

systemctl daemon-reload
systemctl enable media-api
systemctl restart media-api
sleep 3
systemctl is-active --quiet media-api && info "Media API running on :${PORT}" || error "Media API failed — check: journalctl -u media-api -n 50"

# ── FIREWALL ─────────────────────────────────────────────────────────────────
section "Configuring firewall"
UFW_STATUS=$(ufw status | head -1)
if echo "$UFW_STATUS" | grep -q "inactive"; then
    warn "ufw is inactive — skipping to avoid disrupting existing services"
    warn "After verifying your existing port rules, manually run:"
    warn "  ufw allow ssh && ufw allow 80 && ufw allow 443"
    warn "  ufw deny 9000 && ufw deny 9001 && ufw --force enable"
else
    ufw allow ssh
    ufw allow 80/tcp
    ufw allow 443/tcp
    ufw deny 9000/tcp
    ufw deny 9001/tcp
    ufw reload
    info "Firewall rules added (existing rules untouched)"
fi

# ── NGINX ────────────────────────────────────────────────────────────────────
section "Configuring Nginx"
NGINX_CONF="/etc/nginx/sites-available/media-server"

# Extract domain from first entry in ALLOWED_MEDIA_BASE_URLS
DOMAIN=$(echo $ALLOWED_MEDIA_BASE_URLS | grep -oP 'https?://\K[^"]+' | head -1)

if [ ! -f "$NGINX_CONF" ]; then
    cat > $NGINX_CONF << EOF
server {
    listen 80;
    server_name ${DOMAIN};

    client_max_body_size 500M;
    proxy_read_timeout 120s;

    location ~* \.(webp|jpg|jpeg|png|gif|mp3|wav|ogg|pdf)$ {
        valid_referers none blocked ${DOMAIN} *.${DOMAIN};
        if (\$invalid_referer) {
            return 403;
        }
        proxy_pass http://127.0.0.1:9000;
        proxy_set_header Host \$host;
        add_header Cache-Control "public, max-age=31536000, immutable";
        add_header X-Content-Type-Options nosniff;
    }

    location / {
        proxy_pass http://127.0.0.1:${PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }
}
EOF
    ln -sf $NGINX_CONF /etc/nginx/sites-enabled/media-server
    info "Nginx config written for ${DOMAIN}"
else
    info "Nginx config exists, skipping (edit $NGINX_CONF manually if needed)"
fi

nginx -t && systemctl reload nginx

# ── HEALTH CHECK ─────────────────────────────────────────────────────────────
section "Health check"
sleep 2
STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:${PORT}/health)
[ "$STATUS" == "200" ] && info "API health check passed ✓" || warn "Health check returned $STATUS — may still be starting"

# ── DONE ─────────────────────────────────────────────────────────────────────
section "Setup complete"
echo ""
echo "  Services:    systemctl status minio media-api"
echo "  API logs:    journalctl -u media-api -f"
echo "  MinIO logs:  journalctl -u minio -f"
echo "  Restart all: systemctl restart minio media-api"
echo "  Health:      curl http://localhost:${PORT}/health"
echo ""
echo "  Re-running this script is safe — existing config/env/venv won't be overwritten"
echo ""
echo "  Next — SSL:"
echo "  apt install certbot python3-certbot-nginx"
echo "  certbot --nginx -d ${DOMAIN}"
echo ""