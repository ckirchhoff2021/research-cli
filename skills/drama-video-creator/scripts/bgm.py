"""改进版BGM合成器：多层乐器（古筝+竹笛+低音+弦乐pad+鼓点），更丰富的旋律和动态。"""
from __future__ import annotations
import numpy as np
import scipy.io.wavfile as wav

def gen_gufeng(path, dur, duck_ranges, sr=44100):
    """古风武侠BGM：古筝琶音+竹笛旋律+古琴低音+弦乐铺底+轻鼓点。"""
    t = np.linspace(0, dur, int(sr*dur), endpoint=False)
    a = np.zeros_like(t)

    # 五声音阶 (D调: D E F# A B)
    pent_low = [73.42, 82.41, 92.50, 110.00, 123.47, 146.83, 164.81, 185.00, 220.00, 246.94]
    pent_mid = [293.66, 329.63, 369.99, 440.00, 493.88, 587.33, 659.25, 739.99, 880.00]
    pent_high = [587.33, 659.25, 739.99, 880.00, 987.77, 1174.66, 1318.51]

    def note(freq, start, dur_n, vol=0.03, attack=0.05, decay=2.0, harmonics=None):
        """Play a note with guzheng-like pluck envelope."""
        s = int(start*sr); e = int(min((start+dur_n)*sr, len(t)))
        if s >= len(t): return
        nt = np.linspace(0, (e-s)/sr, e-s, endpoint=False)
        an = int(min(attack, dur_n*0.3)*sr)
        dn = e - s - an
        env = np.concatenate([np.linspace(0,1,an), np.exp(-decay*np.linspace(0,4,dn))])[:e-s]
        if harmonics is None:
            harmonics = [(1,1.0),(2,0.5),(3,0.25),(4,0.12)]
        w = np.zeros(e-s)
        for mult, amp in harmonics:
            w += amp * np.sin(2*np.pi*freq*mult*nt)
        a[s:e] += vol * w * env

    def flute(freq, start, dur_n, vol=0.025, vibrato=5):
        """Bamboo flute note with vibrato."""
        s = int(start*sr); e = int(min((start+dur_n)*sr, len(t)))
        if s >= len(t): return
        nt = np.linspace(0,(e-s)/sr,e-s,endpoint=False)
        an=int(0.15*sr); dn=e-s-an
        env=np.concatenate([np.linspace(0,1,an),np.ones(max(dn-int(0.1*sr),1))*0.8,np.linspace(0.8,0,int(0.1*sr))])[:e-s]
        vib = 1 + 0.003*np.sin(2*np.pi*vibrato*nt)
        w = np.sin(2*np.pi*freq*nt*vib) + 0.3*np.sin(2*np.pi*freq*2*nt*vib) + 0.1*np.sin(2*np.pi*freq*3*nt*vib)
        a[s:e] += vol * w * env

    def drum_hit(start, vol=0.08):
        """Low drum/pad hit for punctuation."""
        s = int(start*sr); bl = int(0.4*sr)
        if s+bl >= len(t): return
        bt = np.linspace(0,0.4,bl)
        be = np.exp(-12*bt)
        a[s:s+bl] += vol*np.sin(2*np.pi*70*bt)*be + vol*0.5*np.sin(2*np.pi*100*bt)*np.exp(-20*bt)

    # String pad (sustained low notes, gentle)
    for f in [73.42, 110.0, 146.83]:
        a += 0.012*np.sin(2*np.pi*f*t)*(0.7+0.3*np.sin(2*np.pi*0.1*t))

    # Guzheng arpeggios (continuous background plucks)
    arp_pattern = [(0,5),(4,3),(7,4),(5,2),(4,3),(2,5),(0,3),(2,4),
                   (5,4),(7,3),(9,5),(7,2),(5,3),(4,4),(2,3),(0,5)]
    cur = 2.0
    arp_speed = 0.4
    for _ in range(int(dur/arp_speed)+5):
        ni, nd = arp_pattern[_ % len(arp_pattern)]
        f = pent_low[ni % len(pent_low)]
        note(f, cur, arp_speed*nd/4, vol=0.025, decay=3.0)
        # Add a higher octave pluck occasionally
        if _ % 4 == 0:
            note(f*2, cur+0.05, arp_speed*nd/5, vol=0.015, decay=4.0)
        cur += arp_speed * 0.6

    # Bamboo flute melody (main theme, more musical)
    melody = [
        (7,4),(9,3),(7,2),(5,4),(4,3),(5,2),(7,5),(9,4),
        (7,3),(5,2),(4,4),(2,3),(0,5),(2,4),(4,3),(5,6),
        (7,4),(5,3),(4,2),(5,4),(7,3),(9,5),(11,4),(9,3),
        (7,5),(5,3),(4,4),(2,6),(0,4),(2,3),(4,4),(5,7),
    ]
    cur = 4.0
    for ni, nd in melody:
        if cur >= dur - 8: break
        f = pent_high[ni % len(pent_high)]
        flute(f, cur, nd*0.55, vol=0.028, vibrato=5.5)
        # Echo
        if nd > 3:
            flute(f, cur+nd*0.3, nd*0.35, vol=0.012, vibrato=5)
        cur += nd*0.5

    # Bass guqin notes (emphasize beat)
    bass_notes = [(0,8),(5,6),(0,4),(4,6),(7,8),(5,4),(4,6),(0,8)]
    cur = 0.0
    bpi = 0
    while cur < dur - 4:
        ni, nd = bass_notes[bpi % len(bass_notes)]
        note(pent_low[ni]*0.5, cur, nd*0.6, vol=0.04, harmonics=[(1,1),(2,0.3)], decay=1.5)
        if bpi % 4 == 0:
            drum_hit(cur + nd*0.3, vol=0.04)
        cur += nd*0.5
        bpi += 1

    # Build volume envelope with ducking
    vol = np.ones(len(t)) * 0.4
    for s, e in duck_ranges:
        si, ei = int(s*sr), int(min(e*sr, len(t)))
        dl = ei - si
        if dl > 0:
            fd = int(0.5*sr); fu = int(0.8*sr)
            ramp_dn = np.linspace(1, 0.15, min(fd, dl))
            mid = np.ones(max(dl-fd-fu, 0)) * 0.15
            ramp_up = np.linspace(0.15, 1, min(fu, dl))
            env = np.concatenate([ramp_dn, mid, ramp_up])[:dl]
            vol[si:ei] *= env

    a *= vol
    # Fade in/out
    fi, fo = int(4*sr), int(6*sr)
    a[:fi] *= np.linspace(0, 1, fi)
    a[-fo:] *= np.linspace(1, 0, fo)
    # Normalize
    pk = np.max(np.abs(a))
    if pk > 0:
        a = a / pk * 0.45
    wav.write(path, sr, (a*32767).astype(np.int16))

def gen_bgm(path, dur, duck_ranges, sr=44100, style="gufeng"):
    if style in ("gufeng", "epic"):
        gen_gufeng(path, dur, duck_ranges, sr)
    else:
        # Fallback to simpler version for other styles
        t = np.linspace(0,dur,int(sr*dur),endpoint=False)
        a = 0.06*np.sin(2*np.pi*220*t)+0.04*np.sin(2*np.pi*330*t)
        # Simple ducking
        vol = np.ones(len(t))*0.3
        for s,e in duck_ranges:
            si,ei=int(s*sr),int(min(e*sr,len(t))); dl=ei-si
            if dl>0:
                env=np.concatenate([np.linspace(1,0.15,int(0.5*sr)),np.ones(max(dl-int(1.3*sr),0))*0.15,np.linspace(0.15,1,int(0.8*sr))])[:dl]
                vol[si:ei]*=env
        a*=vol
        fi,fo=int(4*sr),int(6*sr); a[:fi]*=np.linspace(0,1,fi); a[-fo:]*=np.linspace(1,0,fo)
        pk=np.max(np.abs(a)); a=a/pk*0.4 if pk>0 else a
        wav.write(path,sr,(a*32767).astype(np.int16))
