#!/bin/sh
# Lightsail prepends its initialization and invokes user data with /bin/sh.
set -eu
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y docker.io docker-compose-v2 python3 openssl ca-certificates curl
systemctl enable --now docker
install -d -m 0755 /opt/mujuthaek-source
touch /var/lib/mujuthaek-bootstrap-ready
