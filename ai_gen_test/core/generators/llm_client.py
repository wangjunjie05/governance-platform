import requests

from core.config import MODEL, NUM_PREDICT, OLLAMA_URL, TEMPERATURE, OLLAMA_TIMEOUT, OLLAMA_RETRY


def call_ollama(prompt: str) -> str:
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": NUM_PREDICT, "temperature": TEMPERATURE},
    }
    last_error = None
    retry = max(int(OLLAMA_RETRY or 1), 1)
    for _ in range(retry):
        try:
            resp = requests.post(OLLAMA_URL, json=payload, timeout=OLLAMA_TIMEOUT)
            resp.raise_for_status()
            return resp.json().get("response", "").strip()
        except Exception as exc:
            last_error = exc
    raise last_error
