import base64
import json
import uuid
import requests
import os
from dotenv import load_dotenv
import argparse

load_dotenv()

appid = os.getenv("TTS_APPID")
access_token= os.getenv("TTS_ACCESS_TOKEN")
cluster = os.getenv("TTS_CLUSTER")


host = "openspeech.bytedance.com"
api_url = f"https://{host}/api/v1/tts"
header = {"Authorization": f"Bearer;{access_token}"}

def run(text, voice_type, output_file):
    request_json = {
        "app": {
            "appid": appid,
            "token": "access_token",
            "cluster": cluster
        },
        "user": {
            "uid": "388808087185088"
        },
        "audio": {
            "voice_type": voice_type,
            "encoding": "mp3",
            "speed_ratio": 1.0,
            "volume_ratio": 1.0,
            "pitch_ratio": 1.0,
        },
        "request": {
            "reqid": str(uuid.uuid4()),
            "text":  text, 
            "text_type": "plain",
            "operation": "query",
            "with_frontend": 1,
            "frontend_type": "unitTson"

        }
    }
    try:
        resp = requests.post(api_url, json.dumps(request_json), headers=header)
        if "data" in resp.json():
            data = resp.json()["data"]
            file_to_save = open(output_file, "wb")
            file_to_save.write(base64.b64decode(data))
            print(f"Success: speech save to {output_file}")
    except Exception as e:
        e.with_traceback()
        print(f"Error: failed to synthesize speech: {str(e)}")
        
        
if __name__ == '__main__':
    args = argparse.ArgumentParser()
    args.add_argument('--tts_text', type=str, required=True, help='Text to synthesize')
    args.add_argument('--voice_type', type=str, default="zh_male_shenyeboke_moon_bigtts", help='Voice type to use')
    args.add_argument('--output_file', type=str, default='output.mp3', help='Output file path')
    args = args.parse_args()
    run(args.tts_text, args.voice_type, args.output_file)
