# Install with adsb.im

Use this path when your feeder runs the [adsb.im](https://adsb.im/) platform — the Docker-based stack that manages readsb, tar1090, and multi-aggregator feeds.

This dashboard adds WDGoWars uploads, 24h history charts, and one-click ops alongside the adsb.im web UI (`:1099`).

## 1. Install adsb.im

If you do not already have adsb.im running:

```bash
# Review the script first, then run as root:
curl -fsSL https://raw.githubusercontent.com/dirkhh/adsb-feeder-image/main/src/tools/app-install.sh -o app-install.sh
less app-install.sh
sudo bash app-install.sh
```

Or flash an SD card image from [adsb.im/download](https://adsb.im/).

Complete the basic setup in the adsb.im web UI (station name, location, aggregators).

Verify:

```bash
systemctl status adsb-docker adsb-setup
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:1099/
```

## 2. Expose tar1090 to this dashboard

The dashboard reads live aircraft from `/tar1090/data/aircraft.json`. On adsb.im, tar1090 runs in Docker (default port `1090`).

Install lighttpd and proxy tar1090 if it is not already available at `/tar1090/`:

```bash
sudo apt install -y lighttpd git python3 python3-venv
```

Example proxy snippet (`/etc/lighttpd/conf-enabled/88-tar1090-adsbim.conf`):

```lighttpd
$HTTP["url"] =~ "^/tar1090/" {
    proxy.server = ( "" => ( ( "host" => "127.0.0.1", "port" => 1090 ) ) )
    proxy.header = ( "map-urlpath" => ( "/tar1090/" => "/" ) )
}
```

Adjust the port if your `AF_TAR1090_PORT` in `/opt/adsb/config/.env` differs.

## 3. Clone and install dashboard

```bash
git clone https://github.com/ZL1LAC/adsb-feeder-dashboard.git
cd adsb-feeder-dashboard
git submodule update --init --recursive

./scripts/install.sh --profile adsbim
```

This sets `FEED_PROFILE=adsbim` and `FEEDER_LOCATION_FILE=/opt/adsb/config/.env` in `feeder.env`.

If lighttpd or sudoers need root:

```bash
sudo cp /tmp/89-feeder-dashboard.conf /etc/lighttpd/conf-enabled/89-feeder-dashboard.conf
sudo systemctl reload lighttpd
sudo cp /tmp/feeder-ops /etc/sudoers.d/feeder-ops
sudo chmod 440 /etc/sudoers.d/feeder-ops
```

## 4. WDGoWars (optional)

```bash
./scripts/go-live.sh YOUR_WDGOWARS_API_KEY
```

Muninn reads `/run/readsb/aircraft.json` by default. If aircraft data is only inside Docker, set `FEEDER_AIRCRAFT_JSON` in `feeder.env` to the host path adsb.im mounts, or ensure readsb output is shared on the host.

## 5. Open the dashboard

- **This dashboard:** `http://<host>/dashboard/`
- **adsb.im setup UI:** `http://<host>:1099` or [my.adsb.im](https://my.adsb.im/)

## Profile behaviour

| Feature | adsb.im profile |
|---------|-----------------|
| Location | `/opt/adsb/config/.env` (`FEEDER_LAT`, `FEEDER_LONG`, `FEEDER_NAME`) |
| Services card | `adsb-docker`, `adsb-setup` |
| Feeds health | `adsb-docker` active |
| Restart readsb | `systemctl restart adsb-docker` |
| Restart all | `adsb-docker` + `adsb-setup` |
| Gain presets | Use adsb.im web UI (gain is managed inside Docker) |

## Differences from airplanes.live profile

| | airplanes.live | adsb.im |
|--|----------------|---------|
| Upstream | airplanes-feed + MLAT | Multi-aggregator Docker stack |
| Config | `/etc/default/airplanes` | `/opt/adsb/config/.env` |
| Aggregator link | airplanes.live | adsb.im |
