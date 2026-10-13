#!/usr/bin/env python3
"""Build privacy-safe contribution SVGs from GitHub's public calendar only."""
from __future__ import annotations
import datetime as dt
import html
import json
import re
import sys
import urllib.request
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path

USER = "kawaiy"
OUT = Path("dist")
COLORS = {"dark": ("#0d1117", "#c9d1d9", "#8b949e", "#58a6ff", "#21262d"),
          "light": ("#ffffff", "#24292f", "#57606a", "#0969da", "#eaeef2")}

class CalendarParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.days = {}
        self.tips = {}
        self.target = None
        self.parts = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        date = a.get("data-date")
        if date and re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            self.days[a.get("id", date)] = (date, a.get("data-count"))
        if tag == "tool-tip":
            self.target = a.get("for")
            self.parts = []

    def handle_data(self, data):
        if self.target is not None:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "tool-tip" and self.target is not None:
            self.tips[self.target] = " ".join(self.parts)
            self.target = None

def obtain():
    url = f"https://github.com/users/{USER}/contributions"
    req = urllib.request.Request(url, headers={"User-Agent": "kawaiy-profile-graph/1.0", "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=25) as response:
        page = response.read().decode("utf-8")
    p = CalendarParser()
    p.feed(page)
    daily = {}
    for key, (date, inline_count) in p.days.items():
        tip = p.tips.get(key, "")
        match = re.search(r"([\d,]+)\s+contributions?\b", tip, re.I)
        if match:
            count = int(match.group(1).replace(",", ""))
        elif re.search(r"no contributions?\b", tip, re.I):
            count = 0
        elif inline_count is not None and inline_count.isdigit():
            count = int(inline_count)
        else:
            raise RuntimeError(f"GitHub daily count unavailable for {date}; refusing inaccurate chart")
        if date in daily and daily[date] != count:
            raise RuntimeError(f"Inconsistent contribution count: {date}")
        daily[date] = count
    if len(daily) < 350:
        raise RuntimeError(f"Expected at least 350 public-calendar days, got {len(daily)}")
    return sorted((dt.date.fromisoformat(k), v) for k, v in daily.items())

def esc(value):
    return html.escape(str(value), quote=True)

def svg(theme, entries):
    bg, fg, secondary, accent, panel = COLORS[theme]
    total = sum(v for _, v in entries)
    active = sum(v > 0 for _, v in entries)
    peak = max(v for _, v in entries)
    longest = 0
    streak = 0
    for _, value in entries:
        streak = streak + 1 if value else 0
        longest = max(longest, streak)
    # Today is still in progress: do not break streak on a zero today.
    latest = entries[-1][0]
    current = 0
    for date, value in reversed(entries[:-1] if latest == dt.datetime.now(dt.timezone.utc).date() and entries[-1][1] == 0 else entries):
        if not value:
            break
        current += 1

    monthly = defaultdict(int)
    for date, count in entries:
        monthly[date.strftime("%Y-%m")] += count
    labels = sorted(monthly)[-12:]
    vals = [monthly[k] for k in labels]
    maxval = max(vals) if vals else 1

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 850 340" width="850" height="340" role="img" aria-label="Contributions {total}; active days {active}; longest streak {longest} days; current streak {current} days">']
    parts += [f'<rect width="850" height="340" rx="16" fill="{bg}"/>',
              f'<text x="26" y="35" fill="{fg}" font-size="19" font-weight="bold" font-family="Arial,sans-serif">Contribution overview</text>',
              f'<text x="825" y="35" fill="{secondary}" font-size="12" text-anchor="end" font-family="Arial,sans-serif">Rolling 12 months · public calendar</text>']
    stats = [("Contributions", f"{total:,}"), ("Active days", str(active)), ("Longest streak", f"{longest} days"), ("Current streak", f"{current} days")]
    for i, (label, value) in enumerate(stats):
        x = 26 + i * 205
        parts += [f'<rect x="{x}" y="52" width="191" height="79" rx="10" fill="{panel}"/>',
                  f'<text x="{x+13}" y="77" fill="{secondary}" font-size="13" font-family="Arial,sans-serif">{esc(label)}</text>',
                  f'<text x="{x+13}" y="111" fill="{accent}" font-size="27" font-weight="bold" font-family="Arial,sans-serif">{esc(value)}</text>']
    parts.append(f'<text x="26" y="166" fill="{fg}" font-size="16" font-weight="bold" font-family="Arial,sans-serif">Monthly contributions</text>')
    for i, (month, value) in enumerate(zip(labels, vals)):
        x = 35 + i * 67
        h = round(110 * value / max(1, maxval))
        parts += [f'<rect x="{x}" y="{292-h}" width="34" height="{h}" rx="4" fill="{accent}"/>',
                  f'<text x="{x+17}" y="{285-h}" fill="{fg}" font-size="11" text-anchor="middle" font-family="Arial,sans-serif">{value}</text>',
                  f'<text x="{x+17}" y="312" fill="{secondary}" font-size="11" text-anchor="middle" font-family="Arial,sans-serif">{esc(month[5:])}</text>']
    parts += [f'<text x="825" y="330" text-anchor="end" fill="{secondary}" font-size="10" font-family="Arial,sans-serif">Anonymous public activity only · {esc(latest.isoformat())}</text>', '</svg>']
    return "\n".join(parts)

def main():
    entries = obtain()
    OUT.mkdir(exist_ok=True)
    for mode in ("dark", "light"):
        (OUT / f"overview-{mode}.svg").write_text(svg(mode, entries), encoding="utf-8")
    print(json.dumps({"days": len(entries), "total": sum(x[1] for x in entries), "end": entries[-1][0].isoformat()}))

if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        print(f"Graph generation failed safely: {ex}", file=sys.stderr)
        sys.exit(1)
