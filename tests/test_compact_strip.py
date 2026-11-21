"""Small, label-free edge overlay; mocked client only."""
import unittest


class CompactStripTests(unittest.TestCase):
    def test_compact_strip_is_flush_top_right_label_free_and_click_through(self):
        from test_live_addon import LiveAddonTests
        harness=LiveAddonTests('test_opt_in_pixel_render_and_disable_and_version')
        harness.setUp()
        harness.do('''
local original=CreateFrame
function CreateFrame(...)
 local f=original(...)
 function f:EnableMouse(v) self.mouseEnabled=v end
 return f
end
SlashCmdList.FOREVERCONTEXT('live on')
local L=ForeverContext.Live
assert(L.frame.width==256 and L.frame.height==36, 'compact overlay must be 256x36')
assert(L.frame.point[1]=='TOPRIGHT' and L.frame.point[3]=='TOPRIGHT', 'overlay must be at right edge')
assert(L.frame.point[4]==0 and L.frame.point[5]==0, 'overlay must be flush with edge')
assert(L.frame.mouseEnabled==false, 'overlay must not intercept clicks')
assert(L.label==nil, 'no label below compact overlay')
for _,f in ipairs(frames) do assert(f.kind~='FontString', 'transmitter must not create text') end
for n,t in ipairs(L.cells) do
 assert(t.width==2 and t.height==2, 'compact cells must be 2x2')
 assert(t.point[4]==((n-1)%128)*2 and t.point[5]==-math.floor((n-1)/128)*2)
end
''')


if __name__=='__main__':
    unittest.main()
