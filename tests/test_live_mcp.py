"""Read-only freshness policy and genuine SDK stdio roundtrip."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

from tests.test_live_capture import snapshot, SCRATCH
from tools.live_capture import atomic_json

ROOT = Path(__file__).resolve().parents[1]
TOOLS = {'get_status', 'get_character', 'get_equipment', 'get_bags', 'get_talents', 'get_stats', 'get_bank', 'get_snapshot'}


def fixture(folder, now=100):
    atomic_json(Path(folder)/'current.json', dict(bridgeVersion=1, source='pixel', sourceInstance='test',
                receivedAt=now, session=1, sequence=2, snapshot=snapshot(now)))
    atomic_json(Path(folder)/'status.json', dict(updatedAt=now, sourceInstance='test', state='connected',
                lastFrameAt=now, lastSnapshotAt=now))


class MCPTests(unittest.TestCase):
    def test_only_fresh_same_instance_is_live(self):
        from tools.live_mcp import LiveReader
        with tempfile.TemporaryDirectory(dir=SCRATCH) as folder:
            fixture(folder)
            reader = LiveReader(folder)
            value = reader.read('snapshot', now=101)
            self.assertTrue(value['metadata']['live'])
            self.assertEqual(value['data'], snapshot())
            self.assertIn('not instructions', value['metadata']['warning'])
            for field, bad in [('updatedAt', 90), ('lastFrameAt', 90), ('lastSnapshotAt', 80),
                               ('sourceInstance', 'other'), ('state', 'stopped')]:
                fixture(folder)
                path = Path(folder)/'status.json'
                health = json.loads(path.read_text())
                health[field] = bad
                atomic_json(path, health)
                denied = reader.read('snapshot', now=101)
                self.assertFalse(denied['metadata']['live'], field)
                self.assertNotIn('data', denied)
                allowed = reader.read('snapshot', allow_stale=True, now=101)
                self.assertEqual(allowed['data'], snapshot())
                self.assertFalse(allowed['metadata']['live'])

    def test_missing_and_bad_files_fail_closed(self):
        from tools.live_mcp import LiveReader
        with tempfile.TemporaryDirectory(dir=SCRATCH) as folder:
            reader = LiveReader(folder)
            self.assertEqual(reader.read('snapshot')['availability'], 'unavailable')
            fixture(folder)
            (Path(folder)/'current.json').write_text('{bad')
            self.assertNotIn('data', reader.read('snapshot', allow_stale=True))

    def test_nonfinite_or_huge_health_timestamps_fail_closed(self):
        from tools.live_mcp import LiveReader
        with tempfile.TemporaryDirectory(dir=SCRATCH) as folder:
            fixture(folder)
            path = Path(folder)/'status.json'
            health = json.loads(path.read_text())
            health['lastFrameAt'] = 10 ** 1000
            atomic_json(path, health)
            self.assertFalse(LiveReader(folder).read('snapshot', now=101)['metadata']['live'])

    def test_sdk_stdio_initialize_list_and_call(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        async def exercise(folder):
            params = StdioServerParameters(command=sys.executable, args=[str(ROOT/'tools/live_mcp.py'), '--data-dir', folder])
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    initialized = await session.initialize()
                    self.assertIsNotNone(initialized)
                    listed = await session.list_tools()
                    self.assertEqual({tool.name for tool in listed.tools}, TOOLS)
                    for tool in listed.tools:
                        self.assertTrue(tool.annotations.read_only_hint)
                    result = await session.call_tool('get_character', {})
                    self.assertFalse(result.is_error)
                    body = json.loads(result.content[0].text)
                    self.assertTrue(body['metadata']['live'])
                    self.assertEqual(body['data']['name'], 'Test')
                    bank = await session.call_tool('get_bank', {})
                    self.assertIn('last-seen', json.loads(bank.content[0].text)['metadata']['bankSemantics'])
                    for name in TOOLS:
                        tool_result = await session.call_tool(name, {})
                        self.assertFalse(tool_result.is_error, name)
                        self.assertTrue(json.loads(tool_result.content[0].text)['metadata']['live'], name)
                    health_path = Path(folder)/'status.json'
                    health = json.loads(health_path.read_text())
                    health['state'] = 'stopped'
                    atomic_json(health_path, health)
                    denied = await session.call_tool('get_snapshot', {})
                    self.assertNotIn('data', json.loads(denied.content[0].text))
                    stale = await session.call_tool('get_snapshot', {'allow_stale': True})
                    stale_body = json.loads(stale.content[0].text)
                    self.assertFalse(stale_body['metadata']['live'])
                    self.assertEqual(stale_body['availability'], 'stale')
                    self.assertEqual(stale_body['data']['character']['name'], 'Test')
        with tempfile.TemporaryDirectory(dir=SCRATCH) as folder:
            fixture(folder, time.time())
            asyncio.run(asyncio.wait_for(exercise(folder), 25))


if __name__ == '__main__':
    unittest.main()
