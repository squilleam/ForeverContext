"""Execute Lua texture renderer -> Python image decoder -> schema validator.

This is mocked-client integration, never presented as a live game transfer.
"""
import json
import unittest
from PIL import Image,ImageDraw
from tools import live_protocol as codec
from tools.read_snapshot import validate_snapshot


class LivePipelineTests(unittest.TestCase):
    def test_lua_rendered_multiframe_snapshot_decodes_without_mixing_updates(self):
        from test_live_addon import LiveAddonTests
        harness=LiveAddonTests('test_opt_in_pixel_render_and_disable_and_version')
        harness.setUp()
        harness.do("ForeverContext.Stats=function() return {fixture='SYNTHETIC é龍 '..string.rep('x',4200)} end; SlashCmdList.FOREVERCONTEXT('live on')")
        live=harness.lua.globals().ForeverContext[b'Live']
        frames=live[b'frames']
        expected=b''.join(frames[i][40:] for i in range(1,len(frames)+1))
        self.assertGreater(len(frames),1)
        r=codec.Reassembler()
        geometry=None
        complete=None
        for frame_index in range(len(frames)):
            if frame_index:
                harness.do('ForeverContext.Live.frame.scripts.OnUpdate(ForeverContext.Live.frame,.1)')
            image=Image.new('RGB',(int(live[b'frame'][b'width']),int(live[b'frame'][b'height'])))
            draw=ImageDraw.Draw(image)
            cells=live[b'cells']
            for n in range(2304):
                color=cells[n+1][b'color']
                rgb=tuple(round(color[i]*255) for i in (1,2,3))
                texture=cells[n+1]
                x,y=int(texture[b'point'][4]),-int(texture[b'point'][5])
                w,h=int(texture[b'width']),int(texture[b'height'])
                draw.rectangle((x,y,x+w-1,y+h-1),fill=rgb)
            frame,geometry=codec.decode_image(image,geometry)
            result=r.feed(frame,now=frame_index*.1)
            if result is not None:
                self.assertIsNone(complete)
                complete=result
        self.assertEqual(complete,expected)
        data=validate_snapshot(complete.decode('utf-8'))
        self.assertIn('SYNTHETIC é龍',data['stats']['fixture'])
        self.assertEqual(data['addonVersion'],'1.1.3')
        self.assertEqual(json.loads(expected),data)


if __name__=='__main__':
    unittest.main()
