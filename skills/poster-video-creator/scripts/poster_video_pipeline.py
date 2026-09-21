#!/usr/bin/env python3
"""海报驱动的动画化视频批量管线。

流程: 人物海报 --图生图(风格化关键帧, 全局缓存/可复用)--> Seedance 多参考图视频。
解决问题: Seedance 对写实真人肖像直接返回 400 InputImageSensitiveContentDetected.
PrivacyInformation; 先转成明确的动画角色关键帧即可通过, 同时保留人物辨识度。

任务 JSON 格式:
[
  {
    "name": "05_体育热血番",
    "style": "anime",                 # 3d | anime | ink | cyber
    "posters": ["041_boxer.jpg", ...],# poster-dir 下的文件名, 建议 6 张对应 6 个镜头
    "prompt": "分镜描述文本...",
    "ratio": "9:16"                   # 可选, 默认 9:16
  }
]
"""
import os, sys, json, time, re, argparse, importlib.util
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
SKILLS_DIR = os.path.join(REPO_ROOT, 'skills')


def load_module(mod_name, rel_path):
    path = os.path.join(SKILLS_DIR, rel_path)
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


KEEP = ('严格保留参考图的人物姿态、构图、服装、配饰、场景与光影色调；人物仍是戴细黑金属圆框眼镜、'
        '短寸高渐变发型、单眼皮偏圆脸、短胡茬的同一位亚洲男士，辨识度高；竖版，无任何文字、字母、logo、水印。')
STYLES = {
 '3d': '把参考图转成3D动画电影角色画面，迪士尼皮克斯级三维渲染：CG皮肤材质、明亮有神的大眼睛、细腻毛发与布料、柔和棚拍级电影光、色彩温暖高级。',
 'anime': '把参考图转成写实向高质量日式动画电影画面，今敏式赛璐璐画风：干净利落线稿、细腻赛璐璐上色、电影级色彩分级与光影、写实背景。',
 'ink': '把参考图转成中国风水墨工笔重彩动画画面，参考《中国奇谭》：石青石绿朱砂矿物色重彩结合水墨晕染笔触、宣纸纹理、线条雅致、东方意境。',
 'cyber': '把参考图转成赛博朋克日系动画画面，参考《边缘行者》《攻壳机动队》：干净赛璐璐线稿、高饱和霓虹蓝洋红撞色、强烈电影光效、精致机械细节。',
}
BOOST = '形象进一步卡通化、动画化，明确是非真人的手绘/三维动画角色，面部比例适度夸张。'
SAFE = '彻底Q版儿童动画化，可爱无害，色彩明亮，去掉一切写实、惊悚、暴力、武器相关元素，改为适合全年龄的卡通玩具感画面。'
LOCK = ('所有画面中的男士必须是同一个动画角色：戴细黑金属圆框眼镜的亚洲男士，短寸高渐变发型、单眼皮、'
        '偏圆脸型、短胡茬，五官与参考图片完全一致；画面不出现任何文字、字幕、字母、logo、水印。')


class Pipeline:
    def __init__(self, args):
        self.args = args
        load_dotenv(args.env_file or os.path.join(REPO_ROOT, '.env'))
        ig_mod = load_module('igen', 'image-generator/scripts/generator.py')
        vg_mod = load_module('vgen', 'video-generator/scripts/generator.py')
        self.ig = ig_mod.ImageGenerator(
            os.getenv('IMAGE_GEN_BASE_URL'), os.getenv('IMAGE_GEN_API_KEY'), os.getenv('IMAGE_GEN_MODEL'))
        self.vg = vg_mod.VideoGenerator(
            os.getenv('VIDEO_GEN_BASE_URL'), os.getenv('VIDEO_GEN_API_KEY'), os.getenv('VIDEO_GEN_MODEL'))
        self.image_to_base64 = vg_mod.image_to_base64

    def stylize(self, style, poster):
        out = os.path.join(self.args.cache_dir, f'{style}_{os.path.basename(poster)}')
        if os.path.exists(out) and os.path.getsize(out) > 20000:
            return out, None
        last_err = ''
        for round_ in range(4):
            extra = '' if round_ == 0 else (BOOST if round_ < 3 else BOOST + SAFE)
            prompt = STYLES[style] + KEEP + extra
            try:
                url = self.ig.text2image(prompt, self.args.image_size,
                                        os.path.join(self.args.poster_dir, poster))
                data = requests.get(url, timeout=180).content
                if len(data) < 20000:
                    raise RuntimeError('bad keyframe payload')
                with open(out, 'wb') as f:
                    f.write(data)
                return out, None
            except Exception as e:
                last_err = f'{style}/{poster} round {round_ + 1}: {str(e)[:200]}'
                print('[retry]', last_err, flush=True)
                time.sleep(3 * (round_ + 1))
        return out, last_err

    def beat_path(self, task, i):
        return os.path.join(self.args.cache_dir, f"{task['name']}__b{i + 1}.jpg")

    def stylize_beat(self, task, i):
        """故事模式：用同一 anchor 生成服装/场景统一的连续故事节拍关键帧。"""
        out = self.beat_path(task, i)
        if os.path.exists(out) and os.path.getsize(out) > 20000:
            return out, None
        beat_keep = (
            '这是同一个生活故事的连续关键帧之一：全片必须是同一位男士、同一套服装、同一处生活环境，'
            '时间自然推进，禁止换装、禁止身份切换；人物是戴细黑金属圆框眼镜、短寸高渐变发型、'
            '单眼皮偏圆脸、短胡茬的亚洲男士，五官与参考图一致；'
            f"服装统一为{task.get('wardrobe', '参考图中的服装')}；"
            f"本帧情节：{task['beats'][i]}；竖版电影构图，无任何文字、字母、logo、水印。")
        last_err = ''
        for round_ in range(4):
            extra = '' if round_ == 0 else (BOOST if round_ < 3 else BOOST + SAFE)
            prompt = STYLES[task['style']] + beat_keep + extra
            try:
                url = self.ig.text2image(prompt, self.args.image_size,
                                        os.path.join(self.args.poster_dir, task['anchor']))
                data = requests.get(url, timeout=180).content
                if len(data) < 20000:
                    raise RuntimeError('bad keyframe payload')
                with open(out, 'wb') as f:
                    f.write(data)
                return out, None
            except Exception as e:
                last_err = f"{task['name']}/beat{i + 1} round {round_ + 1}: {str(e)[:200]}"
                print('[retry]', last_err, flush=True)
                time.sleep(3 * (round_ + 1))
        return out, last_err

    def submit_video(self, task):
        out = os.path.join(self.args.out_dir, task['name'] + '.mp4')
        if os.path.exists(out) and os.path.getsize(out) > 100000:
            return task['name'], None, True

        content = [{'type': 'text', 'text': task['prompt'] + LOCK}]
        story_mode = 'beats' in task
        n_refs = len(task['beats']) if story_mode else len(task['posters'])
        for i in range(n_refs):
            if story_mode:
                kf = self.beat_path(task, i)
            else:
                kf = os.path.join(self.args.cache_dir,
                                  f"{task['style']}_{os.path.basename(task['posters'][i])}")
            if not os.path.exists(kf):
                return task['name'], f'missing keyframe {kf}', False
            content.append({'type': 'image_url',
                            'image_url': {'url': self.image_to_base64(kf)},
                            'role': 'reference_image'})
        for retry_round in range(2):
            try:
                t = self.vg.client.content_generation.tasks.create(
                    model=self.vg.model_name, content=content, generate_audio=True,
                    ratio=task.get('ratio', '9:16'), resolution=self.args.resolution,
                    duration=task.get('duration', self.args.duration), watermark=False)
                break
            except Exception as e:
                msg = str(e)
                if '400' in msg and retry_round == 0:
                    idxs = sorted({int(x) - 1 for x in re.findall(r'content\[(\d+)\]', msg)
                                   if int(x) >= 1 and int(x) - 1 < n_refs})
                    print(f"[{task['name']}] blocked frames {idxs}, re-stylizing...", flush=True)
                    for j in idxs:
                        if story_mode:
                            kf = self.beat_path(task, j)
                            if os.path.exists(kf):
                                os.remove(kf)
                            _, err = self.stylize_beat(task, j)
                        else:
                            poster = task['posters'][j]
                            kf = os.path.join(self.args.cache_dir,
                                              f"{task['style']}_{os.path.basename(poster)}")
                            if os.path.exists(kf):
                                os.remove(kf)
                            _, err = self.stylize(task['style'], poster)
                        if err:
                            return task['name'], err, False
                    continue
                return task['name'], msg[:300], False
        else:
            return task['name'], 'task rejected after retry', False

        while True:
            r = self.vg.client.content_generation.tasks.get(task_id=t.id)
            if r.status == 'succeeded':
                data = requests.get(r.content.video_url, timeout=300).content
                if len(data) < 100000:
                    return task['name'], 'downloaded video too small', False
                with open(out, 'wb') as f:
                    f.write(data)
                return task['name'], None, False
            if r.status == 'failed':
                return task['name'], str(r.error)[:300], False
            print(f"[{task['name']}] {r.status}", flush=True)
            time.sleep(20)

    def run(self, tasks):
        os.makedirs(self.args.cache_dir, exist_ok=True)
        montage = sorted({(t['style'], p) for t in tasks if 'beats' not in t
                          for p in t['posters']})
        beat_jobs = [(t, i) for t in tasks if 'beats' in t
                     for i in range(len(t['beats']))]
        total = len(montage) + len(beat_jobs)
        print(f'=== phase A: {total} keyframes ({len(montage)} montage, {len(beat_jobs)} story) ===', flush=True)
        failed = []
        with ThreadPoolExecutor(max_workers=self.args.key_workers) as ex:
            futs = {ex.submit(self.stylize, s, p): (s, p) for s, p in montage}
            for t, i in beat_jobs:
                futs[ex.submit(self.stylize_beat, t, i)] = (t['name'], i)
            done = 0
            for fut in as_completed(futs):
                out, err = fut.result()
                done += 1
                if err:
                    failed.append(err)
                print(f'[{done:3d}/{total}] {"OK  " if err is None else "FAIL"} {os.path.basename(out)}', flush=True)
        if failed:
            print('KEYFRAME FAILURES:', failed, flush=True)
            if self.args.strict:
                sys.exit(2)

        if self.args.keyframes_only:
            return

        print(f'=== phase B: {len(tasks)} videos ===', flush=True)
        ok = 0
        with ThreadPoolExecutor(max_workers=self.args.workers) as ex:
            futs = [ex.submit(self.submit_video, t) for t in tasks]
            for fut in as_completed(futs):
                name, err, skipped = fut.result()
                ok += err is None
                tag = 'SKIP ' if skipped else ('OK   ' if err is None else 'FAIL ')
                print(f'{tag}[{ok}/{len(tasks)}] {name}' + (f' :: {err}' if err else ''), flush=True)


def main():
    ap = argparse.ArgumentParser(description='海报 -> 动画关键帧 -> 批量视频')
    ap.add_argument('--tasks', required=True, help='任务 JSON 文件路径')
    ap.add_argument('--poster-dir', required=True, help='海报图片目录')
    ap.add_argument('--out-dir', required=True, help='视频输出目录')
    ap.add_argument('--cache-dir', default=None, help='关键帧缓存目录, 默认 out-dir/cache')
    ap.add_argument('--env-file', default=None, help='.env 路径, 默认仓库根 .env')
    ap.add_argument('--workers', type=int, default=3, help='视频并发数')
    ap.add_argument('--key-workers', type=int, default=5, help='关键帧并发数')
    ap.add_argument('--duration', type=int, default=10, help='单段视频时长(秒)')
    ap.add_argument('--resolution', default='1080p', choices=['480p', '720p', '1080p'])
    ap.add_argument('--image-size', default='2K', help='关键帧生成尺寸')
    ap.add_argument('--only', default=None, help='只运行指定 name, 逗号分隔')
    ap.add_argument('--keyframes-only', action='store_true', help='只生成关键帧')
    ap.add_argument('--dry-run', action='store_true', help='只校验任务与缓存, 不发起任何生成')
    ap.add_argument('--strict', action='store_true', help='有关键帧失败时立即退出')
    args = ap.parse_args()

    if args.cache_dir is None:
        args.cache_dir = os.path.join(args.out_dir, 'cache')

    with open(args.tasks, encoding='utf-8') as f:
        tasks = json.load(f)
    if args.only:
        wanted = {x.strip() for x in args.only.split(',') if x.strip()}
        tasks = [t for t in tasks if t['name'] in wanted]
    for t in tasks:
        assert t['name'] and t['style'] in STYLES and t['prompt'], t
        if 'beats' in t:
            assert t['anchor'] and t['beats'], t
            refs = [t['anchor']]
        else:
            assert t['posters'], t
            refs = t['posters']
        for p in refs:
            path = os.path.join(args.poster_dir, p)
            assert os.path.exists(path), f'missing poster: {path}'

    if args.dry_run:
        for t in tasks:
            if 'beats' in t:
                missing = [i + 1 for i in range(len(t['beats']))
                           if not os.path.exists(Pipeline(args).beat_path(t, i))]
                print(f"{t['name']}: story {len(t['beats'])} beats, {len(missing)} keyframes missing {missing}")
            else:
                missing = [p for p in t['posters']
                           if not os.path.exists(os.path.join(args.cache_dir,
                                                              f"{t['style']}_{os.path.basename(p)}"))]
                print(f"{t['name']}: {len(t['posters'])} refs, {len(missing)} keyframes missing {missing}")
        return

    os.makedirs(args.out_dir, exist_ok=True)
    Pipeline(args).run(tasks)


if __name__ == '__main__':
    main()
