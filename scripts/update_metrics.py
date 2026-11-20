"""Generate the profile dashboard using public GitHub data and Python's stdlib."""

import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from html import escape
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
import subprocess
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
USER = "liyouran0820"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif"


def gh(endpoint, payload=None):
    args = ["gh", "api", endpoint]
    if payload is not None:
        args += ["--input", "-"]
    result = subprocess.run(args, input=json.dumps(payload) if payload else None,
                            text=True, capture_output=True, check=True)
    data = json.loads(result.stdout)
    if data.get("errors") or data.get("incomplete_results"):
        raise RuntimeError("GitHub returned incomplete statistics; keeping the previous dashboard")
    return data


def graphql(query, **variables):
    return gh("graphql", {"query": query, "variables": {"user": USER, **variables}})["data"]["user"]


class ContributionCalendar(HTMLParser):
    """Parse the anonymous, publicly visible contribution calendar, never PAT-only data."""

    def __init__(self):
        super().__init__()
        self.dates, self.counts = {}, {}
        self.tooltip, self.words = None, []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("data-date") and attrs.get("id"):
            self.dates[attrs["id"]] = attrs["data-date"]
        if tag == "tool-tip":
            self.tooltip, self.words = attrs.get("for"), []

    def handle_data(self, text):
        if self.tooltip:
            self.words.append(text)

    def handle_endtag(self, tag):
        if tag == "tool-tip" and self.tooltip:
            match = re.search(r"^(No|[\d,]+) contributions? on\b", "".join(self.words).strip())
            if match:
                self.counts[self.tooltip] = 0 if match[1] == "No" else int(match[1].replace(",", ""))
            self.tooltip = None

    def days(self):
        return {day: self.counts[key] for key, day in self.dates.items() if key in self.counts}


def public_activity(today):
    first, last = today - timedelta(days=31), today - timedelta(days=1)
    values = {}
    for year in range(first.year, last.year + 1):
        url = f"https://github.com/users/{USER}/contributions?from={year}-01-01&to={year}-12-31"
        request = Request(url, headers={"User-Agent": "Newland-profile", "Accept-Language": "en-US"})
        with urlopen(request, timeout=45) as response:
            parser = ContributionCalendar()
            parser.feed(response.read().decode("utf-8"))
        values.update(parser.days())
    days = []
    for index in range(31):
        day = (first + timedelta(days=index)).isoformat()
        if day not in values:
            raise RuntimeError(f"Public contribution calendar is missing {day}; refusing to invent zeros")
        days.append({"date": day, "count": values[day]})
    return days


REPOSITORIES = """query($user:String!,$cursor:String){user(login:$user){
  followers{totalCount}
  repositories(first:100,after:$cursor,ownerAffiliations:OWNER,privacy:PUBLIC,isFork:false){
    pageInfo{hasNextPage endCursor} nodes{stargazerCount
      languages(first:100,orderBy:{field:SIZE,direction:DESC}){
        pageInfo{hasNextPage} edges{size node{name color}}
      }
    }
  }
}}"""
COMMITS = """query($user:String!,$year:DateTime!,$cursor:String){user(login:$user){
  contributionsCollection(from:$year){
    totalRepositoriesWithContributedCommits
    commitContributionsByRepository(maxRepositories:100){
      repository{nameWithOwner isPrivate}
      contributions(first:100,after:$cursor){nodes{commitCount} pageInfo{hasNextPage endCursor}}
    }
  }
}}"""
REVIEWS = """query($user:String!,$year:DateTime!,$cursor:String){user(login:$user){
  contributionsCollection(from:$year){pullRequestReviewContributions(first:100,after:$cursor){
    nodes{repository{isPrivate}} pageInfo{hasNextPage endCursor}
  }}
}}"""


def collect(today):
    stars, languages, colors, cursor = 0, Counter(), {}, None
    while True:
        user = graphql(REPOSITORIES, cursor=cursor)
        connection = user["repositories"]
        for repository in connection["nodes"]:
            stars += repository["stargazerCount"]
            if repository["languages"]["pageInfo"]["hasNextPage"]:
                raise RuntimeError("A repository has over 100 languages; extend language pagination first")
            for edge in repository["languages"]["edges"]:
                name = edge["node"]["name"]
                languages[name] += edge["size"]
                colors[name] = edge["node"]["color"] or "#8499aa"
        if not connection["pageInfo"]["hasNextPage"]:
            break
        cursor = connection["pageInfo"]["endCursor"]
    followers = user["followers"]["totalCount"]
    year = f"{today.year}-01-01T00:00:00Z"
    collection = graphql(COMMITS, year=year, cursor=None)["contributionsCollection"]
    if collection["totalRepositoriesWithContributedCommits"] > 100:
        raise RuntimeError("Annual commits span over 100 repositories; keeping the previous dashboard")
    commits = 0
    for repository in collection["commitContributionsByRepository"]:
        if repository["repository"]["isPrivate"]:
            continue
        connection = repository["contributions"]
        while True:
            commits += sum(node["commitCount"] for node in connection["nodes"])
            if not connection["pageInfo"]["hasNextPage"]:
                break
            page = graphql(COMMITS, year=year, cursor=connection["pageInfo"]["endCursor"])
            candidates = page["contributionsCollection"]["commitContributionsByRepository"]
            connection = next(r["contributions"] for r in candidates
                              if r["repository"]["nameWithOwner"] == repository["repository"]["nameWithOwner"])
    reviews, cursor = 0, None
    while True:
        connection = graphql(REVIEWS, year=year, cursor=cursor)["contributionsCollection"]["pullRequestReviewContributions"]
        reviews += sum(not n["repository"]["isPrivate"] for n in connection["nodes"])
        if not connection["pageInfo"]["hasNextPage"]:
            break
        cursor = connection["pageInfo"]["endCursor"]
    totals = {}
    for name, kind in (("prs", "pr"), ("issues", "issue")):
        # Search visibility is explicit even if the local gh login can read private repositories.
        totals[name] = gh(f"search/issues?q=author%3A{USER}+is%3A{kind}+is%3Apublic&per_page=1")["total_count"]
    return {"user": USER, "as_of": today.isoformat(), "year": today.year,
            "stars": stars, "commits": commits, "reviews": reviews, "followers": followers, **totals,
            "languages": [{"name": name, "bytes": size, "color": colors[name]}
                          for name, size in languages.most_common() if size > 0],
            "days": public_activity(today)}


def rank(data):
    """Adapted from github-readme-stats calculateRank, under scripts/rank-LICENSE.txt."""
    cdf = lambda x: 1 - 2 ** -x
    score = (2 * cdf(data["commits"] / 250) + 3 * cdf(data["prs"] / 50)
             + cdf(data["issues"] / 25) + cdf(data["reviews"] / 2)
             + 4 * data["stars"] / (50 + data["stars"])
             + data["followers"] / (10 + data["followers"])) / 12
    percentile = max(0, min(100, (1 - score) * 100))
    labels = zip((1, 12.5, 25, 37.5, 50, 62.5, 75, 87.5, 100),
                 ("S", "A+", "A", "A-", "B+", "B", "B-", "C+", "C"))
    return next(label for limit, label in labels if percentile <= limit), score


def text(x, y, value, size=22, color="#edf4ff", **attrs):
    extra = " ".join(f'{key.replace("_", "-")}="{escape(str(val), quote=True)}"' for key, val in attrs.items())
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" {extra}>{escape(str(value))}</text>'


def panel(x, y, width, height, green=False):
    return (f'<rect x="{x+1}" y="{y+1}" width="{width-2}" height="{height-2}" rx="24" '
            f'fill="url(#{"green" if green else "blue"})" stroke="{"#34554f" if green else "#394c6c"}"/>')


def svg(width, height, body, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title">'
            f'<title id="title">{escape(title)}</title><defs>'
            '<linearGradient id="blue" x2="1" y2="1"><stop stop-color="#152a48"/>'
            '<stop offset="1" stop-color="#161d35"/></linearGradient>'
            '<linearGradient id="green" x2="1" y2="1"><stop stop-color="#123a35"/>'
            '<stop offset="1" stop-color="#162d31"/></linearGradient>'
            '<linearGradient id="area" x2="0" y2="1"><stop stop-color="#78cfb0" stop-opacity=".22"/>'
            '<stop offset="1" stop-color="#78cfb0" stop-opacity="0"/></linearGradient></defs>'
            f'<g font-family="{FONT}">{body}</g></svg>\n')


def stats(data, mobile=False):
    width, height, card_width = (720, 744, 720) if mobile else (1200, 360, 584)
    ox, oy = (0, 384) if mobile else (616, 0)
    body = panel(0, 0, card_width, 360)
    body += text(32, 52, "GitHub Stats", 30, "#c2d9ff", font_weight=600)
    body += text(32, 86, f'公开贡献 · {data["year"]}', 18, "#9fafd0")
    for i, (name, value) in enumerate((("Stars", data["stars"]), (f'Commits ({data["year"]})', data["commits"]),
                                        ("PRs", data["prs"]), ("Issues", data["issues"]))):
        y = 140 + i * 51
        body += text(32, y, name, 23) + text(302 if mobile else 285, y, f"{value:,}", 25, text_anchor="end")
    label, score = rank(data)
    cx, cy, radius = (548 if mobile else 450), 214, 75
    circumference = 2 * math.pi * radius
    body += (f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="#34465f" stroke-width="8"/>'
             f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="#97badf" stroke-width="8" '
             f'stroke-dasharray="{score*circumference:.2f} {circumference:.2f}" transform="rotate(-90 {cx} {cy})"/>')
    body += text(cx, cy+16, label, 55, "#d0e2ff", text_anchor="middle", font_weight=500)
    body += text(cx, 324, "Readme Stats rank", 15, "#9fafd0", text_anchor="middle")
    body += panel(ox, oy, card_width, 360, green=True)
    body += text(ox+32, oy+52, "Top Languages", 30, "#c6e9d5", font_weight=600)
    body += text(ox+32, oy+86, "公开自有仓库 · 按代码量", 18, "#9dbeaf")
    languages = list(data["languages"])
    if len(languages) > 6:
        languages = languages[:5] + [{"name": "Other", "bytes": sum(r["bytes"] for r in languages[5:]), "color": "#8caaa6"}]
    total = sum(r["bytes"] for r in languages)
    if not total:
        body += text(ox+32, oy+185, "暂无公开代码语言数据", 22, "#9dbeaf")
        return svg(width, height, body, "GitHub 公开贡献统计与语言占比")
    x, bar_width = ox+32, card_width-64
    body += f'<clipPath id="language-bar"><rect x="{x}" y="{oy+116}" width="{bar_width}" height="14" rx="7"/></clipPath><g clip-path="url(#language-bar)">'
    for row in languages:
        segment = row["bytes"] / total * bar_width
        body += f'<rect x="{x:.3f}" y="{oy+116}" width="{segment:.3f}" height="14" fill="{row["color"]}"/>'
        x += segment
    body += "</g>"
    for i, row in enumerate(languages):
        x, y = ox+32+(i % 2)*(card_width-64)/2, oy+190+(i//2)*53
        body += f'<circle cx="{x+5}" cy="{y-7}" r="5" fill="{row["color"]}"/>'
        name = row["name"] if len(row["name"]) <= 14 else row["name"][:13] + "…"
        body += text(x+19, y, f'{name} · {row["bytes"]/total*100:.1f}%', 19, "#e5f4ed")
    return svg(width, height, body, "GitHub 公开贡献统计、评级与公开自有仓库语言占比")


def activity(data, mobile=False):
    width, height = (720, 350) if mobile else (1200, 310)
    left, right, top, bottom = 65, width-32, 126, height-58
    days = data["days"]
    peak = max(3, math.ceil(max(d["count"] for d in days) / 3) * 3)
    body = panel(0, 0, width, height, green=True)
    body += text(32, 49, "Activity · last 31 days", 28, "#c6e9d5", font_weight=600)
    body += text(32, 82, f'{days[0]["date"]} — {days[-1]["date"]}', 17, "#9dbeaf")
    body += text(width-32, 49, f'{sum(d["count"] for d in days):,} contributions', 18, "#b2d5c6", text_anchor="end") if not mobile else ""
    for i in range(4):
        y = bottom - (bottom-top)*i/3
        body += f'<path d="M{left} {y:.2f}H{right}" stroke="#34554f"/>'
        body += text(left-14, y+5, f'{peak*i//3}', 15, "#9dbeaf", text_anchor="end")
    points = [(left+i*(right-left)/30, bottom-d["count"]/peak*(bottom-top)) for i, d in enumerate(days)]
    coords = " ".join(f'{x:.2f},{y:.2f}' for x, y in points)
    body += f'<polygon points="{left},{bottom} {coords} {right},{bottom}" fill="url(#area)"/>'
    body += f'<polyline points="{coords}" fill="none" stroke="#7bcdb4" stroke-width="3" stroke-linejoin="round"/>'
    for index in ((0, 10, 20, 30) if mobile else (0, 5, 10, 15, 20, 25, 30)):
        x, _ = points[index]
        anchor = "start" if index == 0 else "end" if index == 30 else "middle"
        body += text(x, height-24, days[index]["date"][5:], 18 if mobile else 16, "#9dbeaf", text_anchor=anchor)
    return svg(width, height, body, f'最近31个完整自然日的GitHub公开可见贡献，{days[0]["date"]}至{days[-1]["date"]}')


def tools(mobile=False):
    width, height = (720, 260) if mobile else (1200, 176)
    rows = (("Swift", "Python", "JavaScript", "C", "HTML", "CSS"), ("PHP", "MySQL", "Git", "macOS"))
    if mobile:
        rows = (("Swift", "Python", "JavaScript", "C"), ("HTML", "CSS", "PHP", "MySQL"), ("Git", "macOS"))
    body = panel(0, 0, width, height)
    body += text(32, 48, "Languages & Tools", 28, "#c2d9ff", font_weight=600)
    for i, row in enumerate(rows):
        x, y = 32, 93+i*47
        for name in row:
            chip_width = len(name)*12+30
            body += f'<rect x="{x}" y="{y-25}" width="{chip_width}" height="35" rx="8" fill="#233853"/>'
            body += text(x+15, y, name, 20, "#d8e5f5")
            x += chip_width+13
    return svg(width, height, body, "Languages and Tools: Swift, Python, JavaScript, C, HTML, CSS, PHP, MySQL, Git, macOS")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "assets/dashboard")
    args = parser.parse_args()
    data = collect(datetime.now(timezone.utc).date())
    files = {}
    for mobile in (False, True):
        suffix = "-mobile" if mobile else ""
        files[f"stats{suffix}.svg"] = stats(data, mobile)
        files[f"activity{suffix}.svg"] = activity(data, mobile)
        files[f"tools{suffix}.svg"] = tools(mobile)
    files["data.json"] = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    args.output.mkdir(parents=True, exist_ok=True)
    # Collection and rendering must both succeed before replacing any existing card.
    for name, content in files.items():
        (args.output / name).write_text(content, encoding="utf-8")
    print(f'Dashboard updated: {data["as_of"]}, {len(data["days"])} complete activity days, public aggregates only')


if __name__ == "__main__":
    main()
