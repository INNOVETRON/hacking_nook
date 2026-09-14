"""Bounded, explicit ADB reboot of the configured display; never queue a reboot."""
import ipaddress
import subprocess
import threading
import time


class ResetError(Exception):
    def __init__(self, message, status=503):
        super().__init__(message)
        self.status = status


class DisplayControl:
    def __init__(self):
        self.lock = threading.Lock()
        self.last_sent = None

    def reset(self, address):
        try:
            host, port = address.rsplit(':', 1)
            ipaddress.IPv4Address(host)
            if not port.isdigit() or not 1 <= int(port) <= 65535:
                raise ValueError()
        except (AttributeError, ValueError):
            raise ResetError('Reset failed: configure the Nook ADB address on the server.')
        if not self.lock.acquire(blocking=False):
            raise ResetError('A display reset is already in progress.', 409)
        try:
            if self.last_sent is not None and time.monotonic() - self.last_sent < 30:
                raise ResetError('A reboot was just sent. Wait 30 seconds before trying again.', 409)
            def adb(args, timeout):
                return subprocess.run(['adb'] + args, capture_output=True, text=True,
                                      timeout=timeout, check=False)
            # adb connect can return exit status 0 even when the connection fails.
            adb(['connect', address], 8)
            state = adb(['-s', address, 'get-state'], 4)
            if state.returncode != 0 or state.stdout.strip() != 'device':
                raise ResetError('Reset failed: Nook is asleep, off, or not connected. Wake it with the n button and try again.')
            result = adb(['-s', address, 'reboot'], 5)
            if result.returncode != 0:
                raise ResetError('Reset failed: the Nook did not accept the reboot command. Wake it and try again.')
            self.last_sent = time.monotonic()
            return {'message': 'Reboot command sent. The Nook is restarting.'}
        except FileNotFoundError:
            raise ResetError('Reset failed: ADB is not installed on the server.')
        except subprocess.TimeoutExpired:
            raise ResetError('Reset failed: the Nook did not respond in time. Reboot could not be confirmed; check the display before retrying.')
        except OSError:
            raise ResetError('Reset failed: the server could not run ADB.')
        finally:
            self.lock.release()
