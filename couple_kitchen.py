# Keep the renderer; --app selects the responsive, authenticated two-person kitchen.
import sys as _sys
if __name__ == "__main__" and "--app" in _sys.argv:
    from kitchen_app.server import cli as _app_cli
    raise SystemExit(_app_cli([x for x in _sys.argv[1:] if x != "--app"]))

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import math, os, subprocess, sys, wave, struct, hashlib, shutil, json
from pathlib import Path

W, H, FPS, DURATION = 1290, 2796, 30, 33.0
REFERENCE_DIR = Path(__file__).resolve().parent / "reference"
REFERENCE_SECONDS_PER_PAGE = 3.0
ROOT = Path(__file__).resolve().parent
FRAMES = ROOT / 'frames'
OUT = ROOT / 'out'
FONT_BOLD = r'C:\Windows\Fonts\msyhbd.ttc'
FONT_REG = r'C:\Windows\Fonts\msyh.ttc'
FONT_SERIF = r'C:\Windows\Fonts\NotoSerifSC-VF.ttf'

for p in (FRAMES, OUT): p.mkdir(exist_ok=True)

def font(size, bold=False, serif=False):
    path = FONT_SERIF if serif else (FONT_BOLD if bold else FONT_REG)
    return ImageFont.truetype(path, size)

def ease_out(t): return 1 - (1-t)**3

def ease_in_out(t): return t*t*(3-2*t)

def clamp(x,a=0,b=1): return max(a,min(b,x))

def rr(draw, xy, r, fill, outline=None, width=1):
    draw.rounded_rectangle(xy, radius=r, fill=fill, outline=outline, width=width)

def center_text(draw, xy, text, fnt, fill, stroke=0, stroke_fill=None):
    x,y = xy
    box=draw.textbbox((0,0),text,font=fnt,stroke_width=stroke)
    draw.text((x-(box[2]-box[0])/2,y-(box[3]-box[1])/2), text, font=fnt, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)

def fit_text(draw, text, max_width, size, bold=False, serif=False):
    f=font(size,bold,serif)
    if draw.textbbox((0,0),text,font=f)[2] <= max_width: return f
    while size>12:
        size-=2; f=font(size,bold,serif)
        if draw.textbbox((0,0),text,font=f)[2] <= max_width: return f
    return f

def draw_heart(draw, cx, cy, s, fill):
    pts=[]
    for i in range(101):
        t=2*math.pi*i/100
        x=16*math.sin(t)**3
        y=-(13*math.cos(t)-5*math.cos(2*t)-2*math.cos(3*t)-math.cos(4*t))
        pts.append((cx+x*s,cy+y*s))
    draw.polygon(pts,fill=fill)

def draw_pan(draw, x, y, scale, rot=0):
    # icon-like skillet
    draw.ellipse((x-95*scale,y-44*scale,x+95*scale,y+52*scale), fill=(37,31,44), outline=(255,177,117), width=max(1,int(7*scale)))
    draw.line((x+85*scale,y+4*scale,x+190*scale,y-30*scale), fill=(255,177,117), width=max(2,int(16*scale)))
    draw.ellipse((x-55*scale,y-28*scale,x+55*scale,y+28*scale), fill=(253,155,112))

def frame_at(t):
    # Reproduce the eleven observed reference screens, not the previous invented story.
    page = min(11, max(1, int(max(0.0, t) / REFERENCE_SECONDS_PER_PAGE) + 1))
    with Image.open(REFERENCE_DIR / f"page{page:02d}.jpg") as image:
        return image.convert("RGB")


def legacy_frame_at(t):
    im=Image.new('RGB',(W,H),(24,16,34)); d=ImageDraw.Draw(im)
    # warm paper / kitchen gradient
    for yy in range(H):
        q=yy/H
        col=(int(29+22*q), int(18+13*q), int(43+18*q))
        d.line((0,yy,W,yy),fill=col)
    # decorative tile grid
    for x in range(0,W,120): d.line((x,240,x,H), fill=(255,255,255,12), width=2)
    for y in range(240,H,120): d.line((0,y,W,y), fill=(255,255,255,10), width=2)
    # top branding
    d.rounded_rectangle((48,48,1032,185), radius=34, fill=(255,245,226), outline=(239,169,118), width=4)
    center_text(d,(540,93),'情侣趣味厨房',font(42,True), (48,29,42))
    center_text(d,(540,145),'独 家 御 膳 房  ·  今 日 菜 单',font(26,False,True), (152,76,80))
    # floating hearts
    for i,(x,y,sc,ph) in enumerate([(92,310,1.2,0),(968,340,.9,1.2),(900,1640,1.05,2.4),(130,1570,.75,1.7)]):
        yy=y+math.sin(t*2+ph)*12
        draw_heart(d,x,yy,sc,(239,104,122))
    # scene cards
    if t < 2.35:
        p=clamp(t/0.45); slide=-450*(1-ease_out(p)) if t<.45 else 0
        # message bubbles
        rr(d,(78+slide,330,1002+slide,620),36,(255,248,234),outline=(255,198,150),width=4)
        d.text((130+slide,380),'今日想吃什么？',font=font(60,True),fill=(56,32,48))
        d.text((130+slide,477),'朕要一道“看起来很贵”的晚餐。',font=font(37),fill=(113,70,82))
        rr(d,(238+slide,700,920+slide,1020),34,(253,199,184),outline=(255,238,224),width=4)
        d.text((292+slide,758),'臣妾遵旨。',font=font(66,True),fill=(73,36,51))
        d.text((292+slide,860),'马上为陛下开启御膳房。',font=font(35),fill=(122,58,72))
        draw_heart(d,874+slide,760,1.0,(238,77,107))
        if t>1.05:
            alpha=clamp((t-1.05)/.5); rr(d,(150,1110,930,1250),28,(255,231,166),outline=(234,166,82),width=4)
            center_text(d,(540,1180),'点击菜单 · 进入厨房',font(42,True), (100,52,29))
    elif t < 4.9:
        p=clamp((t-2.35)/.55)
        # menu zoom card
        scale=1+0.08*ease_out(p)
        cx,cy=540,930
        cardw,cardh=850*scale,1080*scale
        rr(d,(cx-cardw/2,cy-cardh/2,cx+cardw/2,cy+cardh/2),42,(250,239,211),outline=(213,141,93),width=6)
        center_text(d,(540,470),'御 膳 菜 单',font(76,True,True),(85,41,44))
        center_text(d,(540,565),'本店今日只接待一位贵客',font(32), (148,87,76))
        items=[('A01','番茄玫瑰·心动版','¥ 0.00'),('B02','空气炸锅·御前小酥','¥ 0.00'),('C03','男朋友亲手端上桌','无价')]
        for i,(code,name,price) in enumerate(items):
            y=720+i*170
            d.line((145,y+95,935,y+95),fill=(221,174,129),width=3)
            d.text((160,y),code,font=font(30,True),fill=(189,91,91))
            d.text((270,y),name,font=font(35,True),fill=(65,39,44))
            d.text((704,y+4),price,font=font(31,True),fill=(160,75,69))
        rr(d,(280,1330,800,1455),32,(214,84,103))
        center_text(d,(540,1392),'下 单',font(48,True),(255,247,234))
        if t>3.6:
            d.text((150,1570),'备注：少放一点盐，多放一点爱。',font=font(31,False,True),fill=(115,66,60))
    elif t < 7.75:
        # cooking montage
        p=(t-4.9)/2.85
        # counter
        d.rectangle((0,1140,W,H),fill=(101,53,53))
        d.rectangle((0,1140,W,1190),fill=(235,155,106))
        # stove and pan
        d.ellipse((85,1280,590,1515),fill=(24,21,29),outline=(255,190,117),width=7)
        d.ellipse((145,1335,530,1470),fill=(236,106,87))
        draw_pan(d,730,1390,1.45)
        # ingredients circles
        for i,(x,y,c) in enumerate([(180,1650,(243,89,95)),(370,1620,(255,217,108)),(560,1670,(105,193,111)),(760,1610,(237,150,91))]):
            rr(d,(x-90,y-90,x+90,y+90),90,c)
            center_text(d,(x,y),['番茄','鸡蛋','葱','爱心'][i],font(34,True),(64,33,44))
        # steam
        for i in range(5):
            x=250+i*90+math.sin(t*3+i)*15
            y=1100-abs(math.sin(t*2+i))*160
            d.arc((x-24,y-100,x+24,y+40),180,360,fill=(255,246,211),width=8)
        rr(d,(90,340,990,650),38,(38,27,46),outline=(255,192,126),width=5)
        center_text(d,(540,415),'御膳房 · 火力全开',font(64,True),(255,218,146))
        center_text(d,(540,520),'翻锅 / 撒盐 / 偷偷加糖',font(36), (255,238,220))
        center_text(d,(540,585), '“你负责好看，我负责开火。”',font(35,False,True),(255,180,166))
        # progress bar
        d.rounded_rectangle((145,880,935,935),radius=27,fill=(56,37,55))
        d.rounded_rectangle((145,880,145+790*ease_in_out(clamp(p)),935),radius=27,fill=(248,138,107))
        center_text(d,(540,820),f'烹饪进度 {min(99,int(p*112))}% ',font(35,True),(255,244,224))
    else:
        p=clamp((t-7.75)/3.25)
        # reveal plate
        d.rectangle((0,1150,W,H),fill=(71,41,51))
        rr(d,(130,310,950,1070),48,(254,244,219),outline=(231,166,115),width=7)
        center_text(d,(540,450),'御前最终呈现',font(57,True,True),(73,37,43))
        d.ellipse((225,565,855,945),fill=(250,250,239),outline=(212,144,102),width=7)
        # plated heart dish
        draw_heart(d,540,752,7.2,(224,103,91))
        d.ellipse((370,700,470,800),fill=(255,213,103)); d.ellipse((610,700,710,800),fill=(255,213,103))
        center_text(d,(540,1002),'好吃到需要续费一个拥抱',font(38,True),(89,42,50))
        if t>9.15:
            rr(d,(160,1225,920,1520),34,(255,231,171),outline=(229,161,92),width=5)
            center_text(d,(540,1295),'本单合计',font(32), (118,71,45))
            center_text(d,(540,1380),'¥ 0.00',font(82,True),(187,62,76))
            center_text(d,(540,1472),'付款方式：亲一下即可',font(30,False,True),(113,64,57))
        if t>10.05:
            center_text(d,(540,1650),'下次还点你。',font(54,True),(255,235,204))
            draw_heart(d,810,1625,1.1,(241,84,106))
    # footer
    d.line((68,1810,1012,1810),fill=(255,203,163),width=3)
    d.text((72,1840),'COUPLE KITCHEN / 001',font=font(25,True),fill=(255,214,176))
    d.text((770,1840),'一人下单 · 两人用餐',font=font(25),fill=(255,214,176))
    # subtle grain / vignette
    overlay=Image.new('RGBA',(W,H),(0,0,0,0)); od=ImageDraw.Draw(overlay)
    for i in range(0, W, 12): od.line((i,0,i,H),fill=(255,255,255,4),width=1)
    im=Image.alpha_composite(im.convert('RGBA'),overlay)
    # vignette
    vig=Image.new('L',(W,H),0); vd=ImageDraw.Draw(vig)
    for r in range(0,180,8):
        a=int(2+(180-r)*0.08)
        vd.rectangle((r,r,W-r,H-r),outline=a,width=8)
    shade=Image.new('RGBA',(W,H),(15,8,20,0)); shade.putalpha(vig)
    im=Image.alpha_composite(im,shade)
    return im.convert('RGB')

def main():
    # Timing is an explicit preview setting; original audio/timing is not available.
    expected = json.loads((REFERENCE_DIR / "manifest.json").read_text(encoding="utf-8"))
    for item in expected["images"]:
        image_path = REFERENCE_DIR / f"page{item['index']:02d}.jpg"
        if hashlib.sha256(image_path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError(f"Reference image hash mismatch: {image_path}")
    concat = REFERENCE_DIR / "concat.txt"
    lines = []
    for page in range(1, 12):
        lines.extend([f"file 'page{page:02d}.jpg'", f"duration {REFERENCE_SECONDS_PER_PAGE:.6f}"])
    lines.append("file 'page11.jpg'")
    concat.write_text("\n".join(lines) + "\n", encoding="utf-8")
    final = OUT / "couple_kitchen_reference.mp4"
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat",
               "-safe", "0", "-i", str(concat), "-vf", f"fps={FPS}",
               "-t", str(DURATION), "-c:v", "libx264", "-preset", "fast", "-crf", "16",
               "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart", str(final)]
    subprocess.run(command, check=True)
    print(f"VIDEO={final.resolve()}")
    print(f"SHA256={hashlib.sha256(final.read_bytes()).hexdigest()}")
    print("PAGES=11")
    print(f"FRAMES={int(DURATION*FPS)}")
    print(f"SIZE={W}x{H}")
    print(f"DURATION={DURATION:.1f}")
    print("TIMING=preview_3_seconds_per_page_not_original")
    print("AUDIO=none_original_track_download_timed_out")
    print(f"BYTES={final.stat().st_size}")


def legacy_main():
    n=int(round(DURATION*FPS))
    for idx in range(n):
        t=idx/FPS
        frame_at(t).save(FRAMES/f'f{idx:04d}.png', quality=95)
    # simple original synth soundtrack with clicks, pad, bass
    sr=48000; total=int(DURATION*sr); samples=[]
    def tone(freq, dur, amp, start):
        st=int(start*sr); en=min(total,st+int(dur*sr))
        for j in range(st,en):
            tt=(j-st)/sr; env=min(1,tt*35)*max(0,(dur-tt)*16)
            samples[j]+=amp*env*math.sin(2*math.pi*freq*tt)
    samples=[0.0]*total
    for st in [0,1.0,2.0,3.0,4.0,5.0,6.0,7.0,8.0,9.0,10.0]:
        tone(880,0.055,0.16,st); tone(1320,0.04,0.07,st+0.08)
    for st in [0,2.0,4.0,6.0,8.0,10.0]: tone(110,0.42,0.18,st)
    for i in range(11): tone(220*(1+(i%3)*.5),0.25,0.04,i)
    pcm=bytearray()
    for x in samples:
        v=max(-1,min(1,x*0.55)); pcm += struct.pack('<h', int(v*32767))
    wav=OUT/'music.wav'
    with wave.open(str(wav),'wb') as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr); wf.writeframes(pcm)
    silent=OUT/'couple_kitchen_silent.mp4'; final=OUT/'couple_kitchen_recreation.mp4'
    ff='ffmpeg'
    subprocess.run([ff,'-y','-framerate',str(FPS),'-i',str(FRAMES/'f%04d.png'),'-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-an',str(silent)],check=True)
    subprocess.run([ff,'-y','-i',str(silent),'-i',str(wav),'-c:v','copy','-c:a','aac','-b:a','192k','-shortest','-movflags','+faststart',str(final)],check=True)
    # hash and metadata
    h=hashlib.sha256(final.read_bytes()).hexdigest()
    print(f'VIDEO={final.resolve()}')
    print(f'SHA256={h}')
    print(f'FRAMES={n}')
    print(f'BYTES={final.stat().st_size}')

if __name__=='__main__': main()
