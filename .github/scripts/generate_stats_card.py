#!/usr/bin/env python3
import datetime as dt
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from html import escape
from pathlib import Path


API = "https://api.github.com"
USERNAME = os.environ.get("STATS_USERNAME", "2218084076")
TOKEN = os.environ.get("GH_STATS_TOKEN", "")
OUTPUT = Path(os.environ.get("STATS_CARD_PATH", "profile/stats.svg"))


def request_json(url, *, data=None, accept="application/vnd.github+json"):
    if not TOKEN:
        raise RuntimeError("GH_STATS_TOKEN is not configured.")

    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "profile-stats-card",
    }
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def paged_get(path, params):
    page = 1
    items = []
    while True:
        query = dict(params)
        query.update({"per_page": 100, "page": page})
        url = f"{API}{path}?{urllib.parse.urlencode(query)}"
        batch = request_json(url)
        if not batch:
            return items
        items.extend(batch)
        if len(batch) < 100:
            return items
        page += 1
        time.sleep(0.2)


def search_count(query, search_type="issues", accept="application/vnd.github+json"):
    encoded = urllib.parse.urlencode({"q": query, "per_page": 1})
    data = request_json(f"{API}/search/{search_type}?{encoded}", accept=accept)
    return int(data.get("total_count", 0))


def commit_count():
    query = f"author:{USERNAME}"
    try:
        return search_count(
            query,
            search_type="commits",
            accept="application/vnd.github.cloak-preview+json",
        )
    except Exception as exc:
        print(f"Warning: commit search failed: {exc}", file=sys.stderr)
        return 0


def contribution_repo_count():
    now = dt.datetime.now(dt.timezone.utc)
    start = now - dt.timedelta(days=365)
    query = """
      query($login: String!, $from: DateTime!, $to: DateTime!) {
        user(login: $login) {
          contributionsCollection(from: $from, to: $to) {
            totalRepositoryContributions
          }
        }
      }
    """
    payload = {
        "query": query,
        "variables": {
            "login": USERNAME,
            "from": start.isoformat(),
            "to": now.isoformat(),
        },
    }
    try:
        data = request_json("https://api.github.com/graphql", data=payload)
        user = data.get("data", {}).get("user") or {}
        collection = user.get("contributionsCollection") or {}
        return int(collection.get("totalRepositoryContributions") or 0)
    except Exception as exc:
        print(f"Warning: contribution query failed: {exc}", file=sys.stderr)
        return 0


def collect_stats():
    repos = paged_get(
        "/user/repos",
        {
            "visibility": "all",
            "affiliation": "owner,collaborator,organization_member",
            "sort": "full_name",
            "direction": "asc",
        },
    )

    repo_count = len(repos)
    private_count = sum(1 for repo in repos if repo.get("private"))
    stars = sum(int(repo.get("stargazers_count") or 0) for repo in repos)
    authored_prs = search_count(f"author:{USERNAME} type:pr")
    merged_prs = search_count(f"author:{USERNAME} type:pr is:merged")
    issues = search_count(f"author:{USERNAME} type:issue")
    reviewed_prs = search_count(f"reviewed-by:{USERNAME} type:pr")
    merged_percentage = (merged_prs / authored_prs * 100) if authored_prs else 0

    return {
        "repositories": repo_count,
        "private_repositories": private_count,
        "stars": stars,
        "commits": commit_count(),
        "prs": authored_prs,
        "merged_prs_percentage": f"{merged_percentage:.2f} %",
        "issues": issues,
        "prs_reviewed": reviewed_prs,
        "contributed_to": contribution_repo_count(),
    }


def icon_svg(kind, x, y):
    icons = {
        "repo": (
            '<path d="M3 5.5h5l1.5 2H17v9H3z"/>'
            '<path d="M3 8h14"/>'
        ),
        "lock": (
            '<rect x="4" y="8" width="12" height="8" rx="1.5"/>'
            '<path d="M7 8V6a3 3 0 0 1 6 0v2"/>'
        ),
        "star": (
            '<path d="M10 2.8l2.1 4.3 4.7.7-3.4 3.3.8 4.7L10 13.6l-4.2 2.2.8-4.7-3.4-3.3 4.7-.7z"/>'
        ),
        "commit": (
            '<circle cx="10" cy="10" r="3.2"/>'
            '<path d="M2.5 10h4.3M13.2 10h4.3"/>'
        ),
        "pr": (
            '<circle cx="5" cy="4" r="2"/>'
            '<circle cx="5" cy="16" r="2"/>'
            '<circle cx="15" cy="16" r="2"/>'
            '<path d="M5 6v8M9 4h2a4 4 0 0 1 4 4v6"/>'
        ),
        "percent": (
            '<path d="M4 16L16 4"/>'
            '<circle cx="5.2" cy="5.2" r="1.8"/>'
            '<circle cx="14.8" cy="14.8" r="1.8"/>'
        ),
        "issue": (
            '<circle cx="10" cy="10" r="7"/>'
            '<path d="M10 5.8v5.2"/>'
            '<path d="M10 14.4h.01"/>'
        ),
        "review": (
            '<path d="M2.5 10s3-5 7.5-5 7.5 5 7.5 5-3 5-7.5 5-7.5-5-7.5-5z"/>'
            '<circle cx="10" cy="10" r="2.4"/>'
        ),
        "contrib": (
            '<rect x="4" y="4" width="12" height="9" rx="1.5"/>'
            '<path d="M7 16h6M10 13v3"/>'
        ),
    }
    return f'<g class="icon" transform="translate({x} {y})">{icons[kind]}</g>'


def render_svg(stats):
    rows = [
        ("repo", "Repositories:", stats["repositories"]),
        ("lock", "Private Repositories:", stats["private_repositories"]),
        ("star", "Total Stars Earned:", stats["stars"]),
        ("commit", "Total Commits:", stats["commits"]),
        ("pr", "Total PRs:", stats["prs"]),
        ("percent", "Merged PRs Percentage:", stats["merged_prs_percentage"]),
        ("issue", "Total Issues:", stats["issues"]),
        ("review", "PRs Reviewed:", stats["prs_reviewed"]),
        ("contrib", "Contributed to (last year):", stats["contributed_to"]),
    ]

    width = 520
    row_height = 25
    top = 66
    height = top + row_height * len(rows) + 28
    value_x = 330
    icon_x = 32
    label_x = 58

    row_markup = []
    for index, (icon, label, value) in enumerate(rows):
        y = top + index * row_height
        row_markup.append(
            icon_svg(icon, icon_x, y - 14) +
            f'<text x="{label_x}" y="{y}" class="label">{escape(label)}</text>'
            f'<text x="{value_x}" y="{y}" class="value">{escape(str(value))}</text>'
        )

    return f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title desc">
  <title id="title">Terry's Stats</title>
  <desc id="desc">GitHub statistics for {escape(USERNAME)}</desc>
  <style>
    .card {{ fill: #373f51; stroke: #e6edf3; stroke-width: 1; }}
    .title {{ fill: #e07a5f; font: 700 18px 'Segoe UI', Ubuntu, Sans-Serif; }}
    .label {{ fill: #f4d6b1; font: 700 14px 'Segoe UI', Ubuntu, Sans-Serif; }}
    .value {{ fill: #f4d6b1; font: 700 14px 'Segoe UI', Ubuntu, Sans-Serif; }}
    .icon {{ stroke: #f2cc8f; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; fill: none; }}
    .icon-fill {{ fill: #f2cc8f; stroke: none; }}
    .mark {{ fill: #222936; }}
    .ring {{ stroke: #e07a5f; stroke-width: 6; fill: #f4d6b1; }}
  </style>
  <rect class="card" x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="4.5"/>
  <text x="28" y="34" class="title">Terry's Stats</text>
  <circle class="ring" cx="430" cy="126" r="40"/>
  <text x="405" y="137" class="mark" style="font: 800 30px 'Segoe UI', Ubuntu, Sans-Serif;">GH</text>
  {''.join(row_markup)}
</svg>
"""


def main():
    stats = collect_stats()
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(render_svg(stats), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
