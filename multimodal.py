"""Build Responses API messages from text and local images or image URLs."""
import base64
from pathlib import Path


def image_part(source):
    source = str(source)
    if source.startswith("https://"):
        return {"type": "input_image", "image_url": source, "detail": "high"}
    path = Path(source)
    data = path.read_bytes()
    if not data or len(data) > 20 * 1024 * 1024:
        raise ValueError("Image must be nonempty and at most 20 MB")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif data.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    elif data[:6] in (b"GIF87a", b"GIF89a"):
        mime = "image/gif"
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        mime = "image/webp"
    else:
        raise ValueError("Supported image formats: PNG, JPEG, WEBP, GIF")
    return {"type": "input_image", "image_url": f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}", "detail": "high"}


def user_content(prompt, images=None):
    if not images:
        return prompt
    if isinstance(images, (str, Path)):
        images = [images]
    return [{"type": "input_text", "text": prompt or "Please help me understand these images."},
            *[image_part(source) for source in images]]


def has_images(messages):
    return any(isinstance(m, dict) and isinstance(m.get("content"), list)
               and any(isinstance(p, dict) and p.get("type") == "input_image" for p in m["content"])
               for m in messages)
