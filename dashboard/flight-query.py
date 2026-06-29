#!/usr/bin/env python3
"""Query the ADS-B flight log (flights.sqlite)."""
from __future__ import annotations

import argparse
import json
import sys

from flight_stats import (
    get_flight_stats,
    query_callsign,
    query_overhead,
    query_summary,
    query_top,
)


def print_callsign(data: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2))
        return
    print(f"Callsign: {data['callsign']} (last {data['days']} days)")
    print(f"  Sightings:    {data['sightings']}")
    print(f"  Unique ICAO:  {data['unique_hex']}")
    print(f"  First seen:   {data['first_seen'] or '—'}")
    print(f"  Last seen:    {data['last_seen'] or '—'}")


def print_summary(data: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2))
        return
    print(f"Summary ({data['period']})")
    print(f"  Unique aircraft: {data['unique_hex']}")
    print(f"  Total sightings: {data['sightings']}")
    print(f"  With position:   {data['positioned_sightings']}")


def print_top(rows: list[dict], days: float, as_json: bool) -> None:
    if as_json:
        print(json.dumps({"days": days, "top": rows}, indent=2))
        return
    print(f"Top callsigns (last {days} days)")
    if not rows:
        print("  (no data)")
        return
    for i, row in enumerate(rows, 1):
        print(
            f"  {i:2}. {row['flight']:<12} "
            f"{row['sightings']:>6} sightings  ({row['unique_hex']} ICAO)"
        )


def print_overhead(rows: list[dict], km: float, days: float, as_json: bool) -> None:
    if as_json:
        print(json.dumps({"km": km, "days": days, "aircraft": rows}, indent=2))
        return
    print(f"Aircraft within {km} km (last {days} days)")
    if not rows:
        print("  (none)")
        return
    for row in rows:
        alt = row["alt_baro"]
        alt_s = f"{alt} ft" if alt is not None else "—"
        print(
            f"  {row['flight']:<12} {row['hex']}  "
            f"{row['min_distance_km']:.2f} km  {alt_s}  @ {row['closest_at']}"
        )


def print_stats(data: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2))
        return
    if not data.get("ok"):
        print(f"Error: {data.get('error', 'unknown')}", file=sys.stderr)
        return
    size_mb = data["db_size_bytes"] / (1024 * 1024)
    print("Flight log stats")
    print(f"  Unique ICAO (24h):  {data['unique_hex_24h']}")
    print(f"  Unique ICAO (7d):   {data['unique_hex_7d']}")
    print(f"  Sightings today:    {data['sightings_today']}")
    print(f"  Total rows:         {data['total_rows']}")
    print(f"  Oldest record:      {data['oldest_record'] or '—'}")
    print(f"  Database size:      {size_mb:.2f} MB")
    if data.get("top_callsigns_7d"):
        print("  Top callsigns (7d):")
        for row in data["top_callsigns_7d"]:
            print(f"    {row['flight']:<12} {row['count']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Query ADS-B flight log")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    p_callsign = sub.add_parser("callsign", help="Search by callsign")
    p_callsign.add_argument("callsign")
    p_callsign.add_argument("--days", type=float, default=7)

    p_summary = sub.add_parser("summary", help="Unique aircraft summary")
    p_summary.add_argument("--today", action="store_true", help="Today only (default: 24h)")

    p_top = sub.add_parser("top", help="Top callsigns by sighting count")
    p_top.add_argument("--days", type=float, default=7)
    p_top.add_argument("--limit", type=int, default=20)

    p_overhead = sub.add_parser("overhead", help="Aircraft that passed near the station")
    p_overhead.add_argument("--km", type=float, default=5)
    p_overhead.add_argument("--days", type=float, default=1)

    sub.add_parser("stats", help="Database summary (same as dashboard API)")

    args = parser.parse_args()

    try:
        if args.command == "callsign":
            print_callsign(query_callsign(args.callsign, args.days), args.json)
        elif args.command == "summary":
            print_summary(query_summary(args.today), args.json)
        elif args.command == "top":
            print_top(query_top(args.days, args.limit), args.days, args.json)
        elif args.command == "overhead":
            print_overhead(query_overhead(args.km, args.days), args.km, args.days, args.json)
        elif args.command == "stats":
            print_stats(get_flight_stats(), args.json)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
