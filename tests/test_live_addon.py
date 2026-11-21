"""Real Lua 5.1 transmitter tests. WoW fixtures exist only in tests."""
import json
from pathlib import Path
import struct
import unittest
import zlib

from lupa.lua51 import LuaRuntime
from test_addon import MOCK

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / 'addon' / 'ForeverContext'


class LiveAddonTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True, encoding=None)
        self.do(MOCK)
        self.do('''
local original=CreateFrame
function CreateFrame(...)
 local f=original(...)
 function f:CreateTexture() local t=CreateFrame('Texture'); self.children[#self.children+1]=t; return t end
 function f:SetSize(w,h) self.width=w; self.height=h end
 function f:SetPoint(...) self.point={...} end
 function f:SetScale(s) self.scale=s end
 function f:SetIgnoreParentScale(v) self.ignoreParentScale=v end
 function f:SetColorTexture(r,g,b,a) self.color={r,g,b,a} end
 return f
end
function GetPhysicalScreenSize() return 1920,1080 end
UIParent.GetHeight=function() return 720 end
UIParent.GetEffectiveScale=function() return .5 end
''')
        self.do((ADDON / 'Core.lua').read_text(encoding='utf-8'))
        live = ADDON / 'Live.lua'
        if live.exists():
            self.do(live.read_text(encoding='utf-8'))
        self.do((ADDON / 'UI.lua').read_text(encoding='utf-8'))

    def do(self, code):
        return self.lua.execute(code.encode('utf-8'))

    def build(self, payload, session=0x89ABCDEF, sequence=0xFEDCBA98, captured=1700000000):
        live = self.do('return ForeverContext.Live')
        self.assertIsNotNone(live, 'Live transmitter module must exist')
        return live[b'BuildFrames'](payload, session, sequence, captured)

    def test_wire_bytes_utf8_chunk_boundaries_and_both_checksums(self):
        payload = json.dumps({'capturedAt':1700000000, 'name':'é龍', 'tooltip':'x'*2300}, ensure_ascii=False).encode()
        frames = self.build(payload)
        count = (len(payload)+1047)//1048
        self.assertEqual(len(frames), count)
        for i in range(count):
            raw = frames[i+1]
            chunk = payload[i*1048:(i+1)*1048]
            header = struct.pack('>4sBBHIIHHIHHII', b'FCX1', 1, 0, 40,
                                 0x89ABCDEF, 0xFEDCBA98, i, count, len(payload),
                                 len(chunk), 0, zlib.adler32(payload), 1700000000)
            self.assertEqual(raw, header + struct.pack('>I', zlib.adler32(header+chunk)) + chunk)
        self.assertEqual(b''.join(frames[i+1][40:] for i in range(count)), payload)

    def test_opt_in_pixel_render_and_disable_and_version(self):
        self.do('''
local L=ForeverContext.Live
assert(not L.enabled and not L.frame)
SlashCmdList.FOREVERCONTEXT('live status')
assert(#messages==1 and messages[1]:find('off'))
messages={}
SlashCmdList.FOREVERCONTEXT('live on')
assert(L.enabled, 'live on must enable transmitter')
assert(ForeverContextDB.settings.liveEnabled==true)
assert(#messages==1)
assert(L.frame:IsShown() and L.frame.scripts.OnUpdate)
assert(L.frame.width==256 and L.frame.height==36)
assert(L.frame.ignoreParentScale and L.frame.scale==1/3)
assert(L.frame.point[1]=='TOPRIGHT' and L.frame.point[4]==0 and L.frame.point[5]==0)
assert(#L.cells==128*18)
assert(L.cells[1].color[1]==1 and L.cells[1].color[2]==0 and L.cells[1].color[3]==1)
assert(L.cells[2].color[1]==0 and L.cells[2].color[2]==1 and L.cells[2].color[3]==1)
for n=0,15 do assert(L.cells[9+n].color[1]==(8+16*n)/255) end
local raw=L.frames[1]
for i=1,1088 do
 local b=raw:byte(i) or 0
 assert(L.cells[128+i*2-1].color[1]==(8+16*math.floor(b/16))/255)
 assert(L.cells[128+i*2].color[1]==(8+16*(b%16))/255)
end
local index=L.index
L.frame.scripts.OnUpdate(L.frame,.05)
assert(L.index==index)
L.frame.scripts.OnUpdate(L.frame,.05)
assert(L.index~=index or #L.frames==1)
local session=L.session
SlashCmdList.FOREVERCONTEXT('live off')
assert(not L.enabled and not L.frame:IsShown() and L.frame.scripts.OnUpdate==nil)
assert(not ForeverContextDB.settings.liveEnabled and L.frames==nil)
SlashCmdList.FOREVERCONTEXT('live on')
assert(L.session~=session)
assert(#messages==3)
assert(ForeverContext.version=='1.1.3')
''')
        toc = (ADDON/'ForeverContext.toc').read_text()
        self.assertIn('## Version: 1.1.3', toc)
        self.assertLess(toc.index('Core.lua'), toc.index('Live.lua'))
        self.assertLess(toc.index('Live.lua'), toc.index('UI.lua'))

    def test_saved_opt_in_starts_at_login_silently_and_render_failure_stops(self):
        self.do('''
local L=ForeverContext.Live
ForeverContextDB={settings={liveEnabled=true,other='preserve'}}
local e=L.events
assert(e and e.events.PLAYER_LOGIN, 'Live must initialize after SavedVariables load')
e.scripts.OnEvent(e,'PLAYER_LOGIN')
assert(L.enabled and L.frame:IsShown())
assert(#messages==0 and ForeverContextDB.settings.other=='preserve')
ForeverContext.Stats=function() error('render-cycle capture failure') end
for i=1,#L.frames+1 do
 if L.frame.scripts.OnUpdate then L.frame.scripts.OnUpdate(L.frame,.1) end
end
assert(L.lastError:find('render%-cycle capture failure'))
assert(not L.frame:IsShown() and not L.frame.scripts.OnUpdate)
assert(#messages==0)
''')

    def test_scale_failure_is_silent_and_manual_retry_recovers(self):
        self.do('''
local L=ForeverContext.Live
GetPhysicalScreenSize=nil
SlashCmdList.FOREVERCONTEXT('live on')
assert(L.lastError and #messages==1)
assert(not L.frame:IsShown() and not L.frame.scripts.OnUpdate)
GetPhysicalScreenSize=function() return 1920,1080 end
messages={}
SlashCmdList.FOREVERCONTEXT('live on')
assert(not L.lastError, 'manual retry must finish initializing partial strip')
assert(L.frame:IsShown() and #L.cells==2304 and #messages==1)
''')

    def test_encoder_bounds_reject_partial_or_invalid_streams(self):
        self.build(b'x')
        for payload in (b'', b'x'*1048577, 123):
            with self.assertRaises(Exception):
                self.build(payload)
        for value in (-1, 4294967296, 1.5, float('nan')):
            with self.assertRaises(Exception):
                self.build(b'x', session=value)
        payload = b'z'*1048576
        frames = self.build(payload, session=0, sequence=0, captured=0)
        self.assertEqual(len(frames), 1001)
        self.assertEqual(b''.join(frames[i+1][40:] for i in range(len(frames))), payload)

    def test_stream_frozen_until_wrap_then_idle_recapture_and_error_stop(self):
        self.do('''
local L=ForeverContext.Live
assert(L, 'Live module required')
assert(L.Begin, 'Begin cycle helper required')
ForeverContext.Stats=function() return {large=string.rep('a',2500)} end
assert(L.Begin())
old=L.frames; oldSequence=L.sequence; oldCaptured=ForeverContext.last.capturedAt
first=L.NextFrame()
NOW=NOW+1
ForeverContext.Stats=function() return {large=string.rep('b',2500)} end
local f=ForeverContext.events; f.scripts.OnEvent(f,'BAG_UPDATE',0); RunTimers()
assert(L.frames==old, 'inventory events must not reset active stream')
for i=2,#old do assert(L.NextFrame()==old[i]) end
assert(first==old[1])
assert(L.NextFrame()~=old[1])
assert(L.sequence==oldSequence+1)
assert(ForeverContext.last.capturedAt==oldCaptured+1)
for i=2,#L.frames do L.NextFrame() end
ForeverContext.Stats=function() error('fresh capture failed') end
assert(L.NextFrame()==nil, 'failed fresh capture must not replay previous export')
assert(L.lastError:find('fresh capture failed'))
assert(L.frames==nil)
assert(#messages==0)
''')


if __name__ == '__main__':
    unittest.main()
