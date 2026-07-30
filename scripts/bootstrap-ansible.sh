#!/usr/bin/env bash
set -euo pipefail

sudo apt update
sudo apt install -y ansible-core git python3-venv
ansible-galaxy collection install -r collections/requirements.yml
