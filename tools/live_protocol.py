"""FCTX1 read-only pixel wire protocol. No capture, file IO or game controls."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
import math
import struct
import zlib

COLS=128
ROWS=18
CELL_SIZE=4
HEADER_SIZE=40
MAX_CHUNK_BYTES=1048
MAX_SNAPSHOT_BYTES=1048576
MAGIC=b'FCX1'
_HEADER=struct.Struct('>4sBBHIIHHIHHIII')


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class Frame:
    session: int
    sequence: int
    chunk_index: int
    chunk_count: int
    total_length: int
    payload: bytes
    snapshot_checksum: int
    captured_at: int


@dataclass(frozen=True)
class Geometry:
    x: float
    y: float
    cell_size: float


def _u32(value):
    return type(value) is int and 0 <= value <= 0xffffffff


def _validate(frame):
    if not all(_u32(x) for x in (frame.session,frame.sequence,frame.snapshot_checksum,frame.captured_at)):
        raise ProtocolError('Invalid uint32 field')
    if type(frame.total_length) is not int or not 0 < frame.total_length <= MAX_SNAPSHOT_BYTES:
        raise ProtocolError('Invalid snapshot length')
    expected=(frame.total_length+MAX_CHUNK_BYTES-1)//MAX_CHUNK_BYTES
    if type(frame.chunk_count) is not int or frame.chunk_count != expected:
        raise ProtocolError('Chunk count does not match total length')
    if type(frame.chunk_index) is not int or not 0 <= frame.chunk_index < expected:
        raise ProtocolError('Chunk index out of range')
    length=min(MAX_CHUNK_BYTES,frame.total_length-frame.chunk_index*MAX_CHUNK_BYTES)
    if not isinstance(frame.payload,bytes) or len(frame.payload) != length:
        raise ProtocolError('Chunk payload length mismatch')


def encode_frames(payload,session,sequence,captured_at):
    if not isinstance(payload,bytes) or not 0 < len(payload) <= MAX_SNAPSHOT_BYTES:
        raise ProtocolError('Payload must be nonempty bounded bytes')
    count=(len(payload)+MAX_CHUNK_BYTES-1)//MAX_CHUNK_BYTES
    checksum=zlib.adler32(payload)&0xffffffff
    out=[]
    for index in range(count):
        chunk=payload[index*MAX_CHUNK_BYTES:(index+1)*MAX_CHUNK_BYTES]
        frame=Frame(session,sequence,index,count,len(payload),chunk,checksum,captured_at)
        _validate(frame)
        head=_HEADER.pack(MAGIC,1,0,HEADER_SIZE,session,sequence,index,count,len(payload),len(chunk),0,checksum,captured_at,0)
        frame_sum=zlib.adler32(head[:36]+chunk)&0xffffffff
        out.append(head[:36]+struct.pack('>I',frame_sum)+chunk)
    return out


def decode_frame(raw):
    if not isinstance(raw,bytes) or not HEADER_SIZE <= len(raw) <= HEADER_SIZE+MAX_CHUNK_BYTES:
        raise ProtocolError('Invalid frame byte length')
    magic,version,flags,hlen,session,seq,index,count,total,plen,reserved,check,when,frame_sum=_HEADER.unpack(raw[:HEADER_SIZE])
    if (magic,version,flags,hlen,reserved) != (MAGIC,1,0,HEADER_SIZE,0):
        raise ProtocolError('Unsupported magic, version, flags or reserved fields')
    if plen > MAX_CHUNK_BYTES or len(raw) < HEADER_SIZE+plen:
        raise ProtocolError('Truncated frame')
    payload=raw[HEADER_SIZE:HEADER_SIZE+plen]
    result=Frame(session,seq,index,count,total,payload,check,when)
    _validate(result)
    if zlib.adler32(raw[:36]+payload)&0xffffffff != frame_sum:
        raise ProtocolError('Frame checksum mismatch')
    return result


@dataclass
class _Assembly:
    metadata: tuple
    last_progress: float
    parts: dict = field(default_factory=dict)


class Reassembler:
    """Two bounded generations; duplicate chunks never renew progress/freshness."""
    def __init__(self,timeout=20.0):
        self.timeout=timeout
        self.pending=OrderedDict()
        self.completed=OrderedDict()

    def feed(self,frame,now):
        if not isinstance(frame,Frame) or not isinstance(now,(int,float)) or not math.isfinite(now):
            raise ProtocolError('Invalid frame or monotonic time')
        _validate(frame)
        for key,value in list(self.pending.items()):
            if now-value.last_progress > self.timeout:
                del self.pending[key]
        previous=self.completed.get(frame.session)
        if previous is not None:
            advance=(frame.sequence-previous)&0xffffffff
            if advance==0 or advance>=0x80000000:
                return None
        key=(frame.session,frame.sequence)
        meta=(frame.chunk_count,frame.total_length,frame.snapshot_checksum,frame.captured_at)
        assembly=self.pending.get(key)
        if assembly is not None and assembly.metadata != meta:
            del self.pending[key]
            raise ProtocolError('Conflicting frame generation metadata')
        if assembly is None:
            while len(self.pending)>=2:
                self.pending.popitem(last=False)
            assembly=_Assembly(meta,now)
            self.pending[key]=assembly
        if frame.chunk_index in assembly.parts:
            if assembly.parts[frame.chunk_index] != frame.payload:
                del self.pending[key]
                raise ProtocolError('Conflicting duplicate chunk')
            return None
        assembly.parts[frame.chunk_index]=frame.payload
        assembly.last_progress=now
        if len(assembly.parts) != frame.chunk_count:
            return None
        result=b''.join(assembly.parts[i] for i in range(frame.chunk_count))
        del self.pending[key]
        if len(result) != frame.total_length or zlib.adler32(result)&0xffffffff != frame.snapshot_checksum:
            raise ProtocolError('Snapshot checksum mismatch')
        self.completed[frame.session]=frame.sequence
        self.completed.move_to_end(frame.session)
        while len(self.completed)>8:
            self.completed.popitem(last=False)
        # Do not let older incomplete frames later overwrite a completed generation.
        for old in list(self.pending):
            if old[0]==frame.session and ((old[1]-frame.sequence)&0xffffffff)>=0x80000000:
                del self.pending[old]
        return result


_ANCHORS=((255,0,255),(0,255,255),(255,255,0),(255,0,255),(0,0,0),(255,255,255),(0,255,255),(255,0,0))


class _GeometryError(ProtocolError):
    pass


def _color_matches(pixel,reference):
    # Hue/extreme tests tolerate capture color conversion; payload uses calibration.
    return all((p>160 if r==255 else p<100) for p,r in zip(pixel,reference))


def _decode_at(image,geometry):
    x,y,pitch=geometry.x,geometry.y,geometry.cell_size
    if (not all(isinstance(v,(int,float)) and math.isfinite(v) for v in (x,y,pitch)) or
            pitch<2 or pitch>8 or x<0 or y<0 or x+COLS*pitch>image.width or y+ROWS*pitch>image.height):
        raise _GeometryError('Strip geometry outside capture bounds')
    pixels=image.load()
    def cell(col,row):
        return pixels[math.floor(x+(col+0.5)*pitch),math.floor(y+(row+0.5)*pitch)][:3]
    if any(not _color_matches(cell(i,0),ref) for i,ref in enumerate(_ANCHORS)):
        raise _GeometryError('Strip anchors unavailable/occluded')
    palette=[cell(8+i,0) for i in range(16)]
    if any(sum(palette[i+1])-sum(palette[i])<6 for i in range(15)):
        raise _GeometryError('Invalid calibration row')
    distances=[sum((a-b)**2 for a,b in zip(palette[i],palette[i+1])) for i in range(15)]
    if min(distances)<16:
        raise _GeometryError('Calibration has insufficient contrast')
    tolerances=[]
    for i in range(16):
        neighbors=([distances[i-1]] if i else [])+([distances[i]] if i<15 else [])
        tolerances.append(max(9,min(neighbors)*0.22))
    cache={}
    def nibble(index):
        rgb=cell(index%COLS,1+index//COLS)
        if rgb not in cache:
            scores=[sum((a-b)**2 for a,b in zip(rgb,p)) for p in palette]
            value=min(range(16),key=scores.__getitem__)
            if scores[value]>tolerances[value]:
                raise ProtocolError('Pixel outside calibrated palette')
            cache[rgb]=value
        return cache[rgb]
    def byte(index):
        return (nibble(index*2)<<4)|nibble(index*2+1)
    header=bytes(byte(i) for i in range(HEADER_SIZE))
    if header[:4]!=MAGIC:
        raise ProtocolError('Pixel data magic mismatch')
    plen=int.from_bytes(header[24:26],'big')
    if plen>MAX_CHUNK_BYTES:
        raise ProtocolError('Pixel frame length out of bounds')
    raw=header+bytes(byte(i) for i in range(HEADER_SIZE,HEADER_SIZE+plen))
    return decode_frame(raw)


def decode_image(image,geometry=None):
    """Decode a small captured WoW region, calibrating grayscale and physical pitch.

    A screenshot is only transient input; this function stores nothing. Checksums
    are integrity checks, not authenticity or Blizzard approval.
    """
    if not hasattr(image,'size') or image.width>2048 or image.height>512:
        raise ProtocolError('Expected a bounded capture image')
    if image.mode!='RGB':
        image=image.convert('RGB')
    if geometry is not None:
        try:
            return _decode_at(image,geometry),geometry
        except _GeometryError:
            pass
    pixels=image.load()
    width=min(image.width,1024)
    height=min(image.height,320)
    # Scan transitions into the magenta anchor, not every possible payload origin.
    for y in range(height):
        x=0
        while x<width:
            if not _color_matches(pixels[x,y][:3],_ANCHORS[0]):
                x+=1
                continue
            start=x
            while x<width and _color_matches(pixels[x,y][:3],_ANCHORS[0]):
                x+=1
            run=x-start
            if run<2 or run>9:
                continue
            coarse=list(range(max(8,(run-1)*4),min(32,(run+1)*4)+1))
            pitches=[q/4 for q in coarse]
            # Fractional UI/client scaling need not be a quarter-pixel pitch.
            # Search finer only during acquisition; cached geometry is the fast path.
            pitches.extend(n/100 for n in range(max(200,(run-1)*100),min(800,(run+1)*100)+1) if n%25)
            for pitch in pitches:
                candidate=Geometry(start,y,pitch)
                try:
                    return _decode_at(image,candidate),candidate
                except ProtocolError:
                    continue
    raise ProtocolError('No valid FCTX1 strip; enable /fctx live on and keep it visible')
