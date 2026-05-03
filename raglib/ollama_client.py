import requests

from raglib.config import OLLAMA_URL, MODEL


def chat(system_prompt: str, user_prompt: str, model: str = MODEL, timeout: int = 600) -> str:
    response = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
        },
        timeout=timeout,
    )

    response.raise_for_status()
    return response.json()["message"]["content"]


def generate(prompt: str, model: str = MODEL, timeout: int = 600) -> str:
    response = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
        },
        timeout=timeout,
    )

    response.raise_for_status()
    return response.json()["response"]
