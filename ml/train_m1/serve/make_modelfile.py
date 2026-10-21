"""
ARGUS Phase 5 - register a fine-tuned GGUF in Ollama using the base model's own chat template.

    python -m ml.train_m1.serve.make_modelfile --gguf C:\\models\\argus_sft\\model-Q4_K_M.gguf --base qwen3.5:4b --name argus-m1-sft

Copies `ollama show <base> --modelfile`, replaces its FROM line(s) by the GGUF, writes Modelfile.<name> next to this script and runs `ollama create`.
"""

import argparse
import subprocess
import sys
from pathlib import Path


def build_modelfile(base_text, gguf):
    out, done = [], False
    for line in base_text.splitlines():
        if line.startswith("FROM "):
            if not done:
                out.append("FROM {}".format(gguf))
                done = True
            continue
        out.append(line)
    if not done:
        out.insert(0, "FROM {}".format(gguf))
    return "\n".join(out) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser(description="Register a GGUF in Ollama")
    p.add_argument("--gguf", required=True)
    p.add_argument("--base", default="qwen3.5:4b")
    p.add_argument("--name", required=True)
    o = p.parse_args(argv)
    if not Path(o.gguf).exists():
        print("GGUF file not found: {}".format(o.gguf))
        return 2
    shown = subprocess.run(["ollama", "show", o.base, "--modelfile"], capture_output=True, text=True, encoding="utf-8")
    if shown.returncode != 0:
        print("ollama show failed (is {} installed? run: ollama pull {})\n{}".format(o.base, o.base, shown.stderr))
        return 2
    target = Path(__file__).resolve().parent / "Modelfile.{}".format(o.name)
    target.write_text(build_modelfile(shown.stdout, str(Path(o.gguf).resolve())), encoding="utf-8", newline="\n")
    print("Wrote {}".format(target))
    created = subprocess.run(["ollama", "create", o.name, "-f", str(target)])
    return created.returncode


if __name__ == "__main__":
    sys.exit(main())
