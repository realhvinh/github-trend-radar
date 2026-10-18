"""Weekly GitHub trend collector: weekly completed calendar-week stars, not lifetime stars.

Discovery: GitHub Trending (worldwide + chosen language pages). GitHub REST star
history API (2026-03-10) supplies calendar-week star additions. Results are a
ranked *candidate sample*, not a guaranteed global exhaustive top 10.
"""
from __future__ import annotations

import argparse
import csv
import html
import io
import json
import logging
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from .render import render_dashboard

ROOT = Path(__file__).resolve().parents[1]
API = 'https://api.github.com'
TRENDING = 'https://github.com/trending'
API_VERSION = '2026-03-10'
USER_AGENT = 'GitHubTrendRadar/1.0 (public trend research)'
LOG = logging.getLogger('github_trend_radar')
REPO_NAME = re.compile(r'^/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?$')
TREND_WEEK = re.compile(r'([\d,.]+)\s+stars?\s+this\s+week', re.I)

CATEGORY_RULES = [
    ('AI & Agents', ('llm', 'agent', 'mcp', 'model context protocol', 'inference', 'generative', 'diffusion', 'chatbot', 'transformer', 'rag', 'openai', 'ollama', 'machine learning', 'multimodal')),
    ('Security', ('security', 'pentest', 'malware', 'vulnerability', 'exploit', 'zero trust', 'cryptography', 'scanner')),
    ('Embedded & Systems', ('embedded', 'kernel', 'linux driver', 'firmware', 'rtos', 'microcontroller', 'network os', 'networking stack', 'ebpf', 'operating system')),
    ('Cloud & DevOps', ('kubernetes', 'devops', 'cloud', 'docker', 'terraform', 'container', 'observability', 'monitoring', 'deployment', 'infrastructure')),
    ('Data & Database', ('database', 'postgres', 'sql', 'vector db', 'data engineering', 'analytics', 'warehouse', 'etl')),
    ('Web & UI', ('frontend', 'react', 'vue', 'svelte', 'next.js', 'design system', 'web framework', 'css', 'component library')),
    ('Developer Tools', ('cli', 'terminal', 'developer tool', 'ide', 'editor', 'linter', 'compiler', 'debugger', 'testing framework', 'code generation')),
]


def clean(value: str | None) -> str:
    return ' '.join((value or '').split()).strip()


def parse_trending(text: str) -> list[dict]:
    """Parse GitHub's public trending listing, retaining sample delta only as fallback."""
    soup = BeautifulSoup(text, 'html.parser')
    results = []
    for article in soup.select('article.Box-row'):
        anchor = article.select_one('h2 a[href]')
        if anchor is None:
            continue
        href = (anchor.get('href') or '').split('?')[0]
        if not REPO_NAME.fullmatch(href):
            continue
        name = href.strip('/')
        desc_tag = article.select_one('p')
        lang_tag = article.select_one('[itemprop="programmingLanguage"]')
        weekly_text = clean(article.get_text(' ', strip=True))
        stars = TREND_WEEK.search(weekly_text)
        results.append({
            'name': name,
            'url': 'https://github.com/' + name,
            'description': clean(desc_tag.get_text(' ', strip=True)) if desc_tag else '',
            'language': clean(lang_tag.get_text(' ', strip=True)) if lang_tag else 'Unknown',
            'trending_week_stars': int(stars.group(1).replace(',', '').replace('.', '')) if stars else None,
            'candidate_sources': ['github-trending'],
        })
    return results


def classify(row: dict) -> str:
    combined = ' '.join([row.get('name') or '', row.get('description') or '', ' '.join(row.get('topics') or [])]).lower()
    for label, needles in CATEGORY_RULES:
        if any(needle in combined for needle in needles):
            return label
    return 'Other'


def previous_complete_week(now: datetime) -> tuple[datetime, datetime]:
    """Last completed Sunday 00:00 UTC to following Sunday 00:00 UTC."""
    now = now.astimezone(timezone.utc)
    current_sunday = (now - timedelta(days=(now.weekday() + 1) % 7)).replace(hour=0, minute=0, second=0, microsecond=0)
    return current_sunday - timedelta(days=7), current_sunday


def select_history(history: list, now: datetime) -> tuple[int | None, str | None]:
    """Match the completed calendar week; never silently use a partial week."""
    start, _ = previous_complete_week(now)
    # API's week boundaries aren't guaranteed UTC-aligned; permit +/- 24h drift.
    for item in history:
        try:
            week_date = datetime.fromtimestamp(int(item['week']), timezone.utc)
            count = int(item['total'])
        except (KeyError, ValueError, TypeError, OverflowError):
            continue
        if abs((week_date - start).total_seconds()) <= 24 * 3600 and count >= 0:
            return count, week_date.date().isoformat()
    return None, None


class Client:
    def __init__(self, token: str | None, timeout: int = 20):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': USER_AGENT,
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': API_VERSION,
        })
        self.token = token
        self.timeout = timeout

    def get(self, url: str, params: dict | None = None, accept_html: bool = False):
        headers = {'Accept': 'text/html,application/xhtml+xml'} if accept_html else {}
        # Send API token ONLY to api.github.com, never to github.com/trending.
        if self.token and url.startswith(API + '/') and not accept_html:
            headers['Authorization'] = 'Bearer ' + self.token
        for attempt in range(3):
            try:
                response = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
            except requests.RequestException as exc:
                if attempt == 2:
                    raise RuntimeError(f'Network error: {url} ({exc})') from exc
                time.sleep(1 + 2 * attempt)
                continue
            if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            if response.status_code >= 400:
                preview = clean(response.text)[:180]
                raise RuntimeError(f'HTTP {response.status_code} {url}: {preview}')
            return response.text if accept_html else response.json()
        raise RuntimeError(f'Unable to fetch: {url}')

    def candidates(self, languages: list[str], max_candidates: int, now: datetime) -> list[dict]:
        chosen: dict[str, dict] = {}
        for language in [''] + languages:
            if len(chosen) >= max_candidates:
                break
            url = TRENDING + ('/' + quote(language, safe='') if language else '')
            try:
                text = self.get(url, params={'since': 'weekly'}, accept_html=True)
                rows = parse_trending(text)
                if not rows:
                    LOG.warning('No repos parsed from GitHub Trending: %s', url)
                for row in rows:
                    key = row['name'].lower()
                    if key in chosen:
                        chosen[key]['candidate_sources'].append('trending:' + (language or 'global'))
                    elif len(chosen) < max_candidates:
                        chosen[key] = row
                        row['candidate_sources'] = ['trending:' + (language or 'global')]
            except RuntimeError as exc:
                LOG.warning('Trending discovery failed (%s): %s', language or 'global', exc)

        # The search API is a *fallback for candidate discovery*, not an alternative
        # definition of delta-stars. Its search-by-stars ranking is not our ranking.
        if len(chosen) < 10:
            since = (now - timedelta(days=90)).date().isoformat()
            LOG.warning('Trending returned <10 candidates; using Search API discovery fallback.')
            try:
                response = self.get(API + '/search/repositories', params={
                    'q': f'created:>={since} stars:>=50 fork:false archived:false',
                    'sort': 'stars', 'order': 'desc', 'per_page': min(100, max_candidates),
                })
                for item in response.get('items', []):
                    name = item.get('full_name', '')
                    if not name or name.lower() in chosen or len(chosen) >= max_candidates:
                        continue
                    chosen[name.lower()] = {
                        'name': name, 'url': item['html_url'],
                        'description': clean(item.get('description')),
                        'language': item.get('language') or 'Unknown',
                        'trending_week_stars': None,
                        'candidate_sources': ['github-search-recent'],
                    }
            except RuntimeError as exc:
                LOG.warning('Search fallback failed: %s', exc)
        LOG.info('Found %d candidate repositories', len(chosen))
        return list(chosen.values())

    def history(self, fullname: str) -> list[dict]:
        owner, name = fullname.split('/', 1)
        return self.get(f'{API}/repos/{quote(owner)}/{quote(name)}/stargazers/history', params={'per_page': 4})

    def metadata(self, fullname: str) -> dict:
        owner, name = fullname.split('/', 1)
        return self.get(f'{API}/repos/{quote(owner)}/{quote(name)}')


def calculate(client: Client, config: dict, now: datetime) -> dict:
    start, end = previous_complete_week(now)
    candidates = client.candidates(config['languages'], config['max_candidates'], now)
    if not candidates:
        raise RuntimeError('No candidates found; refusing to publish an empty leaderboard.')
    successes = 0
    api_rows = []
    for index, row in enumerate(candidates, 1):
        try:
            history = client.history(row['name'])
            weekly, matched_week = select_history(history, now)
            successes += 1
            if weekly is None:
                LOG.warning('No full-week data for %s; skipping', row['name'])
                continue
            enriched = dict(row)
            enriched['weekly_stars'] = weekly
            enriched['history_week_start'] = matched_week
            api_rows.append(enriched)
        except (RuntimeError, ValueError, TypeError) as exc:
            LOG.warning('Star history %d/%d %s: %s', index, len(candidates), row['name'], exc)

    if api_rows:
        basis = 'github-api-completed-calendar-week'
        rows = api_rows
    else:
        # If the new star-history endpoint is unavailable, still provide a useful
        # report; it MUST be explicitly labeled as a rolling-7-day approximation.
        rows = [dict(row, weekly_stars=row['trending_week_stars'])
                for row in candidates if row.get('trending_week_stars') is not None]
        if not rows:
            raise RuntimeError('Neither GitHub star history nor weekly Trending star counts are available.')
        basis = 'github-trending-rolling-week'
        LOG.warning('Using GitHub Trending rolling-week count, NOT completed calendar-week count.')

    rows = [r for r in rows if r['weekly_stars'] >= config.get('min_stars', 1)]
    rows.sort(key=lambda x: (-x['weekly_stars'], x['name'].lower()))
    if not rows:
        raise RuntimeError('No nonzero weekly star gains in the candidate set.')
    winners = rows[:config['top_n']]
    for idx, row in enumerate(winners, 1):
        row['rank'] = idx
        try:
            meta = client.metadata(row['name'])
            row['description'] = clean(meta.get('description')) or row['description']
            row['language'] = meta.get('language') or row['language']
            row['total_stars'] = meta.get('stargazers_count')
            row['topics'] = meta.get('topics') or []
            row['created_at'] = meta.get('created_at')
            row['url'] = meta.get('html_url') or row['url']
        except RuntimeError as exc:
            LOG.warning('Metadata unavailable for %s: %s', row['name'], exc)
            row['topics'] = []
            row['total_stars'] = None
        row['category'] = classify(row)
    if basis == 'github-api-completed-calendar-week':
        label = f'{start.date().isoformat()} → {(end - timedelta(days=1)).date().isoformat()}'
    else:
        label = f'Rolling 7 days, collected {now.date().isoformat()} (UTC)'
    return {
        'schema_version': 1,
        'week_id': start.date().isoformat(),
        'window': label,
        'collected_at': now.astimezone(timezone.utc).isoformat(),
        'basis': basis,
        'candidate_count': len(candidates),
        'history_api_success_count': successes,
        'ranked_candidate_count': len(rows),
        'methodology': 'Discovery via GitHub Trending (global + languages); sample ranking. Not a guaranteed worldwide exhaustive top ten.',
        'repos': winners,
    }


def markdown_report(report: dict) -> str:
    lines = [
        '# GitHub Trend Radar — Top 10', '',
        f'**Window:** {report["window"]}  ',
        f'**Metric:** {report["basis"]}  ',
        f'**Discovery candidates:** {report["candidate_count"]}  ',
        '**Scope:** Top of discovered repos; not a global census.', '',
        '| # | Repository | Weekly stars | Language | Category |',
        '|---:|---|---:|---|---|',
    ]
    for row in report['repos']:
        lang = (row.get('language') or 'Unknown').replace('|', '\\|')
        category = row.get('category', 'Other').replace('|', '\\|')
        lines.append(f'| {row["rank"]} | [{row["name"]}]({row["url"]}) | +{row["weekly_stars"]:,} | {lang} | {category} |')
    lines.extend(['', '## What these repositories do', ''])
    for row in report['repos']:
        lines.append(f'**{row["rank"]}. [{row["name"]}]({row["url"]})** — {row.get("description") or "No description provided."}')
        lines.append('')
    counts = Counter(r['category'] for r in report['repos'])
    lines += ['## Category signals', '', ', '.join(f'{k}: {v}' for k, v in counts.most_common()), '',
              '> Data is a discovered candidate sample. Stars measure attention, not quality.', '']
    return '\n'.join(lines)


def save(report: dict, root: Path = ROOT) -> list[Path]:
    week = report['week_id']
    paths = [root / 'data/weeks' / f'{week}.json', root / 'data/index.json',
             root / 'reports' / f'{week}.md', root / 'reports/latest.md',
             root / 'reports' / f'{week}.csv', root / 'docs/index.html']
    for p in paths:
        p.parent.mkdir(parents=True, exist_ok=True)
    report_json = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    paths[0].write_text(report_json, encoding='utf-8')

    index_path = paths[1]
    try:
        index = json.loads(index_path.read_text('utf-8')) if index_path.exists() else []
        if not isinstance(index, list):
            index = []
    except (ValueError, OSError):
        index = []
    index = [entry for entry in index if entry.get('week_id') != week]
    index.insert(0, report)
    index.sort(key=lambda item: item['week_id'], reverse=True)
    index = index[:104]  # 2 years embedded in dashboard; weekly raw JSON retained
    paths[1].write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    md = markdown_report(report)
    paths[2].write_text(md, encoding='utf-8')
    paths[3].write_text(md, encoding='utf-8')
    with paths[4].open('w', newline='', encoding='utf-8') as out:
        writer = csv.writer(out)
        writer.writerow(['rank', 'repo', 'weekly_stars', 'total_stars', 'language', 'category', 'url', 'description'])
        for r in report['repos']:
            writer.writerow([r['rank'], r['name'], r['weekly_stars'], r.get('total_stars'), r.get('language'), r.get('category'), r['url'], r.get('description')])
    paths[5].write_text(render_dashboard(index), encoding='utf-8')
    return paths


def load_config(path: Path) -> dict:
    config = json.loads(path.read_text('utf-8'))
    if not isinstance(config.get('languages'), list) or not isinstance(config.get('max_candidates'), int) or config['max_candidates'] < 10:
        raise ValueError('Invalid config.json: languages list and max_candidates >= 10 required')
    return config


def main(argv=None):
    parser = argparse.ArgumentParser(description='Build weekly GitHub star-growth leaderboard')
    parser.add_argument('--config', default=str(ROOT / 'config.json'))
    parser.add_argument('--root', default=str(ROOT))
    parser.add_argument('--demo', action='store_true', help='Generate demo/preview.html with synthetic sample data (no network)')
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    root = Path(args.root)
    if args.demo:
        from .render import demo_report
        demo_file = root / 'demo' / 'preview.html'
        demo_file.parent.mkdir(parents=True, exist_ok=True)
        demo_file.write_text(render_dashboard([demo_report()]), encoding='utf-8')
        LOG.info('Demo generated (fictional numbers): %s', demo_file)
        return 0
    config = load_config(Path(args.config))
    now = datetime.now(timezone.utc)
    client = Client(os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN'), config.get('request_timeout_seconds', 20))
    report = calculate(client, config, now)
    for path in save(report, root):
        LOG.info('Wrote %s', path.relative_to(root))
    LOG.info('Top: %s +%d (%s)', report['repos'][0]['name'], report['repos'][0]['weekly_stars'], report['basis'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
