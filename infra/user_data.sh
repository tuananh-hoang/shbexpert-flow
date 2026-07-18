#!/bin/bash
# Bootstrap Docker Engine + Compose on Ubuntu 24.04. Code is shipped
# separately (rsync) since we deploy manually without CI/CD.
set -euxo pipefail
export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y ca-certificates curl rsync git

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

usermod -aG docker ubuntu
systemctl enable --now docker

mkdir -p /opt/shbexpert
chown ubuntu:ubuntu /opt/shbexpert

# Marker the deploy script polls on for readiness.
touch /opt/shbexpert/.bootstrap-done
