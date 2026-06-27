# ADS-B Feeder Dashboard

Web dashboard for Raspberry Pi ADS-B feeders: live reception stats, 24h history charts, tar1090 map, WDGoWars score/uploads, and one-click ops (restart readsb, gain presets).

Built for **readsb + tar1090** stacks, with first-class support for [airplanes.live](https://airplanes.live/) and [adsb.im](https://adsb.im/) feeders, plus optional [WDGoWars](https://wdgwars.pl/) uploads via [Muninn](https://github.com/Yggdrasil-AI-labs/adsb-to-wdgwars).

## Features

- Live aircraft table with search, sort, and distance from your station
- Health banner (SDR, readsb, upstream feeds, WDGoWars)
- 24h SVG sparkline history (aircraft, SNR, max range)
- WDGoWars score card, upload timeline, configurable upload interval
- Operations: restart services, gain presets, manual push
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

## Documentation

- [Install with airplanes.live](docs/INSTALL-airplanes-live.md)
- [Install with adsb.im](docs/INSTALL-adsbim.md)
- [Install readsb-only](docs/INSTALL-readsb-only.md)
- [Architecture](docs/ARCHITECTURE.md)

## Configuration

Copy `feeder.env.example` to `feeder.env` and edit paths if needed:

```bash
cp feeder.env.example feeder.env
```

Install scripts create `feeder.env` automatically on first run.

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
