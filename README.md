# metrobus-timetrack-history

Tracking bus location data from https://www.metrobusmobile.com/timetrack.asp.

Every 5 minutes a GitHub Actions workflow runs [`scrape.py`](./scrape.py),
which fetches the HTML fragment served from
https://www.metrobusmobile.com/timetrack_data.asp, parses it with
BeautifulSoup, and writes the result to [`timetrack.json`](./timetrack.json).
If the file changed, the new version is committed, so every meaningful update
shows up as a commit in this repo.

> The old JSON API at `https://www.metrobus.co.ca/api/timetrack/json/` started
> returning 404, and the suggested replacement at
> `https://www.metrobustransit.ca/api/timetrack/json/` returns a server-side
> ASP error. Until/unless a real JSON or GTFS-RT endpoint reappears, we scrape
> the page that the mobile site itself uses.

## Running locally

The script is a [PEP 723](https://peps.python.org/pep-0723/) self-contained
[`uv`](https://docs.astral.sh/uv/) script — `uv` handles the Python version
and the `httpx` + `beautifulsoup4` dependencies for you:

```sh
uv run scrape.py                # writes ./timetrack.json
uv run scrape.py --output -     # prints JSON to stdout
```

Based on https://github.com/simonw/ca-fires-history.
