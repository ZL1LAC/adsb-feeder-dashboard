# Install with airplanes.live

This matches a typical Pi feeder: **readsb → tar1090 → airplanes.live** plus **WDGoWars** uploads and the custom dashboard.

## Hardware

- Raspberry Pi 4/5 (or similar) with Raspberry Pi OS
- RTL-SDR dongle (tested: RTL2832U / R820T, RTL-SDR Blog V4)
- 1090 MHz ADS-B antenna

## 1. System packages

```bash
sudo apt update
sudo apt install -y git lighttpd python3 python3-venv python3-pip
```

## 2. Install airplanes.live feed

This installs readsb, tar1090, and the airplanes.live upstream feed:

```bash
git clone https://github.com/YOUR_USER/adsb-feeder-dashboard.git
cd adsb-feeder-dashboard
git submodule update --init --recursive

sudo ./scripts/install-airplanes.sh
```

The installer uses the official [airplanes-live/feed](https://github.com/airplanes-live/feed) script. You will be prompted for:

- Station latitude / longitude / altitude
- Feed name (UUID shown on [airplanes.live/myfeed](https://airplanes.live/myfeed/))

Config is stored in `/etc/default/airplanes`.

## 3. Install dashboard + Muninn

```bash
./scripts/install.sh --profile airplanes
```

This will:

- Clone/build Muninn in `muninn/` (if submodule not initialized)
- Install systemd user services (`feeder-api`, status timer, SDR watcher)
- Install lighttpd snippet for `/dashboard/`
- Install sudoers rules for restart/gain operations

If lighttpd or sudoers need root:

```bash
sudo cp /tmp/89-feeder-dashboard.conf /etc/lighttpd/conf-enabled/89-feeder-dashboard.conf
sudo systemctl reload lighttpd
sudo cp /tmp/feeder-ops /etc/sudoers.d/feeder-ops
sudo chmod 440 /etc/sudoers.d/feeder-ops
```

## 4. Enable WDGoWars uploads

Get your API key from [wdgwars.pl](https://wdgwars.pl/) → profile → API Key.

```bash
./scripts/go-live.sh YOUR_API_KEY
# optional: custom interval in minutes (default 5)
./scripts/go-live.sh YOUR_API_KEY 10
```

Uploads skip automatically when there are no positioned aircraft.

## 5. Verify

```bash
systemctl status readsb tar1090 airplanes-feed airplanes-mlat
systemctl --user status feeder-api.service feeder-dashboard.timer
curl -s http://127.0.0.1/dashboard/status.json | head
```

Open in a browser:

- Dashboard: `http://<pi-ip>/dashboard/`
- tar1090 map: `http://<pi-ip>/tar1090/`

## Notes

- Muninn warnings about ports `30104` / `30001` are **expected** on airplanes.live setups (MLAT). The dashboard filters them from the UI.
- Upload logs go to `logs/upload.log` if `journalctl --user` is empty: `./scripts/tail-log.sh`
- Optional: add `--lat` / `--lon` to readsb for tar1090 range outline (`readsb-set-location` or `/etc/default/readsb`)

## Troubleshooting

| Symptom | Check |
|---------|--------|
| No aircraft | `systemctl status readsb`, `lsusb`, restart readsb |
| Dashboard 404 | lighttpd config, `systemctl --user status feeder-api` |
| Uploads fail | `./scripts/tail-log.sh`, verify API key with `muninn/muninn.py --whoami -q` |
| SDR drops | Dashboard auto-recovery runs every 60s; replug USB if needed |
