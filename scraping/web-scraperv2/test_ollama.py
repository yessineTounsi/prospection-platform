import requests

response = requests.post(
    "http://localhost:11434/api/generate",
    json={
        "model": "mistral",
        "prompt": 'Réponds uniquement en JSON : {"test": "ok"}',
        "format": "json",
        "stream": False
    },
    timeout=60
)
print(response.status_code)
print(response.json())
