import os
import argparse
from openai import OpenAI
from dotenv import load_dotenv
import base64

load_dotenv()

def audio_to_base64(audio_path):
    with open(audio_path, "rb") as f:
        base64_str = base64.b64encode(f.read()).decode("utf-8")
    return f"data:audio/mpeg;base64,{base64_str}"


class SpeechUnderstanding(object):
    def __init__(self, base_url, api_key, model_name):
        self.client = OpenAI( 
            base_url=base_url, 
            api_key=api_key
        ) 
        self.model_name = model_name

    def understand(self, prompt, audio_path):
        base64_file = audio_to_base64(audio_path)
        response = self.client.responses.create(
            model=self.model_name,
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "audio_url": base64_file
                        },
                        {
                            "type": "input_text",
                            "text": prompt
                        }
                    ],
                }
            ],
            # extra_body= {"thinking": {"type": "enabled"}},
            # reasoning={"effort": "medium"}, # minimal, low, medium, high
        )
        return response


def main():
    parser = argparse.ArgumentParser(description="understand audio content")
    parser.add_argument("--prompt", type=str, required=True, help="prompt to understand audio")
    parser.add_argument("--audio", type=str, default=None, help="reference audio for understanding")
    
    args = parser.parse_args()

    generator = SpeechUnderstanding(
        base_url=os.getenv("SPEECH_BASE_URL"),
        api_key=os.getenv("SPEECH_API_KEY"),
        model_name=os.getenv("SPEECH_MODEL"),
    )

    try:
        response = generator.understand(args.prompt, args.audio)
        # print(response)
        print('thinking: ', response.output[0].summary[0].text)
        print('result: ', response.output_text)
    except:
        print('error: failed to understand audio content')
        

if __name__ == '__main__':
    main()


