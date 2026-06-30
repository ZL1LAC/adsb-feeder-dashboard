# ADS-B Feeder Dashboard

Web dashboard for Raspberry Pi ADS-B feeders: live reception stats, 24h history charts, tar1090 map, WDGoWars score/uploads, and one-click ops (restart readsb, gain presets).

Built for **readsb + tar1090** stacks, with first-class support for [airplanes.live](https://airplanes.live/) and [adsb.im](https://adsb.im/) feeders, plus optional [WDGoWars](https://wdgwars.pl/) uploads via [Muninn](https://github.com/Yggdrasil-AI-labs/adsb-to-wdgwars).

## Features

- Live aircraft table with search, sort, and distance from your station
- Health banner (SDR, readsb, upstream feeds, WDGoWars)
- 24h SVG sparkline history (aircraft, SNR, max range)
- WDGoWars score card, upload timeline, configurable upload interval
- Operations: restart services, gain presets, manual push
- **Gotify alerts**: feeder down, watchlist, overhead passes, squawk codes (7500/7600/7700 + custom)
- **Flight log analytics**: 30-day SQLite history, dashboard stats, CLI queries
- **Settings page** (`/dashboard/settings.html`): Gotify, squawk alerts, watchlist, station location, gain, Muninn interval
- SDR auto-recovery watcher
- Mobile-friendly layout + PWA manifest

## Quick start

**Prerequisites:** Raspberry Pi (or Linux SBC), RTL-SDR, readsb, tar1090, lighttpd.

### airplanes.live (recommended)

```bash
git clone https://github.com/ZL1LAC/adsb-feeder-dashboard.git
cd adsb-feeder-dashboard
git submodule update --init --recursive   # Muninn

sudo ./scripts/install-airplanes.sh      # readsb + tar1090 + airplanes.live feed
./scripts/install.sh --profile airplanes
./scripts/go-live.sh YOUR_WDGOWARS_API_KEY
```

Open `http://<pi-ip>/dashboard/`

### adsb.im

```bash
git clone https://github.com/ZL1LAC/adsb-feeder-dashboard.git
cd adsb-feeder-dashboard
git submodule update --init --recursive

# Install adsb.im first — see docs/INSTALL-adsbim.md
./scripts/install.sh --profile adsbim
./scripts/go-live.sh YOUR_WDGOWARS_API_KEY   # optional
```

### readsb + tar1090 only (no airplanes.live)

```bash
git clone https://github.com/ZL1LAC/adsb-feeder-dashboard.git
cd adsb-feeder-dashboard
git submodule update --init --recursive

# Install readsb + tar1090 first (see docs/INSTALL-readsb-only.md)
./scripts/install.sh --profile readsb-only
./scripts/go-live.sh YOUR_WDGOWARS_API_KEY   # optional
```

### Split stack (SDR on Pi, dashboard on another host)

Keep the RTL-SDR and decoder on the Pi; run the dashboard, alerts, and WDGoWars uploads in Docker on another machine (NAS, VM, etc.).

**On the Pi (decode host):**

```bash
./scripts/install-pi-decode-only.sh
```

**On the Docker host:**

```bash
cd docker && cp .env.example .env   # set PI_HOST, PI_AGENT_URL, PI_AGENT_TOKEN
../scripts/install-split-docker.sh
```

See [Split-stack deployment](docs/SPLIT-STACK.md) for networking, reverse proxy, and troubleshooting.

## Documentation

- [Install with airplanes.live](docs/INSTALL-airplanes-live.md)
- [Install with adsb.im](docs/INSTALL-adsbim.md)
- [Install readsb-only](docs/INSTALL-readsb-only.md)
- [Split stack (SDR on Pi, dashboard elsewhere)](docs/SPLIT-STACK.md)
- [Architecture](docs/ARCHITECTURE.md)

## Configuration

Copy `feeder.env.example` to `feeder.env` and edit paths if needed:

```bash
cp feeder.env.example feeder.env
```

Install scripts create `feeder.env` automatically on first run.

For push notifications, run [Gotify](https://gotify.net/) (see `scripts/install-gotify.sh` or use an existing server), create an app, and paste the app token in **Dashboard → Settings**.

Squawk alerts: emergency codes 7500/7600/7700 are on by default; add custom codes in Settings (comma-separated).

**Dashboard login (Docker / split stack):** optional HTTP basic auth for public URLs:

```bash
./scripts/set-dashboard-password.sh admin
cd docker && docker compose up -d caddy
```

Browser will prompt for username/password on `/dashboard/` and `/tar1090/`. Leave unset for trusted LAN only.

## Logs

Muninn upload logs (when user journal is empty):

```bash
./scripts/tail-log.sh
```

## Security

The dashboard API (`/dashboard/api/*`) has **no authentication** — intended for trusted LAN use only.

## Credits

- [Muninn / adsb-to-wdgwars](https://github.com/Yggdrasil-AI-labs/adsb-to-wdgwars) — WDGoWars uploads
- [wiedehopf/readsb](https://github.com/wiedehopf/readsb) + [tar1090](https://github.com/wiedehopf/tar1090)
- [airplanes.live feed](https://github.com/airplanes-live/feed)

## License

MIT — see [LICENSE](LICENSE).
