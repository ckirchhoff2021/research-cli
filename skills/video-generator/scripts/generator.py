import os
import time
from volcenginesdkarkruntime import Ark   # Install SDK:  pip install 'volcengine-python-sdk[ark]'
from dotenv import load_dotenv
import requests
import argparse
from PIL import Image
import base64
from io import BytesIO



load_dotenv()


def image_to_base64(image_path, fmt='jpeg') -> str:
    image = Image.open(image_path).convert('RGB')
    output_buffer = BytesIO()
    image.save(output_buffer, format=fmt)
    byte_data = output_buffer.getvalue()
    b64_str = base64.b64encode(byte_data).decode('utf-8')
    return f'data:image/{fmt};base64,' + b64_str


def audio_to_base64(audio_path):
    with open(audio_path, "rb") as f:
        base64_str = base64.b64encode(f.read()).decode("utf-8")
    ext = audio_path.split(".")[-1]  
    return f"data:audio/{ext};base64,{base64_str}"



def save_to_local(url):
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs")
    os.makedirs(output_dir, exist_ok=True)
    
    ms_ts = int(time.time() * 1000)
    video_file = os.path.join(output_dir, f"dance_{ms_ts}.mp4")
    video_data = requests.get(url).content
    with open(video_file, 'wb') as f:
        f.write(video_data)
        
    return video_file


class VideoGenerator:
    def __init__(self, base_url, api_key, model_name):
        self.client = Ark(
            base_url=base_url,
            api_key=api_key,
        )
        self.model_name = model_name
        
    
    def generate(
        self, 
        prompt, 
        input_images=None, 
        input_videos=None,
        input_audios=None,
        generate_audio=True, 
        ratio="adaptive", 
        duration=5, 
        frames=-1, 
        resolution="720p", 
        watermark=False
        ):
        '''
        支持的类型：
        1. 文本
        2. 文本（可选）+ 图片
        3. 文本（可选）+ 视频
        4. 文本（可选）+ 图片 + 音频
        5. 文本（可选）+ 图片 + 视频
        6. 文本（可选）+ 视频 + 音频
        7. 文本（可选）+ 图片 + 视频 + 音频

        Generate a video from a prompt and optional reference images.
        
        ratio: The aspect ratio of the video. Defaults to "adaptive", supported values are "adaptive", "16:9", "9:16", "1:1", "3:4"， "9:16", "21:9"
        duration: The duration of the video. Defaults to 5 seconds.
        frames: The number of frames in the video. Defaults to -1, means use duration for generation. Frames take precedence over duration， 24 frames per second.
        watermark: Whether to add a watermark to the video. Defaults to False.
        resolution: The resolution of the video. Defaults to "720p", supported values are "720p", "1080p", "480p"
        input_images: The image URLs/Paths to use as input. Defaults to None.
        input_videos: The video URLs/Paths to use as input. Defaults to None.
        input_audios: The audio URLs/Paths to use as input. Defaults to None.
        '''
        
        content = [{ "type": "text", "text": prompt }]
        
        if input_images:
            for x in input_images:
                if isinstance(x, str) and x.startswith('http'):
                    content.append({"type": "image_url", "image_url": {"url": x}, "role": "reference_image"}) 
                elif isinstance(x, str) and os.path.exists(x):
                    content.append({"type": "image_url", "image_url": {"url": image_to_base64(x)}, "role": "reference_image"})
                else:
                    raise ValueError(f"input image must be either a url, local file path, invalid image path: {x}")
        
        if input_videos:
            for x in input_videos:
                if isinstance(x, str) and x.startswith('http'):
                    content.append({"type": "video_url", "video_url": {"url": x}, "role": "reference_video"})
                else:
                    raise ValueError(f"input video must be a url, invalid video path: {x}")
        
        if input_audios:
            for x in input_audios:
                if isinstance(x, str) and x.startswith('http'):
                    content.append({"type": "audio_url", "audio_url": {"url": x}, "role": "reference_audio"})
                elif isinstance(x, str) and os.path.exists(x):
                    content.append({"type": "audio_url", "audio_url": {"url": audio_to_base64(x)}, "role": "reference_audio"})
                else:
                    raise ValueError(f"input audio must be either a url, local file path, invalid audio path: {x}")
            
        kwargs = {
            'model': self.model_name,
            'content': content,
            'generate_audio': generate_audio,
            'ratio': ratio,
            'resolution': resolution,
            'watermark': watermark,
        }
        if frames > 0:
            kwargs['frames'] = frames
        else:
            kwargs['duration'] = duration
            
        create_result = self.client.content_generation.tasks.create(
            **kwargs
        )
        
        task_id = create_result.id
        while True:
            get_result = self.client.content_generation.tasks.get(task_id=task_id)
            status = get_result.status
            if status == "succeeded":
                video_url = get_result.content.video_url
                video_file = save_to_local(video_url)
                print("----- task succeeded -----")
                print(f'Video url: {video_url}')
                print(f'Saved to: {video_file}')
                break
            elif status == "failed":
                print("----- task failed -----")
                print(f"Error: {get_result.error}")
                break
            else:
                print(f"Task status: {status}, Retrying after 30 seconds...")
                time.sleep(30)
        


def case_001():
    generator = VideoGenerator(
        os.getenv("VIDEO_GEN_BASE_URL"),
        os.getenv("VIDEO_GEN_API_KEY"),
        os.getenv("VIDEO_GEN_MODEL"),
    )
    prompt = "全程使用视频1的第一视角构图，全程使用音频1作为背景音乐。第一人称视角果茶宣传广告，seedance牌「苹苹安安」苹果果茶限定款；首帧为图片1，你的手摘下一颗带晨露的阿克苏红苹果，轻脆的苹果碰撞声；2-4 秒：快速切镜，你的手将苹果块投入雪克杯，加入冰块与茶底，用力摇晃，冰块碰撞声与摇晃声卡点轻快鼓点，背景音：「鲜切现摇」；4-6 秒：第一人称成品特写，分层果茶倒入透明杯，你的手轻挤奶盖在顶部铺展，在杯身贴上粉红包标，镜头拉近看奶盖与果茶的分层纹理；6-8 秒：第一人称手持举杯，你将图片2中的果茶举到镜头前（模拟递到观众面前的视角），杯身标签清晰可见，背景音「来一口鲜爽」，尾帧定格为图片2。背景声音统一为女生音色。"
    images = [
        "https://ark-project.tos-cn-beijing.volces.com/doc_image/r2v_tea_pic1.jpg",
        "https://ark-project.tos-cn-beijing.volces.com/doc_image/r2v_tea_pic2.jpg"
    ]
    
    videos = [
        "https://ark-project.tos-cn-beijing.volces.com/doc_video/r2v_tea_video1.mp4",
    ]
    
    audios = [
        "https://ark-project.tos-cn-beijing.volces.com/doc_audio/r2v_tea_audio1.mp3",
    ]
    
    generator.generate(
        prompt,
        input_images=images,
        input_videos=videos,
        input_audios=audios,
        ratio="16:9",
        duration=11
    )
    

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="generate video from prompt")
    parser.add_argument("--prompt", type=str, required=True, help="prompt to generate video")
    parser.add_argument("--images", type=str, default=None, help="reference images for video generation, comma-separated")
    parser.add_argument("--videos", type=str, default=None, help="reference videos for video generation, comma-separated")
    parser.add_argument("--audios", type=str, default=None, help="reference audios for video generation, comma-separated")
    parser.add_argument("--ratio", type=str, default="adaptive", choices=["adaptive", "16:9", "9:16", "1:1", "3:4", "9:16", "21:9"], help="aspect ratio of the video")
    parser.add_argument("--duration", type=int, default=5, help="duration of the video")
    parser.add_argument("--frames", type=int, default=-1, help="number of frames in the video, default -1 means use duration for generation")
    parser.add_argument("--resolution", type=str, default="720p", choices=["720p", "1080p", "480p"], help="resolution of the video")
    parser.add_argument("--watermark", action="store_true", help="whether to add a watermark to the video")
   
    
    args = parser.parse_args()
    generator = VideoGenerator(
        os.getenv("VIDEO_GEN_BASE_URL"),
        os.getenv("VIDEO_GEN_API_KEY"),
        os.getenv("VIDEO_GEN_MODEL"),
    )
    
    # print(args.images.split(','))
    generator.generate(
        args.prompt,
        input_images=args.images.split(',') if args.images else None,
        input_videos=args.videos.split(',') if args.videos else None,
        input_audios=args.audios.split(',') if args.audios else None,
        ratio=args.ratio,
        duration=args.duration,
        frames=args.frames,
        resolution=args.resolution,
        watermark=args.watermark,
    )