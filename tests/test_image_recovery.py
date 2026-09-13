import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

from PIL import Image
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server'))
import panel_server as panel


def png():
    out = io.BytesIO()
    Image.new('L', (600, 800), 255).save(out, format='PNG')
    return out.getvalue()


class ImageRecovery(unittest.TestCase):
    def test_failure_cache_restart_and_corruption(self):
        body = png()
        with tempfile.TemporaryDirectory() as cache:
            config = {'mirror_url': 'http://renderer/today.png'}
            with patch.object(panel.urllib.request, 'urlopen', side_effect=OSError('offline')):
                renderer = panel.RenderedPages(config, cache)
            self.assertEqual(renderer.current(), b'')
            self.assertTrue(renderer.retrying)
            with patch.object(panel.urllib.request, 'urlopen', return_value=io.BytesIO(body)):
                renderer.refresh()
            self.assertFalse(renderer.retrying)
            self.assertEqual(renderer.cache_path.read_bytes(), body)
            with patch.object(panel.urllib.request, 'urlopen', return_value=io.BytesIO(body[:40])):
                renderer.refresh()
            self.assertEqual(renderer.current(), body)
            self.assertEqual(renderer.cache_path.read_bytes(), body)
            with patch.object(panel.urllib.request, 'urlopen', side_effect=OSError('offline')):
                restarted = panel.RenderedPages(config, cache)
            self.assertEqual(restarted.current(), body)
            with patch.object(restarted.settings_changed, 'wait', side_effect=InterruptedError) as sleep:
                with self.assertRaises(InterruptedError):
                    restarted.run_forever()
            sleep.assert_called_once_with(30)

    def test_empty_image_returns_retryable_http_error(self):
        renderer = Mock(config={})
        renderer.current.return_value = b''
        handler = object.__new__(panel.make_handler(renderer))
        handler.path = '/panel.png'
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler.do_GET()
        handler.send_response.assert_called_once_with(503)
        handler.send_header.assert_any_call('Retry-After', '30')


class GenerationRecovery(unittest.TestCase):
    def setUp(self):
        fake = types.ModuleType('epd_server')
        fake.DisplayServer = type('Base', (), {'regenerate': Mock()})
        spec = importlib.util.spec_from_file_location('retry_adapter', ROOT / 'upstream/retrying_server.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'epd_server': fake}):
            spec.loader.exec_module(module)
        self.server = module.DisplayServer()
        self.server.shutdown_event = Mock()
        self.server.shutdown_event.wait.return_value = False
        self.generate = fake.DisplayServer.regenerate

    def test_retries_then_succeeds(self):
        self.generate.side_effect = [RuntimeError('temporary'), RuntimeError('temporary'), ['today']]
        self.assertEqual(self.server.regenerate(only=['today']), ['today'])
        self.assertEqual([c.args[0] for c in self.server.shutdown_event.wait.call_args_list], [30, 60])
        self.assertTrue(self.generate.call_args.kwargs['force_refresh'])
        self.assertEqual(self.generate.call_args.kwargs['only'], ['today'])

    def test_bounded_failure(self):
        self.generate.side_effect = RuntimeError('persistent')
        with self.assertRaises(RuntimeError):
            self.server.regenerate()
        self.assertEqual(self.generate.call_count, 3)

    def test_shutdown_interrupts_retry(self):
        self.generate.side_effect = RuntimeError('failed')
        self.server.shutdown_event.wait.return_value = True
        with self.assertRaises(RuntimeError):
            self.server.regenerate()
        self.assertEqual(self.generate.call_count, 1)

    def test_skipped_page_is_not_failure(self):
        self.generate.return_value = []
        self.assertEqual(self.server.regenerate(), [])
        self.server.shutdown_event.wait.assert_not_called()

if __name__ == '__main__':
    unittest.main()
