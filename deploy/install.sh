#!/usr/bin/env bash
# BOTLAB Auditor - one-shot installer for a fresh Vultr Ubuntu 24.04 VM.
#
#   sudo bash deploy/install.sh
#
# It installs Docker, builds the sandbox image, creates a Python virtual environment, registers the
# app as a systemd service on 127.0.0.1:8780, and puts Caddy in front of it so the site is served
# over HTTPS on an sslip.io hostname derived from the VM's public IP (no domain purchase needed).
#
# Safe to re-run: every step is idempotent. It never writes a secret - the owner pastes the Vultr
# Serverless Inference key into .env themselves (see deploy/DEPLOY_VULTR.md).
set -euo pipefail

APP_USER="auditor"
APP_DIR="/opt/botlab-auditor"
PORT="8780"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

log() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31m!! %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "run this with sudo: sudo bash deploy/install.sh"

# ------------------------------------------------------------------------------ base packages
log "Installing base packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
  ca-certificates curl git python3 python3-venv python3-pip ufw debian-keyring \
  debian-archive-keyring apt-transport-https gnupg

# ------------------------------------------------------------------------------------- docker
if ! command -v docker >/dev/null 2>&1; then
  log "Installing Docker Engine"
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io
fi
systemctl enable --now docker

# --------------------------------------------------------------------------- app user and code
if ! id -u "$APP_USER" >/dev/null 2>&1; then
  log "Creating the service account: $APP_USER"
  useradd --system --create-home --shell /usr/sbin/nologin "$APP_USER"
fi
# The app shells out to "docker run", so the service account needs the docker group.
usermod -aG docker "$APP_USER"

log "Copying the application to $APP_DIR"
mkdir -p "$APP_DIR"
if [ "$SRC_DIR" != "$APP_DIR" ]; then
  tar -C "$SRC_DIR" --exclude='.git' --exclude='.venv' --exclude='__pycache__' \
      --exclude='.pytest_cache' --exclude='.env' -cf - . | tar -C "$APP_DIR" -xf -
fi
# Keep an existing .env; otherwise seed it from the example so the owner has a file to edit.
[ -f "$APP_DIR/.env" ] || cp "$APP_DIR/.env.example" "$APP_DIR/.env"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
chmod 600 "$APP_DIR/.env"

# ----------------------------------------------------------------------------- python venv
log "Creating the Python virtual environment"
if [ ! -x "$APP_DIR/.venv/bin/python" ]; then
  python3 -m venv "$APP_DIR/.venv"
fi
"$APP_DIR/.venv/bin/pip" install --upgrade pip wheel
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"
chown -R "$APP_USER:$APP_USER" "$APP_DIR/.venv"

# ------------------------------------------------------------------------- sandbox image
log "Building the sandbox container image"
docker build -f "$APP_DIR/sandbox/Dockerfile" -t botlab-sandbox:latest "$APP_DIR"

# ------------------------------------------------------------------------- systemd service
log "Installing the systemd service"
cat > /etc/systemd/system/botlab-auditor.service <<EOF
[Unit]
Description=BOTLAB Auditor (FastAPI)
After=network-online.target docker.service
Wants=network-online.target
Requires=docker.service

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port $PORT --proxy-headers
Restart=always
RestartSec=3
# The app itself needs no privileges; the sandbox container is what runs untrusted code.
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
MemoryMax=1500M

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable botlab-auditor
systemctl restart botlab-auditor

# -------------------------------------------------------------------------------- caddy / TLS
PUBLIC_IP="$(curl -4fsS --max-time 10 https://api.ipify.org || true)"
[ -n "$PUBLIC_IP" ] || PUBLIC_IP="$(hostname -I | awk '{print $1}')"
HOSTNAME_SSLIP="${PUBLIC_IP//./-}.sslip.io"

if ! command -v caddy >/dev/null 2>&1; then
  log "Installing Caddy"
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -y
  apt-get install -y caddy
fi

log "Configuring Caddy for https://$HOSTNAME_SSLIP"
cat > /etc/caddy/Caddyfile <<EOF
# sslip.io resolves <ip-with-dashes>.sslip.io to that IP, so Let's Encrypt can issue a
# certificate without buying a domain.
$HOSTNAME_SSLIP {
	encode zstd gzip
	# Server-Sent Events must not be buffered.
	reverse_proxy 127.0.0.1:$PORT {
		flush_interval -1
	}
	request_body {
		max_size 1MB
	}
	header {
		-Server
		Referrer-Policy "no-referrer"
		X-Content-Type-Options "nosniff"
	}
	log {
		# Request lines only. Uploaded file contents are never logged, here or in the app.
		output file /var/log/caddy/access.log
	}
}
EOF
systemctl enable caddy
systemctl restart caddy

# ------------------------------------------------------------------------------------ firewall
log "Opening the firewall for ssh, http and https"
ufw allow 22/tcp  >/dev/null
ufw allow 80/tcp  >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null

# -------------------------------------------------------------------------------------- done
sleep 3
log "Status"
systemctl is-active botlab-auditor && echo "app: active"
systemctl is-active caddy && echo "caddy: active"
curl -fsS "http://127.0.0.1:$PORT/api/health" || echo "health check failed - see: journalctl -u botlab-auditor -n 50"

cat <<EOF

--------------------------------------------------------------------
Installed.

  Public URL : https://$HOSTNAME_SSLIP
  Service    : systemctl status botlab-auditor
  Logs       : journalctl -u botlab-auditor -f
  Config     : $APP_DIR/.env   (paste the Vultr Serverless Inference key into LLM_API_KEY)

After editing .env:  sudo systemctl restart botlab-auditor
--------------------------------------------------------------------
EOF
