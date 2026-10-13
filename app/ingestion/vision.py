"""Optional second reader for scanned pages: a vision LLM transcribes a page the local OCR was unsure of.

Off by default. When it is on, the page image leaves the machine, and a model that transcribes can
also invent, so its output is trimmed and never preferred over a confident local reading.
"""

from app.logging import get_logger

logger = get_logger(__name__)

PROMPT = (
    "Transcribe all text on this page exactly as written, line by line, in reading order. Include "
    "handwriting. Do not correct, complete, translate or explain anything. Write each line once. "
    "If a word is illegible write [illegible]. Output only the transcription."
)


class VisionTranscriber:
    """Calls an OpenAI-compatible chat endpoint with one page image and returns the text it reads."""

    def __init__(self, base_url: str, api_key: str, model: str, timeout_s: float = 30.0):
        self.model = model
        self._base_url = base_url
        self._api_key = api_key
        self._timeout_s = timeout_s

    def __call__(self, jpeg: bytes) -> str:
        import base64

        import httpx  # lazy: only needed when a page is actually sent

        image = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
        response = httpx.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self.model,
                "temperature": 0,
                "max_tokens": 1500,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": PROMPT},
                            {"type": "image_url", "image_url": {"url": image}},
                        ],
                    }
                ],
            },
            timeout=self._timeout_s,
        )
        response.raise_for_status()
        return drop_repeated_tail(response.json()["choices"][0]["message"]["content"] or "")


def drop_repeated_tail(text: str) -> str:
    """Cut the transcription where it starts over.

    Vision models sometimes finish a page and then begin it again, often in broken fragments. The
    first substantial line showing up a second time marks that point.
    """
    lines = [line.rstrip() for line in text.strip().splitlines()]
    first = next((line.strip() for line in lines if len(line.strip()) >= 8), None)
    if first is None:
        return "\n".join(lines).strip()
    seen = False
    for index, line in enumerate(lines):
        if line.strip() == first:
            if seen:
                return "\n".join(lines[:index]).strip()
            seen = True
    return "\n".join(lines).strip()
