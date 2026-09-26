#!/bin/bash
set -e

echo "=== Building Frontend ==="
cd frontend
npm run build
cd ..

echo "=== Determining LAN IP ==="
LAN_IP=$(hostname -I | awk '{print $1}')
if [ -z "$LAN_IP" ]; then
    echo "Could not determine LAN IP. Ensure you are connected to the network."
    exit 1
fi
echo "Your LAN IP is: $LAN_IP"

echo "=== Starting Server ==="
echo "Access the application at: http://$LAN_IP:8000"
echo "(If users cannot connect, ensure your firewall allows TCP port 8000)"
cd backend
source venv/bin/activate 2>/dev/null || true
uvicorn app.main:app --host 0.0.0.0 --port 8000
