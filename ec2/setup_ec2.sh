#!/usr/bin/env bash
# ==============================================================================
# NexChecker EC2 Host Setup & Provisioning Script
# Target OS: Ubuntu 22.04 / 24.04 LTS (AWS EC2 t2/t3.micro, small, medium)
# ==============================================================================
set -euo pipefail

echo "========================================================"
echo "🚀 Starting NexChecker EC2 Initial Provisioning..."
echo "========================================================"

# 1. Update OS packages
echo "📦 Updating apt packages..."
sudo apt-get update -y && sudo apt-get upgrade -y
sudo apt-get install -y curl wget git ufw htop net-tools ca-certificates gnupg lsb-release

# 2. Configure 2GB Swap (Crucial for t3.micro / 1GB RAM instances)
if ! grep -q "swapfile" /etc/fstab; then
    echo "💾 Creating 2GB swap space for memory stability..."
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    sudo sysctl vm.swappiness=10
    echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf
    echo "✅ Swap configured successfully."
else
    echo "ℹ️  Swap already configured."
fi

# 3. Install Docker Engine & Docker Compose Plugin
if ! command -v docker &> /dev/null; then
    echo "🐳 Installing Docker Engine..."
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    sudo apt-get update -y
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    sudo usermod -aG docker "$USER"
    sudo systemctl enable docker
    sudo systemctl start docker
    echo "✅ Docker installed."
else
    echo "ℹ️  Docker is already installed."
fi

# 4. Install Python 3.11/3.12 and dependencies for Native mode option
sudo apt-get install -y python3-pip python3-venv

# 5. Configure Basic Firewall
echo "🔒 Configuring UFW Firewall..."
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 8000/tcp
sudo ufw --force enable

echo "========================================================"
echo "🎉 EC2 Host Provisioning Completed!"
echo "Run 'bash ec2/deploy.sh' to launch NexChecker."
echo "========================================================"
