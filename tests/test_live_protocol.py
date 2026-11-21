"""Synthetic protocol fixtures only; no fabricated runtime character data."""
import importlib
import unittest


def codec():
    try:
        return importlib.import_module('tools.live_protocol')
    except ModuleNotFoundError as exc:
        raise AssertionError('Missing live wire codec implementation') from exc


class WireTests(unittest.TestCase):
    def test_chunked_utf8_roundtrip_and_completed_replay_not_fresh(self):
        c=codec()
        payload=('SYNTHETIC Équipement — item:123:0:-77; '*150).encode('utf-8')
        frames=c.encode_frames(payload,session=123,sequence=7,captured_at=1795246716)
        self.assertGreater(len(frames),1)
        r=c.Reassembler()
        complete=None
        for i,raw in enumerate(reversed(frames)):
            value=r.feed(c.decode_frame(raw),now=i*0.05)
            if value is not None:
                self.assertIsNone(complete)
                complete=value
        self.assertEqual(complete,payload)
        for raw in frames:
            self.assertIsNone(r.feed(c.decode_frame(raw),now=2.0))


    def test_corruption_bounds_and_conflicting_generations_are_rejected(self):
        c=codec()
        from dataclasses import replace
        raw=c.encode_frames(b'x'*1500,session=2,sequence=9,captured_at=1795246716)
        for offset in (0,4,5,7,19,23,24,27,28,35,36,40,len(raw[0])-1):
            altered=bytearray(raw[0]); altered[offset]^=1
            with self.subTest(offset=offset),self.assertRaises(c.ProtocolError):
                c.decode_frame(bytes(altered))
        for payload in (b'',b'x'*(c.MAX_SNAPSHOT_BYTES+1)):
            with self.assertRaises(c.ProtocolError):
                c.encode_frames(payload,1,1,1)
        r=c.Reassembler()
        first=c.decode_frame(raw[0])
        self.assertIsNone(r.feed(first,0))
        with self.assertRaises(c.ProtocolError):
            r.feed(replace(first,captured_at=first.captured_at+1),0.1)

    def test_duplicates_do_not_extend_expiry_and_buffers_are_bounded(self):
        c=codec()
        raw=c.encode_frames(b'x'*1500,session=1,sequence=1,captured_at=1795246716)
        r=c.Reassembler()
        r.feed(c.decode_frame(raw[0]),0)
        r.feed(c.decode_frame(raw[0]),19)
        self.assertIsNone(r.feed(c.decode_frame(raw[1]),21))
        for seq in range(2,8):
            frame=c.decode_frame(c.encode_frames(b'z'*1500,1,seq,1795246716)[0])
            r.feed(frame,22+seq)
            self.assertLessEqual(len(r.pending),2)

    def test_full_snapshot_checksum_is_verified(self):
        c=codec()
        import struct,zlib
        frames=c.encode_frames(b'SYNTHETIC'*200,1,1,1795246716)
        r=c.Reassembler()
        with self.assertRaises(c.ProtocolError):
            for i,frame in enumerate(frames):
                altered=bytearray(frame)
                altered[28:32]=struct.pack('>I',99)
                altered[36:40]=struct.pack('>I',zlib.adler32(altered[:36]+altered[40:])&0xffffffff)
                r.feed(c.decode_frame(bytes(altered)),i*0.1)


def image_for(raw, cell_size=4, offset=(0,0), shift=0):
    from PIL import Image,ImageDraw
    import math
    anchors=[(255,0,255),(0,255,255),(255,255,0),(255,0,255),(0,0,0),(255,255,255),(0,255,255),(255,0,0)]
    w=math.ceil(offset[0]+128*cell_size)+3
    h=math.ceil(offset[1]+18*cell_size)+3
    image=Image.new('RGB',(w,h),(33,42,50))
    draw=ImageDraw.Draw(image)
    def cell(col,row,color):
        box=(math.floor(offset[0]+col*cell_size),math.floor(offset[1]+row*cell_size),math.floor(offset[0]+(col+1)*cell_size)-1,math.floor(offset[1]+(row+1)*cell_size)-1)
        draw.rectangle(box,fill=tuple(max(0,min(255,v+shift)) for v in color))
    for x in range(128):
        color=anchors[x] if x<8 else (8+16*(x-8),)*3 if x<24 else (0,0,0)
        cell(x,0,color)
    raw=raw+b'\x00'*(1088-len(raw))
    nibbles=[n for byte in raw for n in (byte>>4,byte&15)]
    for i,n in enumerate(nibbles):
        cell(i%128,1+i//128,(8+16*n,)*3)
    return image


class ImageTests(unittest.TestCase):
    def test_locates_and_decodes_calibrated_strip_at_different_scales(self):
        c=codec()
        payload=b'SYNTHETIC pixel payload '+bytes(range(256))*3
        raw=c.encode_frames(payload,session=11,sequence=3,captured_at=1795246716)[0]
        for pitch in (3,4,5.5,3.56,4.35):
            with self.subTest(pitch=pitch):
                image=image_for(raw,cell_size=pitch,offset=(12,9),shift=2)
                frame,geometry=c.decode_image(image)
                self.assertEqual(frame.payload,payload)
                # Rasterization can make nearby subpixel pitches observationally identical.
                self.assertAlmostEqual(geometry.cell_size,pitch,delta=0.02)
                again,same=c.decode_image(image,geometry)
                self.assertEqual(again,frame)
                self.assertEqual(same,geometry)

    def test_occlusion_and_bad_payload_are_not_valid_frames(self):
        c=codec()
        from PIL import ImageDraw
        raw=c.encode_frames(b'SYNTHETIC',session=1,sequence=1,captured_at=1795246716)[0]
        image=image_for(raw)
        ImageDraw.Draw(image).rectangle((0,0,120,5),fill=(30,40,50))
        with self.assertRaises(c.ProtocolError):
            c.decode_image(image)
        corrupt=bytearray(raw)
        corrupt[-1]^=1
        with self.assertRaises(c.ProtocolError):
            c.decode_image(image_for(bytes(corrupt)))


if __name__=='__main__':
    unittest.main()
