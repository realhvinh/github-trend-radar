import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from src.radar import parse_trending, previous_complete_week, select_history, classify, calculate, save
from src.render import demo_report, render_dashboard

HTML = '''<article class="Box-row"><h2><a href="/myorg/agent-tool">myorg / agent-tool</a></h2>
<p>Experimental AI agent that works offline</p><span itemprop="programmingLanguage">Python</span>
<span class="float-sm-right">1,234 stars this week</span></article>'''


class FakeClient:
    def candidates(self, *_):
        return [{'name': f'org/repo{i}', 'url': f'https://github.com/org/repo{i}',
                 'language': 'Python', 'description': 'An agent toolkit',
                 'trending_week_stars': i * 11, 'candidate_sources': ['test']} for i in range(12)]

    def history(self, name):
        i = int(name.split('repo')[1])
        return [{'week': 1791072000, 'total': i * 100, 'days': [1]*7}]

    def metadata(self, name):
        return {'description': 'AI agents for testing', 'language': 'Python', 'topics': ['agent'],
                'stargazers_count': 2000, 'html_url': 'https://github.com/' + name}


class RadarTests(unittest.TestCase):
    def test_html_parsing(self):
        result = parse_trending(HTML)
        self.assertEqual(result[0]['name'], 'myorg/agent-tool')
        self.assertEqual(result[0]['trending_week_stars'], 1234)
        self.assertEqual(result[0]['language'], 'Python')

    def test_calendar_week(self):
        now = datetime(2026, 10, 12, 1, tzinfo=timezone.utc) # Monday
        start, end = previous_complete_week(now)
        self.assertEqual(start.date().isoformat(), '2026-10-04')
        self.assertEqual(end.date().isoformat(), '2026-10-11')

    def test_week_choice_never_choose_partial(self):
        now = datetime(2026, 10, 12, 1, tzinfo=timezone.utc)
        data = [
            {'week': int(datetime(2026, 10, 11, tzinfo=timezone.utc).timestamp()), 'total': 999},
            {'week': int(datetime(2026, 10, 4, tzinfo=timezone.utc).timestamp()), 'total': 25},
        ]
        self.assertEqual(select_history(data, now)[0], 25)

    def test_missing_returns_none(self):
        self.assertEqual(select_history([], datetime(2026,10,12,tzinfo=timezone.utc)), (None, None))

    def test_classification(self):
        self.assertEqual(classify({'name':'demo', 'description':'Linux kernel driver', 'topics':[]}), 'Embedded & Systems')

    def test_candidate_ranking_and_archive(self):
        now = datetime(2026, 10, 12, 1, tzinfo=timezone.utc)
        client = FakeClient()
        # align fixture dynamically with completed week to prevent stale epoch assumptions
        client.history = lambda name: [{'week': int(datetime(2026, 10, 4, tzinfo=timezone.utc).timestamp()), 'total': int(name.split('repo')[1]) * 100}]
        report = calculate(client, {'languages':[], 'max_candidates':20, 'top_n':10, 'min_stars':1}, now)
        self.assertEqual(report['repos'][0]['name'], 'org/repo11')
        self.assertEqual(report['repos'][0]['weekly_stars'], 1100)
        self.assertEqual(report['basis'], 'github-api-completed-calendar-week')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            save(report, root)
            self.assertTrue((root / 'docs/index.html').exists())
            self.assertTrue((root / 'reports/2026-10-04.csv').exists())
            save(report, root)
            self.assertEqual(len(json.loads((root/'data/index.json').read_text('utf8'))), 1)

    def test_rolling_fallback(self):
        class FailedClient(FakeClient):
            def history(self, _):
                raise RuntimeError('not enabled')
        report = calculate(FailedClient(), {'languages':[], 'max_candidates':20, 'top_n':10}, datetime(2026,10,12,tzinfo=timezone.utc))
        self.assertEqual(report['basis'], 'github-trending-rolling-week')
        self.assertEqual(report['repos'][0]['weekly_stars'], 121)

    def test_dashboard_escapes_embedded_tags(self):
        report = demo_report()
        report['repos'][0]['description'] = '</script><script>alert(1)</script>'
        body = render_dashboard([report])
        self.assertNotIn('</script><script>alert(1)', body)
        self.assertIn('DEMO', body)

if __name__ == '__main__':
    unittest.main()
