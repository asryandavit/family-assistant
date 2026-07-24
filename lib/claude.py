import json
import os
import subprocess


def _strip_fences(s):
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.endswith("```"):
            s = s[: s.rfind("```")]
    return s.strip()


def run(cfg, prompt_file, data=None, expect_json=True):
    """Run `claude -p` with prompt_file + optional data payload.

    The prompt is piped via STDIN, not passed as an argv argument: Windows caps
    command lines near 32k characters and any real data payload blows past it
    (WinError 206).
    """
    path = os.path.join(cfg["_root"], prompt_file)
    with open(path, encoding="utf-8") as f:
        prompt = f.read()

    if data is not None:
        prompt += "\n\nINPUT DATA (JSON):\n" + json.dumps(data, ensure_ascii=False)

    proc = subprocess.run(
        [cfg["claude_cmd"], "-p", "--output-format", "json"],
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=600,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude failed: {(proc.stderr or proc.stdout)[:500]}")

    wrapper = json.loads(proc.stdout)
    text = wrapper.get("result", proc.stdout)

    if not expect_json:
        return text
    return json.loads(_strip_fences(text))
