import argparse
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from portable_ai import PORTABLE_OLLAMA_URL, PortableAiRuntime


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("build_dir", type=Path)
    args = parser.parse_args()

    runtime = PortableAiRuntime(args.build_dir.resolve())
    try:
        if not runtime.starten():
            print("Portable KI-Laufzeit konnte nicht gestartet werden.")
            return 1
        payload = {
            "model": "qwen3:4b",
            "prompt": "Antworte nur mit OK.",
            "stream": False,
            "think": False,
            "options": {"num_ctx": 512, "num_predict": 8},
        }
        request = Request(
            f"{PORTABLE_OLLAMA_URL}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=180) as response:
            data = json.loads(response.read().decode("utf-8"))
        print(
            f"model={data.get('model')} done={data.get('done')} "
            f"response={str(data.get('response', '')).strip()}"
        )
        return 0 if data.get("done") is True else 1
    finally:
        runtime.beenden()


if __name__ == "__main__":
    raise SystemExit(main())
