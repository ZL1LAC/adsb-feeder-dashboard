# Install readsb + tar1090 only

Use this path if you **do not** feed airplanes.live (or use a different upstream). The dashboard still works; the Feeds card will show airplanes.live as disconnected.

## 1. Install readsb and tar1090

Follow the official installers for your platform:

- [wiedehopf/readsb](https://github.com/wiedehopf/readsb) — SDR decoder
- [wiedehopf/tar1090](https://github.com/wiedehopf/tar1090) — web map at `/tar1090/`

On Raspberry Pi, the common pattern is:

```bash
# Example — use upstream install scripts for your OS version
sudo bash -c "$(wget -O - https://github.com/wiedehopf/readsb/raw/master/readsb-install.sh)"
sudo bash -c "$(wget -O - https://github.com/wiedehopf/tar1090/raw/master/install.sh)"
```

Verify:

```bash
systemctl status readsb tar1090
ls -la /run/readsb/aircraft.json
curl -s http://127.0.0.1/tar1090/data/aircraft.json | head
```

## 2. lighttpd

```bash
sudo apt install -y lighttpd
```

Ensure tar1090 is served (usually `/etc/lighttpd/conf-enabled/88-tar1090.conf`).

## 3. Clone and install dashboard

```bash
git clone https://github.com/YOUR_USER/adsb-feeder-dashboard.git
cd adsb-feeder-dashboard
git submodule update --init --recursive

./scripts/install.sh --profile readsb-only
```

## 4. WDGoWars (optional)

```bash
./scripts/go-live.sh YOUR_WDGOWARS_API_KEY
```

Without this step, the dashboard still shows reception and aircraft; only automated WDGoWars uploads are disabled.

## 5. Station location

For distance column and max-range stats, set your coordinates in a location file. The dashboard reads `/etc/default/airplanes` if present, or create `feeder.env`:

```bash
FEEDER_LOCATION_FILE=/etc/default/airplanes
```

Example `/etc/default/airplanes` (minimal):

```bash
LATITUDE="-36.59382"
LONGITUDE="174.69439"
ALTITUDE="12m"
```

## Differences from airplanes.live profile

| Feature | readsb-only | airplanes.live |
|---------|-------------|----------------|
| Upstream feed | Manual / other | airplanes-feed + MLAT |
| Feeds health chip | May show red | Green when connected |
| Restart all | readsb + tar1090 only | + airplanes services |

The install script uses the same dashboard; only `FEED_PROFILE` in `feeder.env` documents your setup.
