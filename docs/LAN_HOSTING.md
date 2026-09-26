# Hosting over College LAN

This guide explains how to host the application directly from a laptop connected to a college LAN, allowing 100+ participants on the same network to access and use the application through their browsers without needing to install anything.

## Architecture

The application has been unified so that the backend serves the built frontend files directly. This ensures that frontend API requests naturally use relative paths (`/api/...`), bypassing any `localhost` issues when accessed from other devices.

## Requirements

1. Python 3.10+ and Node.js installed on the host laptop.
2. A built frontend (run `npm run build` in the `frontend/` directory).
3. The backend installed and running (`uvicorn app.main:app --host 0.0.0.0 --port 8000`).

## Startup Procedure

A convenience script `start-lan.sh` is provided in the project root to automate this process.

1. **Run the script:**
   ```bash
   ./start-lan.sh
   ```
2. **Observe the output:**
   The script will build the frontend, determine your laptop's LAN IP address, and start the unified server on port `8000`.

   Example output:
   ```
   Your LAN IP is: 10.20.5.42
   === Starting Server ===
   Access the application at: http://10.20.5.42:8000
   ```
3. **Share the URL:**
   Participants can now open `http://<YOUR_LAN_IP>:8000` on their phones or laptops.

## Network & Firewall Configuration

- **Firewall:** You must configure your laptop's firewall to allow inbound connections on TCP port `8000`.
  - **Linux (UFW):** `sudo ufw allow 8000/tcp`
  - **macOS:** System Settings > Network > Firewall > Options > Add Python/Uvicorn.
  - **Windows:** Windows Defender Firewall > Advanced Settings > Inbound Rules > New Rule > Port > 8000.
- **Client/AP Isolation:** Some college networks use "Client Isolation" or "AP Isolation," which prevents devices on the same Wi-Fi network from communicating with each other. If participants cannot load the page despite the firewall being open, contact the network administrator to disable client isolation or request a dedicated subnet/VLAN for the event.

## Concurrency & Performance

- **Database:** The backend uses SQLite configured with `WAL` (Write-Ahead Logging) mode, a 5-second `busy_timeout`, and in-memory page caching. This allows concurrent readers and safely queues writers, comfortably supporting 100+ concurrent users on a standard laptop NVMe drive.
- **Thundering Herd:** Leaderboard queries are cached in-memory for 10 seconds, and client polling uses randomized jitter to prevent synchronized spikes in traffic.
- **Monitoring:** Monitor your laptop's CPU and RAM during the event (e.g., using `htop` or Activity Monitor). The application should consume minimal resources even under load.
