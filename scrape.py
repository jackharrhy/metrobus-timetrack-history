#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "beautifulsoup4>=4.12",
#     "httpx>=0.27",
# ]
# ///
"""Scrape Metrobus timetrack data and write it to timetrack.json.

The old JSON API (https://www.metrobus.co.ca/api/timetrack/json/) is gone and
the replacement at https://www.metrobustransit.ca/api/timetrack/json/ returns a
server-side ASP error. The public-facing page at
https://www.metrobusmobile.com/timetrack.asp still works and loads its content
from /timetrack_data.asp, which returns an HTML fragment. This script parses
that fragment back into a JSON shape close to the old API so the git-history
diffs keep working.

Run locally with:
    uv run scrape.py
or just:
    ./scrape.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

URL = "https://www.metrobusmobile.com/timetrack_data.asp"
REFERER = "https://www.metrobusmobile.com/timetrack.asp"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# fa-kit icons used on the page look like:
#   <i class="fa-kit fa-01-1 fa-4x" style="color: #0056d6;"></i>  (route)
#   <i class="fa-kit fa-2439 fa-4x" style="color: #000000;"></i> (vehicle)
ROUTE_CLASS_RE = re.compile(r"^fa-(\d+-\d+)$")
VEHICLE_CLASS_RE = re.compile(r"^fa-(\d+)$")
BG_COLOR_RE = re.compile(r"background-color:\s*(#[0-9A-Fa-f]{6})")


def fetch(url: str = URL) -> str:
    resp = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT, "Referer": REFERER},
        timeout=30,
        follow_redirects=True,
    )
    resp.raise_for_status()
    return resp.text


def _icon_value(icon: Tag, pattern: re.Pattern[str]) -> str | None:
    for cls in icon.get("class", []):
        m = pattern.match(cls)
        if m:
            return m.group(1)
    return None


def _bg_color(anchor: Tag) -> str | None:
    style = anchor.get("style", "")
    m = BG_COLOR_RE.search(style)
    return m.group(1) if m else None


def _parse_badge(text: str) -> tuple[str | None, str | None]:
    """Badge example: '4 MINS BEHIND @ 5:03 PM' -> ('4 MINS BEHIND', '5:03 PM')."""
    text = " ".join(text.split())
    if not text:
        return None, None
    if "@" in text:
        deviation, _, ts = text.partition("@")
        return deviation.strip() or None, ts.strip() or None
    return text, None


def _to_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_anchor(anchor: Tag) -> dict[str, Any] | None:
    href = anchor.get("href") or ""
    if "busLocate.asp" not in href:
        return None
    params = dict(parse_qsl(urlparse(href).query, keep_blank_values=True))

    icons = anchor.find_all("i", class_="fa-kit")
    current_route: str | None = None
    vehicle: str | None = None
    for icon in icons:
        if current_route is None:
            current_route = _icon_value(icon, ROUTE_CLASS_RE)
        if vehicle is None:
            vehicle = _icon_value(icon, VEHICLE_CLASS_RE)
    if current_route is None:
        current_route = params.get("route")

    headsign_tag = anchor.find("h3")
    headsign: str | None = None
    if headsign_tag is not None:
        # h3 may contain a nested <span> bulletin notice; drop it before reading text.
        for child in headsign_tag.find_all(["span", "br"]):
            child.extract()
        headsign = headsign_tag.get_text(strip=True) or None

    current_location: str | None = None
    location_tag = anchor.find("p", class_="font-800")
    if location_tag is not None:
        text = location_tag.get_text(" ", strip=True)
        if text.lower().startswith("currently"):
            text = text[len("currently") :].strip()
        current_location = text or None

    deviation: str | None = None
    time_stamp: str | None = None
    badge = anchor.find("span", class_="badge")
    if badge is not None:
        deviation, time_stamp = _parse_badge(badge.get_text(" ", strip=True))

    routenumber: int | None = None
    if current_route and "-" in current_route:
        head = current_route.split("-", 1)[0]
        if head.isdigit():
            routenumber = int(head)

    return {
        "current_route": current_route,
        "routerun": f"Rt {current_route}" if current_route else None,
        "routenumber": routenumber,
        "vehicle": vehicle,
        "gtfs_trip_headsign": headsign,
        "current_location": current_location,
        "deviation": deviation,
        "time_stamp": time_stamp,
        "position_time": params.get("position_time"),
        "bus_lat": _to_float(params.get("lat")),
        "bus_lon": _to_float(params.get("lon")),
        "exception": params.get("exception"),
        "colour": _bg_color(anchor),
    }


def parse(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, Any]] = []
    for anchor in soup.select('a[href^="/busLocate.asp"]'):
        row = _parse_anchor(anchor)
        if row is not None:
            rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("timetrack.json"),
        help="Output JSON path (default: timetrack.json). Use '-' for stdout.",
    )
    args = parser.parse_args()

    html = fetch()
    rows = parse(html)
    if not rows:
        # Don't overwrite good history with an empty array on a transient hiccup.
        print("ERROR: no entries parsed from timetrack_data.asp", file=sys.stderr)
        sys.stderr.write(html[:500] + "\n")
        return 1

    payload = json.dumps(rows, indent=2, ensure_ascii=False) + "\n"
    if str(args.output) == "-":
        sys.stdout.write(payload)
    else:
        args.output.write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
