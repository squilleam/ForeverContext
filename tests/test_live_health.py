"""A complete generation must be immediately readable through strict MCP checks."""
import json
from pathlib import Path
import tempfile
import unittest
from tools.live_capture import CaptureState
from tools.live_protocol import encode_frames, decode_frame
from tools.live_mcp import LiveReader
from tests.test_live_capture import snapshot,SCRATCH


class HealthPublicationTests(unittest.TestCase):
    def test_completed_snapshot_publishes_matching_health_without_poll_delay(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as folder:
            state=CaptureState(folder,source_instance='SYNTHETIC')
            state.write_status(wall=100,mono=0,force=True)
            raw=encode_frames(json.dumps(snapshot(100)).encode(),12,1,100)[0]
            self.assertTrue(state.accept(decode_frame(raw),wall=100.1,mono=.1))
            # No outer-loop heartbeat call yet: a real query can arrive right here.
            response=LiveReader(folder).read('snapshot',now=100.11)
            self.assertTrue(response['metadata']['live'],response['metadata']['checks'])
            self.assertEqual(response['data']['character']['name'],'Test')


    def test_normal_generations_do_not_repeat_connected_log_messages(self):
        import contextlib,io
        with tempfile.TemporaryDirectory(dir=SCRATCH) as folder:
            state=CaptureState(folder,source_instance='SYNTHETIC')
            output=io.StringIO()
            with contextlib.redirect_stderr(output):
                for seq in (1,2):
                    raw=encode_frames(json.dumps(snapshot(100)).encode(),12,seq,100)[0]
                    state.accept(decode_frame(raw),wall=100+seq/10,mono=seq/10)
                    state.refresh(seq/10)
                    state.write_status(wall=100+seq/10,mono=seq/10,force=True)
            self.assertEqual(output.getvalue().count('ForeverContext: connected'),1)


if __name__=='__main__':
    unittest.main()
