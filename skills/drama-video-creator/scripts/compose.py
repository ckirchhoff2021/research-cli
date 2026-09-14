"""最终合成：片头片尾 + 交叉淡入淡出 + BGM + 对白音轨精确对齐。"""
from __future__ import annotations
import os, subprocess, tempfile, numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import scipy.io.wavfile as wav
import imageio_ffmpeg
from moviepy import VideoFileClip, AudioFileClip, CompositeAudioClip

def gen_bgm(path, dur, duck_ranges, sr=44100, style="gufeng"):
    """Generate style-matched BGM with ducking during dialogue."""
    t = np.linspace(0, dur, int(sr*dur), endpoint=False)
    a = np.zeros_like(t)

    if style in ("gufeng", "epic"):
        pent = [65.41,82.41,98,130.81,146.83,164.81,196,220,261.63,293.66,329.63,392,440,523.25,587.33]
        base_vol = 0.05
        melody_vol = 0.04
        flute_notes = [392,440,523.25,587.33,659.25,587.33,523.25,440]
        a += base_vol*np.sin(2*np.pi*65.41*t)+0.04*np.sin(2*np.pi*98*t)+0.02*np.sin(2*np.pi*130.81*t)
    elif style in ("business", "bright"):
        pent = [261.63,293.66,329.63,392,440,523.25,587.33,659.25]
        base_vol = 0.04
        melody_vol = 0.03
        flute_notes = [523,587,659,784]
        a += 0.04*np.sin(2*np.pi*261.63*t)+0.03*np.sin(2*np.pi*329.63*t)
    else:
        pent = [130.81,146.83,164.81,196,220,261.63,293.66,329.63]
        base_vol = 0.03
        melody_vol = 0.02
        flute_notes = [220,261.63,293.66,329.63]
        a += 0.03*np.sin(2*np.pi*130.81*t)+0.02*np.sin(2*np.pi*196*t)

    # Melody
    mel = [(10,5),(12,4),(10,2.5),(8,5.5),(7,3.5),(10,5),(8,4.5),(7,5),(5,4),(7,2.5),
           (8,6),(10,3.5),(12,5),(10,4),(8,5.5),(7,3.5),(5,5),(7,4.5),(8,2.5),(10,6)]
    cur=3.0
    for ni,d in mel:
        if cur>=dur-6: break
        f=pent[ni%len(pent)]; s,e=int(cur*sr),int(min((cur+d)*sr,len(t)))
        nt=np.linspace(0,(e-s)/sr,e-s,endpoint=False)
        an=int(min(0.06,d*0.15)*sr); dn=max(e-s-an,1)
        env=np.concatenate([np.linspace(0,1,an),np.exp(-1.2*np.linspace(0,3.5,dn))])[:e-s]
        w=melody_vol*np.sin(2*np.pi*f*nt)+melody_vol*0.5*np.sin(2*np.pi*f*2*nt)
        a[s:e]+=w*env; cur+=d
    # Flute/high melody
    cur=5.0
    for _ in range(int(dur/4)):
        if cur>=dur-8: break
        for f in flute_notes:
            if cur>=dur-8: break
            d=2.0; s,e=int(cur*sr),int(min((cur+d)*sr,len(t)))
            nt=np.linspace(0,(e-s)/sr,e-s,endpoint=False)
            an=int(0.15*sr); dn=max(e-s-an,1)
            env=np.concatenate([np.linspace(0,1,an),np.exp(-2*np.linspace(0,3,dn))])[:e-s]
            a[s:e]+=0.018*np.sin(2*np.pi*f*nt)*env; cur+=d

    # Ducking during dialogue
    vol = np.ones(len(t)) * 0.4
    for s,e in duck_ranges:
        si,ei=int(s*sr),int(min(e*sr,len(t))); dl=ei-si
        if dl>0:
            fd=int(0.4*sr); fu=int(0.6*sr)
            rd=np.linspace(1,0.25,min(fd,dl)); mid=np.ones(max(dl-fd-fu,0))*0.25
            ru=np.linspace(0.25,1,min(fu,dl))
            env=np.concatenate([rd,mid,ru])[:dl]; vol[si:ei]*=env
    a*=vol
    fi,fo=int(4*sr),int(6*sr); a[:fi]*=np.linspace(0,1,fi); a[-fo:]*=np.linspace(1,0,fo)
    pk=np.max(np.abs(a)); a=a/pk*0.5 if pk>0 else a
    wav.write(path,sr,(a*32767).astype(np.int16))

def make_card(ff, out, t1, t2, dur, fi, fo, W=1920, H=1080, FPS=24,
             bg=(12,8,20), tc=(255,220,140), lc=(200,170,100)):
    img=Image.new('RGB',(W,H),bg); draw=ImageDraw.Draw(img); ft=fs=None
    for fp in ["/System/Library/Fonts/STHeiti Medium.ttc","/System/Library/Fonts/PingFang.ttc"]:
        if os.path.exists(fp):
            try: ft=ImageFont.truetype(fp,72 if t1 else 48); fs=ImageFont.truetype(fp,30); break
            except: continue
    if ft is None: ft=fs=ImageFont.load_default()
    if t1:
        draw.line([(W/2-250,H/2-80),(W/2+250,H/2-80)],fill=lc,width=2)
        b=draw.textbbox((0,0),t1,font=ft); draw.text(((W-(b[2]-b[0]))/2,H/2-50),t1,fill=tc,font=ft)
    if t2:
        b=draw.textbbox((0,0),t2,font=fs); draw.text(((W-(b[2]-b[0]))/2,H/2+40),t2,fill=(180,170,150),font=fs)
    tmp=os.path.join(tempfile.gettempdir(),f"_dc_{os.path.basename(out)}.png"); img.save(tmp)
    return subprocess.run([ff,'-y','-loop','1','-i',tmp,'-f','lavfi','-i','anullsrc=r=44100:cl=stereo','-t',str(dur),
        '-vf',f'fade=in:0:{int(fi*FPS)},fade=out:{int((dur-fo)*FPS)}:{int(fo*FPS)},scale={W}:{H},format=yuv420p',
        '-r',str(FPS),'-c:v','libx264','-preset','fast','-crf','18','-c:a','aac','-b:a','128k','-shortest',out],
        capture_output=True, text=True).returncode == 0

def compose_final(project, base, venv_py, ff, project_root):
    WK = tempfile.mkdtemp(prefix="dc_compose_")
    W, H, FPS = 1920, 1080, 24
    title = project.get("script",{}).get("title","短剧")
    bgm_style = project.get("script",{}).get("bgm_style","gufeng")

    def run(cmd):
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  [ERR] {r.stderr[-300:]}"); return False
        return True

    def vdur(p):
        from moviepy import VideoFileClip
        c=VideoFileClip(p); d=c.duration; c.close(); return d

    print("[1] 规范化视频片段...")
    segs = sorted(Path(base/"segments").glob("shot_*.mp4"))
    nps=[]
    for i,sp in enumerate(segs):
        o=os.path.join(WK,f"n{i:02d}.mp4")
        fo = 4 if i == len(segs)-1 else 0
        d=vdur(str(sp)); vf=[f'scale={W}:{H}','format=yuv420p',f'fps={FPS}']; af=[]
        if fo:
            vf.append(f'fade=out:{int((d-fo)*FPS)}:{int(fo*FPS)}')
            af.append(f'afade=t=out:st={d-fo}:d={fo}')
        cmd=[ff,'-y','-i',str(sp),'-vf',','.join(vf),'-r',str(FPS),'-c:v','libx264','-preset','fast','-crf','18',
             '-c:a','aac','-b:a','128k','-ar','44100','-ac','2']
        if af: cmd+=['-af',','.join(af)]
        cmd.append(o)
        print(f"  {sp.name}...",end=" ",flush=True)
        print("OK" if run(cmd) else "FAIL")
        nps.append(o)

    print("\n[2] 片头片尾...")
    tp=os.path.join(WK,"t.mp4"); ep=os.path.join(WK,"e.mp4")
    make_card(ff,tp,title,"",4,1.2,1.2)
    make_card(ff,ep,"剧终","",8,2,4,bg=(8,5,12))
    clips=[tp]+nps+[ep]; durs=[vdur(p) for p in clips]
    xf=[1.2]+[1.0]*len(nps)+[3.0]

    print("\n[3] 拼接视频...")
    offs=[]; cum=durs[0]
    for i in range(1,len(clips)): offs.append(cum-xf[i-1]); cum+=durs[i]-xf[i-1]
    td=cum
    inputs=[]
    for p in clips: inputs+=['-i',p]
    fl=[]; pv,pa="0:v","0:a"
    for i in range(1,len(clips)):
        ov=f"v{i}" if i<len(clips)-1 else "vo"; oa=f"a{i}" if i<len(clips)-1 else "ao"
        fl.append(f'[{pv}][{i}:v]xfade=transition=fade:duration={xf[i-1]}:offset={offs[i-1]:.3f}[{ov}]')
        fl.append(f'[{pa}][{i}:a]acrossfade=d={xf[i-1]}:c1=tri:c2=tri[{oa}]')
        pv,pa=ov,oa
    cp=os.path.join(WK,"cat.mp4")
    run([ff,'-y']+inputs+['-filter_complex',';'.join(fl),'-map','[vo]','-map','[ao]',
        '-c:v','libx264','-preset','medium','-crf','20','-c:a','aac','-b:a','192k','-pix_fmt','yuv420p','-r',str(FPS),cp])

    # Calculate voice timings
    print("\n[4] 计算音轨时间...")
    seg_starts = offs[:len(nps)]
    seg_main = [s + 1.0 for s in seg_starts]  # after xfade fully visible

    tracks = []
    ducks = []
    for si, shot in enumerate(project.get("shots",[])):
        for v in shot.get("voices", []):
            vf = v.get("voice_file","")
            if not vf or not os.path.exists(vf): continue
            start = seg_main[si] + v.get("start_offset", 2.5)
            c = AudioFileClip(vf).with_start(start).with_volume_scaled(3.0)
            tracks.append(c)
            ducks.append((start - 0.3, start + v.get("duration",3) + 0.3))
            print(f"  s{si+1:02d} {v['character']} @{start:.1f}s: {v['text'][:20]}")

    print("\n[5] 合成BGM...")
    bgw=os.path.join(WK,"bgm.wav")
    gen_bgm(bgw, int(td)+5, ducks, style=bgm_style)

    print("\n[6] 混音...")
    bgm_clip=AudioFileClip(bgw).subclipped(0,td)
    comp=CompositeAudioClip([bgm_clip]+tracks)
    mix=os.path.join(WK,"mix.wav")
    comp.write_audiofile(mix,fps=44100,nbytes=2,codec='pcm_s16le',logger=None)
    comp.close()
    for t in tracks: t.close()
    bgm_clip.close()

    print("\n[7] 最终合成...")
    final_path = str(base / "final.mp4")
    run([ff,'-y','-i',cp,'-i',mix,'-c:v','copy','-c:a','aac','-b:a','192k',
         '-map','0:v:0','-map','1:a:0','-shortest',final_path])

    if os.path.exists(final_path):
        sz=os.path.getsize(final_path)/(1024*1024)
        c=VideoFileClip(final_path)
        print(f"\n✅ 成片完成: {final_path}")
        print(f"   时长: {c.duration:.1f}s ({c.duration/60:.1f}分钟), {c.size[0]}x{c.size[1]}, {sz:.1f}MB")
        c.close()
        project["final_video"] = final_path
