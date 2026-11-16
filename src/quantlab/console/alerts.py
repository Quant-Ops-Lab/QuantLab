"""Original, locally generated alert tone. No cloud audio or API cost."""
from __future__ import annotations
from io import BytesIO
import math
import struct
import wave

def alert_wav(frequency:int=880,duration_ms:int=260)->bytes:
    if not 200<=frequency<=2000 or not 100<=duration_ms<=1000:raise ValueError('invalid sound')
    rate=16000; count=int(rate*duration_ms/1000)
    out=BytesIO()
    with wave.open(out,'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(rate)
        payload=bytearray()
        for i in range(count):
            # Soft envelope avoids a sharp click.
            env=min(i/160,1,(count-i)/240)
            val=int(16000*max(0,env)*math.sin(2*math.pi*frequency*i/rate))
            payload.extend(struct.pack('<h',val))
        w.writeframes(bytes(payload))
    return out.getvalue()
