import json
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
from display_control import DisplayControl, ResetError
import settings

class DisplayReset(unittest.TestCase):
    def setUp(self):
        self.control = DisplayControl()
        self.address = '192.0.2.78:5555'
        self.ok = SimpleNamespace(returncode=0, stdout='')
        self.connected = SimpleNamespace(returncode=0, stdout='device\n')

    def test_reboot_only_after_connection_verified_and_no_duplicate(self):
        with patch('display_control.subprocess.run', side_effect=[self.ok, self.connected, self.ok]) as run:
            self.assertIn('sent', self.control.reset(self.address)['message'])
            self.assertEqual(run.call_args_list[-1].args[0], ['adb', '-s', self.address, 'reboot'])
            with self.assertRaises(ResetError): self.control.reset(self.address)
            self.assertEqual(run.call_count, 3)

    def test_failed_connect_with_zero_exit_never_reboots(self):
        with patch('display_control.subprocess.run', side_effect=[self.ok, SimpleNamespace(returncode=1, stdout='offline')]) as run:
            with self.assertRaisesRegex(ResetError, 'not connected'): self.control.reset(self.address)
            self.assertEqual(run.call_count, 2)

    def test_timeout_missing_adb_and_rejected_reboot(self):
        for error in (FileNotFoundError(), subprocess.TimeoutExpired('adb', 8), OSError()):
            with self.subTest(error=error), patch('display_control.subprocess.run', side_effect=error):
                with self.assertRaisesRegex(ResetError, 'Reset failed'): self.control.reset(self.address)
                self.assertFalse(self.control.lock.locked())
        with patch('display_control.subprocess.run', side_effect=[self.ok, self.connected, SimpleNamespace(returncode=1)]):
            with self.assertRaisesRegex(ResetError, 'did not accept'): self.control.reset(self.address)

    def test_invalid_target_and_concurrent_reset_never_run_adb(self):
        with patch('display_control.subprocess.run') as run:
            for address in ('', None, '-s x', '192.0.2.78:5555; reboot', '192.0.2.78:0'):
                with self.assertRaises(ResetError): self.control.reset(address)
            self.control.lock.acquire()
            with self.assertRaises(ResetError): self.control.reset(self.address)
            self.control.lock.release()
            run.assert_not_called()

    def test_http_protection_and_failure_response(self):
        store = settings.Settings(SimpleNamespace(config={'nook_adb_address': self.address}), '/unused')
        server = ThreadingHTTPServer(('127.0.0.1', 0), settings.make_handler(store))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        def request(method, body='{}', headers=None):
            connection = HTTPConnection(*server.server_address, timeout=2)
            connection.request(method, '/api/display/reset', body, headers or {'Content-Type':'application/json'})
            response = connection.getresponse()
            result = response.status, json.loads(response.read())
            connection.close()
            return result
        with patch.object(store.display, 'reset', side_effect=ResetError('Reset failed: offline')) as reset:
            self.assertEqual(request('GET')[0], 404)
            self.assertEqual(request('POST', headers={'Content-Type':'text/plain'})[0], 415)
            self.assertEqual(request('POST', headers={'Content-Type':'application/json','Origin':'http://elsewhere'})[0], 403)
            self.assertEqual(request('POST', '{"command":"reboot"}')[0], 400)
            reset.assert_not_called()
            status, body = request('POST')
            self.assertEqual(status, 503)
            self.assertEqual(body['error'], 'Reset failed: offline')
            reset.assert_called_once_with(self.address)
