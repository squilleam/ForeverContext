"""Opt-in, read-only WoW pixel companion. Never sends input or reads memory."""
from __future__ import annotations

import argparse
from collections import OrderedDict
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time
import uuid

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.live_protocol import Reassembler, ProtocolError, decode_image
from tools.read_snapshot import validate_snapshot, SnapshotError

LIVE_DIR = Path(__file__).resolve().parents[1] / 'data' / 'live'


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.fctx-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as handle:
            json.dump(value, handle, ensure_ascii=False, allow_nan=False)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


class CaptureState:
    def __init__(self, directory=LIVE_DIR, assembler=None, source_instance=None):
        self.directory = Path(directory)
        self.assembler = assembler if assembler is not None else Reassembler()
        self.source_instance = source_instance or uuid.uuid4().hex
        self.state, self.reason = 'waiting', 'Waiting for visible /fctx live on strip'
        self.last_frame_at = self.last_snapshot_at = None
        self.last_frame_mono = self.last_snapshot_mono = None
        self._seen = OrderedDict()
        self._completed = OrderedDict()
        self._last_write = -math.inf
        self._written_state = None

    def transition(self, state, reason):
        self.state, self.reason = state, reason

    def accept(self, frame, wall, mono):
        # Reassembler validates even duplicates/conflicting frames before health changes.
        payload = self.assembler.feed(frame, mono)
        previous = self._completed.get(frame.session)
        if previous is not None and (frame.sequence - previous) & 0xffffffff >= 0x80000000:
            self.refresh(mono)
            return False
        if previous == frame.sequence:
            self.refresh(mono)
            return False
        if payload is not None:
            self._completed[frame.session] = frame.sequence
            self._completed.move_to_end(frame.session)
            while len(self._completed) > 8:
                self._completed.popitem(last=False)
        key = (frame.session, frame.sequence)
        seen = self._seen.setdefault(key, set())
        novel = frame.chunk_index not in seen
        seen.add(frame.chunk_index)
        self._seen.move_to_end(key)
        while len(self._seen) > 16:
            self._seen.popitem(last=False)
        if novel:
            self.last_frame_at, self.last_frame_mono = wall, mono
            self.transition('receiving', 'Receiving validated snapshot chunks')
        if payload is None:
            self.refresh(mono)
            return False
        data = validate_snapshot(payload.decode('utf-8'))
        if data['capturedAt'] != frame.captured_at:
            raise SnapshotError('Header and snapshot capturedAt disagree')
        atomic_json(self.directory / 'current.json', {
            'bridgeVersion': 1, 'source': 'pixel', 'receivedAt': wall,
            'sourceInstance': self.source_instance, 'session': frame.session,
            'sequence': frame.sequence, 'snapshot': data})
        self.last_snapshot_at, self.last_snapshot_mono = wall, mono
        self.transition('connected', 'Complete validated snapshot received')
        # Publish matching health immediately: a strict MCP query may arrive before
        # the periodic heartbeat and must not reject a just-completed generation.
        self.write_status(wall, mono, force=True)
        return True

    def refresh(self, mono):
        if self.state in ('connected', 'receiving'):
            if self.last_frame_mono is None or mono - self.last_frame_mono > 3:
                self.transition('stale', 'No new valid frames within 3 seconds')
            elif self.last_snapshot_mono is not None and mono - self.last_snapshot_mono > 15:
                self.transition('stale', 'No complete snapshot within 15 seconds')
            elif self.last_snapshot_mono is not None:
                self.transition('connected', 'Complete snapshot and frames are recent')

    def write_status(self, wall, mono, force=False):
        signature = (self.state, self.reason)
        if force or signature != self._written_state or mono - self._last_write >= 1:
            atomic_json(self.directory / 'status.json', {
                'bridgeVersion': 1, 'updatedAt': wall, 'source': 'pixel',
                'sourceInstance': self.source_instance, 'state': self.state,
                'reason': self.reason, 'lastFrameAt': self.last_frame_at,
                'lastSnapshotAt': self.last_snapshot_at})
            if self._written_state is None or signature[0] != self._written_state[0]:
                print('ForeverContext: %s — %s' % signature, file=sys.stderr, flush=True)
            self._last_write, self._written_state = mono, signature


class WriterLock:
    """OS-held lock; released on process exit, without stale PID guessing."""
    def __init__(self, directory):
        self.directory = Path(directory)
        self.handle = None

    def __enter__(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        self.handle = (self.directory / 'capture.lock').open('a+b')
        self.handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.handle.close()
            self.handle = None
            raise RuntimeError('Another capture writer holds this live directory') from exc
        return self

    def __exit__(self, *_):
        if self.handle:
            self.handle.close()
            self.handle = None


class WindowsCapture:
    def __init__(self):
        if os.name != 'nt':
            raise RuntimeError('Live window discovery requires Windows')
        import ctypes
        from ctypes import wintypes as wt
        from mss import MSS
        self.ctypes, self.wt = ctypes, wt
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.user.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        self.user.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        self.user.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
        self.user.IsWindowVisible.argtypes = [wt.HWND]
        self.user.IsIconic.argtypes = [wt.HWND]
        self.user.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
        self.user.ClientToScreen.argtypes = [wt.HWND, ctypes.POINTER(wt.POINT)]
        self.callback_type = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
        self.user.EnumWindows.argtypes = [self.callback_type, wt.LPARAM]
        self.screen = MSS()

    def locate(self, hwnd=None):
        found = []
        def visit(handle, _):
            text = self.ctypes.create_unicode_buffer(512)
            self.user.GetWindowTextW(handle, text, len(text))
            if text.value == 'World of Warcraft':
                found.append(handle)
            return True
        self.user.EnumWindows(self.callback_type(visit), 0)
        if hwnd is None and len(found) > 1:
            raise RuntimeError('Multiple WoW windows; choose --hwnd from: ' + ', '.join(hex(x) for x in found))
        handle = hwnd if hwnd in found else (found[0] if hwnd is None and found else None)
        if handle is None:
            return 'window_missing', None
        if self.user.IsIconic(handle):
            return 'minimized', None
        if not self.user.IsWindowVisible(handle):
            return 'window_missing', None
        rect, origin = self.wt.RECT(), self.wt.POINT(0, 0)
        if not self.user.GetClientRect(handle, self.ctypes.byref(rect)) or not self.user.ClientToScreen(handle, self.ctypes.byref(origin)):
            raise OSError('Cannot obtain WoW client rectangle')
        client_width = rect.right - rect.left
        width, height = min(1024, client_width), min(320, rect.bottom - rect.top)
        if width <= 0 or height <= 0:
            return 'minimized', None
        # Compact transmitter is flush with the client's top-right edge.
        return 'visible', (origin.x + client_width - width, origin.y, width, height)

    def capture(self, rect):
        from PIL import Image
        x, y, width, height = rect
        shot = self.screen.grab({'left': x, 'top': y, 'width': width, 'height': height})
        return Image.frombytes('RGB', shot.size, shot.rgb)

    def close(self):
        self.screen.close()


def run_capture(directory=LIVE_DIR, backend=None, duration=None, once=False, hwnd=None):
    state = CaptureState(directory)
    backend = backend or WindowsCapture()
    geometry, last_rect = None, None
    next_search = 0
    start = time.monotonic()
    end = start + (15 if once and duration is None else duration) if once or duration is not None else math.inf
    completed = False
    try:
        with WriterLock(directory):
            try:
                while time.monotonic() < end:
                    tick = time.monotonic()
                    wall = time.time()
                    visibility, rect = backend.locate(hwnd)
                    if visibility != 'visible':
                        state.transition(visibility, 'WoW client is not visible for passive capture')
                        geometry = None
                    else:
                        if rect != last_rect:
                            geometry, next_search, last_rect = None, 0, rect
                        if geometry is not None or tick >= next_search:
                            try:
                                image = backend.capture(rect)
                                frame, geometry = decode_image(image, geometry)
                                completed = state.accept(frame, wall, tick) or completed
                            except ProtocolError:
                                geometry = None
                                next_search = tick + 1
                                state.transition('stale' if state.last_frame_at else 'waiting',
                                                 'Strip unavailable/corrupt/occluded; enable /fctx live on and keep visible')
                            except (SnapshotError, UnicodeError, RecursionError) as exc:
                                state.transition('error', str(exc))
                        state.refresh(tick)
                    state.write_status(wall, tick)
                    if once and completed:
                        break
                    time.sleep(max(0, 0.05 - (time.monotonic() - tick)))
            except KeyboardInterrupt:
                pass
            except Exception as exc:
                state.transition('error', str(exc))
                state.write_status(time.time(), time.monotonic(), force=True)
                raise
            finally:
                prior = state.state
                state.transition('stopped', 'Capture stopped (previous state: %s)' % prior)
                state.write_status(time.time(), time.monotonic(), force=True)
    finally:
        if hasattr(backend, 'close'):
            backend.close()
    return completed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true', help='Wait at most 15 seconds for one complete snapshot')
    parser.add_argument('--duration', type=float, help='Stop after this many seconds')
    parser.add_argument('--hwnd', type=lambda text: int(text, 0), help='Explicit WoW window handle (decimal or 0x hex)')
    parser.add_argument('--data-dir', type=Path, default=LIVE_DIR)
    args = parser.parse_args(argv)
    if args.duration is not None and (not math.isfinite(args.duration) or args.duration <= 0):
        parser.error('--duration must be positive and finite')
    try:
        completed = run_capture(args.data_dir, duration=args.duration, once=args.once, hwnd=args.hwnd)
        return 0 if completed or not args.once else 1
    except (RuntimeError, OSError) as exc:
        print('ForeverContext: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
