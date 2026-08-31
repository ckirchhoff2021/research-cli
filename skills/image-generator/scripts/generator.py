import base64
from io import BytesIO
from PIL import Image
from openai import OpenAI
import argparse
from dotenv import load_dotenv
import os
import requests
import time

load_dotenv()


def pil_to_base64_with_prefix(image: Image.Image, fmt='jpeg') -> str:
    output_buffer = BytesIO()
    image.save(output_buffer, format=fmt)
    byte_data = output_buffer.getvalue()
    b64_str = base64.b64encode(byte_data).decode('utf-8')
    return f'data:image/{fmt};base64,' + b64_str


def source_image_to_payload(source_image):
    if isinstance(source_image, str) and source_image.startswith(("http://", "https://")):
        return source_image
    if isinstance(source_image, str) and os.path.exists(source_image):
        image = Image.open(source_image)
        return pil_to_base64_with_prefix(image)
    if isinstance(source_image, Image.Image):
        return pil_to_base64_with_prefix(source_image)
    raise ValueError(
        "source_image must be either a url, local file path or a PIL.Image.Image object, "
        f"but got {type(source_image)!r}"
    )


def normalize_source_images(source_image):
    if source_image is None:
        return []
    if isinstance(source_image, (str, Image.Image)):
        return [source_image]
    if isinstance(source_image, (list, tuple)):
        if not source_image:
            return []
        return list(source_image)
    raise ValueError(
        "source_image must be None, a single image, or a list/tuple of images, "
        f"but got {type(source_image)!r}"
    )


def parse_cli_images(images):
    if not images:
        return None

    parsed_images = []
    for item in images:
        parts = [part.strip() for part in item.split(",") if part.strip()]
        parsed_images.extend(parts)

    if not parsed_images:
        return None
    if len(parsed_images) == 1:
        return parsed_images[0]
    return parsed_images


class ImageGenerator(object):
    def __init__(self, base_url, api_key, model_name):
        self.client = OpenAI( 
            base_url=base_url, 
            api_key=api_key
        ) 
        self.model_name = model_name

    def text2image(self, prompt, size='2K', source_image=None):
        extra_body = {
            "watermark": False,
        }
        source_images = normalize_source_images(source_image)
        if source_images:
            image_payloads = [source_image_to_payload(image) for image in source_images]
            extra_body["image"] = image_payloads[0] if len(image_payloads) == 1 else image_payloads
        
        response = self.client.images.generate( 
            model=self.model_name,
            prompt=prompt,
            size=size,
            response_format="url",
            extra_body=extra_body
        ) 
        return response.data[0].url


def save_to_local(url):
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs")
    os.makedirs(output_dir, exist_ok=True)
    
    ms_ts = int(time.time() * 1000)
    output_file = os.path.join(output_dir, f"dream_{ms_ts}.jpg")
    img_data = requests.get(url).content
    with open(output_file, 'wb') as handler:
        handler.write(img_data)
        
    return output_file


def main():
    parser = argparse.ArgumentParser(description="generate image from prompt")
    parser.add_argument("--prompt", type=str, required=True, help="prompt to generate image")
    parser.add_argument(
        "--image",
        type=str,
        action="append",
        default=None,
        help="reference image for image generation; repeatable or comma-separated for multiple images",
    )
    parser.add_argument("--size", type=str, default="2K", choices=["2K", "3K", "4K"], help="size of the image")
    
    args = parser.parse_args()

    generator = ImageGenerator(
        base_url=os.getenv("IMAGE_GEN_BASE_URL"),
        api_key=os.getenv("IMAGE_GEN_API_KEY"),
        model_name=os.getenv("IMAGE_GEN_MODEL"),
    )

    response = generator.text2image(args.prompt, args.size, parse_cli_images(args.image))
    output_file = save_to_local(response)

    print(f"Image URL: {response}")
    print(f"Saved to: {output_file}")


if __name__ == '__main__':
    main()

