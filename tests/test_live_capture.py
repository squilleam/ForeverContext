"""Synthetic fixtures stay in explicit Hermes scratch, never runtime data."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

SCRATCH = Path(os.environ['TMPDIR'])


def snapshot(stamp=100):
    return dict(schemaVersion=1, capturedAt=stamp, character=dict(name='Test', realm='Test'),
                equipment=[], bags=[], talents=[], warnings=[], stats={},
                bank=dict(known=False, accessible=False, items=[]))


class CaptureTests(unittest.TestCase):
    def test_publishes_validated_atomic_envelope(self):
        from tools.live_capture import CaptureState
        class Assembly:
            def feed(self, frame, now):
                return json.dumps(snapshot()).encode()
        with tempfile.TemporaryDirectory(dir=SCRATCH) as folder:
            state = CaptureState(Path(folder), assembler=Assembly(), source_instance='test')
            frame = SimpleNamespace(session=1, sequence=2, chunk_index=0, payload=b'x', captured_at=100)
            self.assertTrue(state.accept(frame, wall=101, mono=1))
            envelope = json.loads((Path(folder)/'current.json').read_text())
            self.assertEqual(envelope['snapshot'], snapshot())
            self.assertEqual(envelope['source'], 'pixel')
            self.assertEqual(envelope['sourceInstance'], 'test')
            self.assertEqual(state.state, 'connected')

    def test_duplicate_and_replay_do_not_refresh(self):
        from tools.live_capture import CaptureState
        from tools.live_protocol import encode_frames, decode_frame
        with tempfile.TemporaryDirectory(dir=SCRATCH) as folder:
            state = CaptureState(folder)
            frame = decode_frame(encode_frames(json.dumps(snapshot()).encode(), 1, 2, 100)[0])
            self.assertTrue(state.accept(frame, 101, 1))
            self.assertFalse(state.accept(frame, 105, 5))
            self.assertEqual(state.last_frame_at, 101)
            self.assertEqual(state.state, 'stale')
            older = decode_frame(encode_frames(json.dumps(snapshot()).encode(), 1, 1, 100)[0])
            self.assertFalse(state.accept(older, 106, 6))
            self.assertEqual(state.last_frame_at, 101)

    def test_invalid_snapshot_preserves_complete_file(self):
        from tools.live_capture import CaptureState
        from tools.live_protocol import encode_frames, decode_frame
        with tempfile.TemporaryDirectory(dir=SCRATCH) as folder:
            state = CaptureState(folder)
            state.accept(decode_frame(encode_frames(json.dumps(snapshot()).encode(), 1, 1, 100)[0]), 101, 1)
            original = (Path(folder)/'current.json').read_bytes()
            bad = decode_frame(encode_frames(json.dumps(snapshot()).encode(), 1, 2, 99)[0])
            with self.assertRaises(ValueError):
                state.accept(bad, 102, 2)
            self.assertEqual((Path(folder)/'current.json').read_bytes(), original)

    def test_occlusion_never_recovers_without_new_frame(self):
        from tools.live_capture import CaptureState
        from tools.live_protocol import encode_frames, decode_frame
        with tempfile.TemporaryDirectory(dir=SCRATCH) as folder:
            state = CaptureState(folder)
            frame = decode_frame(encode_frames(json.dumps(snapshot()).encode(), 1, 1, 100)[0])
            state.accept(frame, 101, 1)
            state.transition('stale', 'Strip occluded')
            state.refresh(1.5)
            self.assertEqual(state.state, 'stale')
            state.accept(frame, 102, 2)
            self.assertEqual(state.state, 'stale')

    def test_image_cycle_publishes_and_missing_window_does_not(self):
        from tools.live_capture import run_capture
        from tools.live_protocol import encode_frames
        from tests.test_live_protocol import image_for
        data = snapshot()
        data['warnings'] = ['SYNTHETIC fixture ' * 200]
        frames = encode_frames(json.dumps(data).encode(), 4, 5, 100)
        class Backend:
            index = 0
            def locate(self, hwnd):
                return 'visible', (0, 0, 520, 80)
            def capture(self, rect):
                image = image_for(frames[self.index % len(frames)], offset=(8, 8))
                self.index += 1
                return image
        with tempfile.TemporaryDirectory(dir=SCRATCH) as folder:
            self.assertTrue(run_capture(folder, Backend(), duration=2, once=True))
            envelope = json.loads((Path(folder)/'current.json').read_text())
            self.assertEqual(envelope['snapshot'], data)
        class Missing:
            def locate(self, hwnd):
                return 'minimized', None
            def capture(self, rect):
                self.fail('Must not capture minimized window')
        with tempfile.TemporaryDirectory(dir=SCRATCH) as folder:
            self.assertFalse(run_capture(folder, Missing(), duration=0.1))
            self.assertFalse((Path(folder)/'current.json').exists())

    def test_waiting_loop_is_bounded_and_lock_is_exclusive(self):
        from tools.live_capture import run_capture, WriterLock
        from PIL import Image
        class Backend:
            def locate(self, hwnd):
                return 'visible', (0, 0, 768, 96)
            def capture(self, rect):
                return Image.new('RGB', (768, 96))
        with tempfile.TemporaryDirectory(dir=SCRATCH) as folder:
            with WriterLock(Path(folder)):
                with self.assertRaises(RuntimeError):
                    with WriterLock(Path(folder)):
                        pass
            self.assertFalse(run_capture(Path(folder), Backend(), duration=0.15))
            status = json.loads((Path(folder)/'status.json').read_text())
            self.assertEqual(status['state'], 'stopped')
            self.assertIsNone(status['lastFrameAt'])
            self.assertFalse((Path(folder)/'current.json').exists())


if __name__ == '__main__':
    unittest.main()
