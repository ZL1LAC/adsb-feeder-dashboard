"""Feeder profile helpers (airplanes.live, adsb.im, readsb-only)."""
from __future__ import annotations

import os

FEED_PROFILE = os.environ.get("FEED_PROFILE", "airplanes").strip().lower()
if FEED_PROFILE in ("adsb-im", "adsb.im"):
    FEED_PROFILE = "adsbim"

LINKS = {
    "airplanes": {"url": "https://airplanes.live/myfeed/", "label": "airplanes.live"},
    "adsbim": {"url": "https://adsb.im/", "label": "adsb.im"},
    "readsb-only": {"url": "https://airplanes.live/myfeed/", "label": "airplanes.live"},
}


def link_info() -> dict[str, str]:
    return LINKS.get(FEED_PROFILE, LINKS["airplanes"])


def restart_units(scope: str) -> list[str]:
    """scope: readsb | all"""
    if FEED_PROFILE == "adsbim":
        return ["adsb-docker"] if scope == "readsb" else ["adsb-docker", "adsb-setup"]
    if scope == "all" and FEED_PROFILE == "airplanes":
        return ["readsb", "tar1090", "airplanes-feed", "airplanes-mlat"]
    return ["readsb", "tar1090"]


def apply_location_line(line: str, loc: dict) -> None:
    if "=" not in line:
        return
    key, _, raw = line.partition("=")
    key = key.strip()
    value = raw.strip().strip('"').strip("'")
    if key in ("LATITUDE", "FEEDER_LAT"):
        loc["lat"] = value
    elif key in ("LONGITUDE", "FEEDER_LONG"):
        loc["lon"] = value
    elif key in ("ALTITUDE", "FEEDER_ALT_M"):
        loc["alt"] = value if value.endswith(("m", "ft")) else f"{value}m"
    elif key in ("USER", "FEEDER_NAME"):
        loc["user"] = value


def build_services(service_state) -> dict:
    services = {
        "readsb": service_state("readsb"),
        "tar1090": service_state("tar1090"),
        "muninn": service_state("muninn-upload.timer", user=True),
    }
    if FEED_PROFILE == "airplanes":
        services["airplanes_feed"] = service_state("airplanes-feed")
        services["airplanes_mlat"] = service_state("airplanes-mlat")
    elif FEED_PROFILE == "adsbim":
        services["adsb_docker"] = service_state("adsb-docker")
        services["adsb_setup"] = service_state("adsb-setup")
    return services


def build_feeds(feed_connected, service_state) -> dict:
    if FEED_PROFILE == "airplanes":
        feeds = feed_connected()
        return {
            "airplanes_live": feeds["beast"],
            "airplanes_mlat": feeds["mlat"],
        }
    if FEED_PROFILE == "adsbim":
        docker = service_state("adsb-docker") == "active"
        setup = service_state("adsb-setup") == "active"
        return {
            "adsb_im_docker": docker,
            "adsb_im_setup": setup,
        }
    feeds = feed_connected()
    return {
        "airplanes_live": feeds["beast"],
        "airplanes_mlat": feeds["mlat"],
    }


def feeds_ok(feeds: dict) -> bool:
    if FEED_PROFILE == "airplanes":
        return bool(feeds.get("airplanes_live") and feeds.get("airplanes_mlat"))
    if FEED_PROFILE == "adsbim":
        return bool(feeds.get("adsb_im_docker"))
    return bool(feeds.get("airplanes_live") and feeds.get("airplanes_mlat"))
