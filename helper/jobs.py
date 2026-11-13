"""Bounded network jobs. Private requests/results use pipes, never argv/env/files."""
import json
import os
import selectors
import subprocess
import sys
import time

MAX_OUTPUT = 16 * 1024 * 1024


def run_job(script, args, timeout, progress=None, cancelled=None, language="en"):
    process = subprocess.Popen([sys.executable, str(script), 'job'], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + timeout
    result = None
    incoming = bytearray()
    try:
        process.stdin.write((json.dumps({'args': args, 'language': language}) + '\n').encode())
        process.stdin.close()
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                if cancelled is not None and cancelled.is_set():
                    return {'ok': False, 'error': 'Mail operation was cancelled.'}
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return {'ok': False, 'error': 'Mail operation timed out; automatic polling will retry.'}
                for key, _ in selector.select(min(0.1, remaining)):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        break
                    incoming.extend(chunk)
                    if len(incoming) > MAX_OUTPUT:
                        return {'ok': False, 'error': 'Mail response exceeded the safe size limit.'}
                    while b'\n' in incoming:
                        line, _, rest = incoming.partition(b'\n')
                        incoming = bytearray(rest)
                        packet = json.loads(line)
                        if not isinstance(packet, dict):
                            raise ValueError('Invalid job response')
                        if packet.get('type') == 'progress':
                            if progress is not None:
                                progress()
                        else:
                            result = packet
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return {'ok': False, 'error': 'Mail operation timed out; automatic polling will retry.'}
        try:
            code = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            return {'ok': False, 'error': 'Mail operation timed out; automatic polling will retry.'}
        if incoming or result is None or code != 0 and result.get('ok') is True:
            return {'ok': False, 'error': 'Mail worker stopped without a complete response; polling will retry.'}
        return result
    except (OSError, ValueError, UnicodeError):
        return {'ok': False, 'error': 'Mail worker communication failed; automatic polling will retry.'}
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if not process.stdin.closed:
            process.stdin.close()
        process.stdout.close()
