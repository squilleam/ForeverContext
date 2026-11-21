"""Mock Win32 geometry; screen capture must stay within the selected client."""
import ctypes
from ctypes import wintypes as wt
from types import SimpleNamespace
import unittest
from tools.live_capture import WindowsCapture


class CompactCaptureBoundsTests(unittest.TestCase):
    def test_top_right_region_uses_client_width_and_clamps_small_clients(self):
        for width,height in ((2560,1440),(400,100)):
            with self.subTest(size=(width,height)):
                def get_rect(handle,pointer):
                    rect=ctypes.cast(pointer,ctypes.POINTER(wt.RECT)).contents
                    rect.left=rect.top=0
                    rect.right,rect.bottom=width,height
                    return True
                def get_origin(handle,pointer):
                    point=ctypes.cast(pointer,ctypes.POINTER(wt.POINT)).contents
                    point.x,point.y=100,200
                    return True
                def get_title(handle,buffer,size):
                    buffer.value='World of Warcraft'
                    return len(buffer.value)
                backend=WindowsCapture.__new__(WindowsCapture)
                backend.ctypes,backend.wt=ctypes,wt
                backend.callback_type=lambda callback:callback
                backend.user=SimpleNamespace(
                    EnumWindows=lambda callback,param:callback(11,param),
                    GetWindowTextW=get_title,IsIconic=lambda handle:False,
                    IsWindowVisible=lambda handle:True,
                    GetClientRect=get_rect,ClientToScreen=get_origin)
                crop_width,crop_height=min(1024,width),min(320,height)
                self.assertEqual(backend.locate(11),('visible',
                    (100+width-crop_width,200,crop_width,crop_height)))


if __name__=='__main__':
    unittest.main()
