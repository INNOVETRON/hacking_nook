import io
from pathlib import Path
import sys
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
from display_activity import DisplayActivity
import panel_server


class ActivityTests(unittest.TestCase):
    def test_restart_local_dates_and_sent_timer(self):
        zone = ZoneInfo('America/Edmonton')
        now = datetime(2026, 9, 16, 0, 15, tzinfo=zone).timestamp()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'history.json'
            activity = DisplayActivity(path)
            activity.record(3600, 'Fixed interval', now - 1800)
            activity.record(900, 'Temperature change', now)
            restored = DisplayActivity(path).snapshot('America/Edmonton', now)
            self.assertEqual([d['count'] for d in restored['days']], [1, 1])
            self.assertEqual(restored['next_fetch'], now + 900)
            self.assertEqual(restored['last_fetch']['seconds'], 900)
            self.assertEqual(restored['started_at'], activity.started_at)

    def test_retention_keeps_offline_last_fetch(self):
        with tempfile.TemporaryDirectory() as folder:
            activity = DisplayActivity(Path(folder) / 'history.json')
            activity.record(3600, 'Fixed', 1000000)
            snapshot = activity.snapshot('UTC', 2000000)
            self.assertEqual(snapshot['last_fetch']['at'], 1000000)
            self.assertEqual(snapshot['days'][0]['count'], 0)
            activity.record(900, 'New', 2000000)
            self.assertEqual(len(activity.events), 1)

    def handler(self, agent='NookPanel/0.1 (BNRV300)', body=b'image'):
        renderer = SimpleNamespace(config={'device_refresh_seconds': 1800}, current=lambda: body, activity=Mock())
        handler = object.__new__(panel_server.make_handler(renderer))
        handler.path = '/panel.png'
        handler.headers = {'User-Agent': agent}
        handler.wfile = io.BytesIO()
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        return handler, renderer

    def test_only_nook_success_counts_and_matches_header(self):
        handler, renderer = self.handler()
        handler.do_GET()
        handler.send_header.assert_any_call('X-Nook-Refresh-Seconds', '1800')
        self.assertEqual(renderer.activity.record.call_args.args[0], 1800)
        handler, renderer = self.handler(agent='Mozilla/5.0')
        handler.do_GET()
        renderer.activity.record.assert_not_called()

    def test_failed_delivery_does_not_count(self):
        handler, renderer = self.handler(body=b'')
        handler.do_GET()
        renderer.activity.record.assert_not_called()
        handler, renderer = self.handler()
        handler.wfile = Mock()
        handler.wfile.write.side_effect = BrokenPipeError
        with self.assertRaises(BrokenPipeError):
            handler.do_GET()
        renderer.activity.record.assert_not_called()


if __name__ == '__main__':
    unittest.main()
