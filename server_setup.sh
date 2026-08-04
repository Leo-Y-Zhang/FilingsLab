#!/bin/bash
set -e

echo "=== Installing Docker ==="
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker ubuntu
sudo apt-get install -y docker-compose-plugin

echo "=== Opening firewall ports ==="
# These rules do NOT restrict what the containers publish. Docker inserts its own
# DOCKER chain in nat/FORWARD, traversed BEFORE INPUT, so a published port is
# reachable whether or not there is an INPUT rule for it. Anything that must not
# be public has to be bound to 127.0.0.1 in docker-compose.yml rather than merely
# left out of this list - which is why the database is bound to loopback there.
# Do not add a port here and assume the converse holds.
sudo apt-get install -y iptables-persistent
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 8000 -j ACCEPT
sudo netfilter-persistent save

echo "=== Cloning FilingsLab ==="
git clone https://github.com/Leo-Y-Zhang/FilingsLab.git
cd FilingsLab

echo "=== Starting FilingsLab ==="
docker compose up -d --build

echo ""
echo "=== Done! ==="
echo "Frontend: http://$(curl -s ifconfig.me)"
echo "API docs: http://$(curl -s ifconfig.me):8000/api/docs"
