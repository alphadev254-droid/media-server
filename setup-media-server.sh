#!/bin/bash
# =============================================================================
# Media Server VPS Setup Script
# Run once on your Hostinger VPS as root
# Usage: bash setup-media-server.sh
# =============================================================================

set -e

# ── CONFIG ────────────────────────────────────────────────────────────────────
APP_DIR="/var/www/media-server"
DATA_DIR="/data/minio"
MINIO_USER="minioadmin"          # change before running
MINIO_PASS="changeme_strong"     # change before running
API_KEY="changeme_api_key"       # change before running
METRICS_TOKEN="changeme_metrics" # change before running
ALLOWED_ORIGINS='["https://aircnc.co.ke"]' # change before running
MEDIA_BASE_URL="https://media.aircnc.co.ke"  # change before running
PORT=3010

# ── COLORS ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()    { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }
section() { echo -e "\n${GREEN}━━━ $1 ━━━${NC}"; }

# ── CHECKS ───────────────────────────────────────────────────────────────────
section "Preflight checks"
[[ $EUID -ne 0 ]] && error "Run as root: sudo bash setup-media-server.sh"
[[ "$MINIO_PASS" == "changeme_strong" ]] && error "Set MINIO_PASS at top of script before running"
[[ "$API_KEY" == "changeme_api_key" ]] && error "Set API_KEY at top of script before running"
info "Checks passed"

# ── SYSTEM DEPS ──────────────────────────────────────────────────────────────
section "Installing system dependencies"
apt-get update -qq
apt-get install -y -qq \
    python3 python3-pip python3-venv \
    libmagic1 \
    ffmpeg \
    nginx \
    ufw \
    curl \
    unzip
info "System deps installed"

# ── MINIO ────────────────────────────────────────────────────────────────────
section "Installing MinIO"
if [ ! -f /usr/local/bin/minio ]; then
    curl -sSL https://dl.min.io/server/minio/release/linux-amd64/minio \
        -o /usr/local/bin/minio
    chmod +x /usr/local/bin/minio
    info "MinIO binary installed"
else
    info "MinIO already installed, skipping"
fi

mkdir -p $DATA_DIR

cat > /etc/default/minio << EOF
MINIO_ROOT_USER=${MINIO_USER}
MINIO_ROOT_PASSWORD=${MINIO_PASS}
MINIO_VOLUMES=${DATA_DIR}
MINIO_OPTS="--console-address :9001"
EOF
chmod 600 /etc/default/minio

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

systemctl daemon-reload
systemctl enable minio
systemctl restart minio
sleep 3

if systemctl is-active --quiet minio; then
    info "MinIO running"
else
    error "MinIO failed to start — check: journalctl -u minio -n 50"
fi

# ── APP ──────────────────────────────────────────────────────────────────────
section "Setting up Media API"
mkdir -p $APP_DIR

# Copy files if running from same dir as project, else assume already there
if [ -f "$(dirname "$0")/main.py" ]; then
    cp -r "$(dirname "$0")/." $APP_DIR/
    info "Project files copied to $APP_DIR"
else
    warn "Project files not found next to script — make sure they are in $APP_DIR"
fi

cd $APP_DIR

# Virtualenv
python3 -m venv venv
source venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
deactivate
info "Python deps installed"

# .env
cat > $APP_DIR/.env << EOF
MINIO_ENDPOINT=http://127.0.0.1:9000
MINIO_ACCESS_KEY=${MINIO_USER}
MINIO_SECRET_KEY=${MINIO_PASS}
MINIO_SECURE=false

PORT=${PORT}
WORKERS=2
MEDIA_BASE_URL=${MEDIA_BASE_URL}

API_KEY=${API_KEY}
ALLOWED_ORIGINS=${ALLOWED_ORIGINS}
METRICS_TOKEN=${METRICS_TOKEN}
EOF
chmod 600 $APP_DIR/.env
info ".env written"

# ── SYSTEMD SERVICE ──────────────────────────────────────────────────────────
section "Creating media-api systemd service"
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

systemctl daemon-reload
systemctl enable media-api
systemctl restart media-api
sleep 3

if systemctl is-active --quiet media-api; then
    info "Media API running on :${PORT}"
else
    error "Media API failed — check: journalctl -u media-api -n 50"
fi

# ── FIREWALL ─────────────────────────────────────────────────────────────────
section "Configuring firewall"
ufw --force enable
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw deny 9000/tcp   # block direct MinIO access
ufw deny 9001/tcp   # block MinIO console from public
ufw reload
info "Firewall configured — MinIO ports blocked from public"

# ── NGINX ────────────────────────────────────────────────────────────────────
section "Configuring Nginx"
DOMAIN=$(echo $MEDIA_BASE_URL | sed 's|https\?://||')

cat > /etc/nginx/sites-available/media-server << EOF
server {
    listen 80;
    server_name ${DOMAIN};

    client_max_body_size 500M;
    proxy_read_timeout 120s;

    # Serve public media files directly from MinIO (internal only)
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

    # API
    location / {
        proxy_pass http://127.0.0.1:${PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }
}
EOF

ln -sf /etc/nginx/sites-available/media-server /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
info "Nginx configured for ${DOMAIN}"

# ── HEALTH CHECK ─────────────────────────────────────────────────────────────
section "Health check"
sleep 2
STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:${PORT}/health)
if [ "$STATUS" == "200" ]; then
    info "API health check passed"
else
    warn "API health check returned $STATUS — may still be starting"
fi

# ── DONE ─────────────────────────────────────────────────────────────────────
section "Setup complete"
echo ""
echo "  Services:    systemctl status minio media-api"
echo "  API logs:    journalctl -u media-api -f"
echo "  MinIO logs:  journalctl -u minio -f"
echo "  Restart all: systemctl restart minio media-api"
echo "  Health:      curl http://localhost:${PORT}/health"
echo ""
echo "  Next: set up SSL with certbot:"
echo "  apt install certbot python3-certbot-nginx"
echo "  certbot --nginx -d ${DOMAIN}"
echo ""