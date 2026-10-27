"""Part-file storage for the harvest: append-only JSONL, resumable, rotated, with manifests.

Layout:  <out>/<generator>/<profile>/part-NNNN.jsonl   and   MANIFEST.json
One line = one generation. Lines are written one at a time with flush + fsync, so a crash can only
damage the LAST line of a part file; repair_truncated_tail() removes such a fragment before resuming.
Files are written in binary mode so Windows never rewrites newlines (always LF).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

PART_RE = re.compile(r"^part-(\d{4})\.jsonl$")
DEFAULT_PART_SIZE = 500
SHARD_STRIDE = 1000  # shard i writes parts numbered i*1000 ... so shards never collide


class StoreError(RuntimeError):
    """A part file is damaged in a way that must be fixed by a human."""


def part_files(folder: Path) -> List[Path]:
    """All part files in folder, sorted by part number."""
    if not folder.is_dir():
        return []
    return sorted((p for p in folder.iterdir() if PART_RE.match(p.name)), key=lambda p: p.name)


def part_number(path: Path) -> int:
    match = PART_RE.match(path.name)
    if not match:
        raise ValueError("not a part file: %s" % path)
    return int(match.group(1))


def part_name(number: int) -> str:
    return "part-%04d.jsonl" % number


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def count_lines(path: Path) -> int:
    with open(path, "rb") as handle:
        return sum(1 for raw in handle if raw.strip())


def repair_truncated_tail(path: Path) -> int:
    """If the file does not end with a newline, cut the unfinished last line. Returns bytes removed."""
    size = path.stat().st_size
    if size == 0:
        return 0
    with open(path, "rb") as handle:
        data = handle.read()
    if data.endswith(b"\n"):
        return 0
    cut = data.rfind(b"\n") + 1  # 0 when there is no newline at all
    with open(path, "r+b") as handle:
        handle.truncate(cut)
    return size - cut


def iter_lines(folder: Path) -> Iterator[Tuple[Path, Dict[str, Any]]]:
    """Yield (part path, parsed line) for every non-blank line in every part file."""
    for path in part_files(folder):
        with open(path, "rb") as handle:
            for number, raw in enumerate(handle, 1):
                if not raw.strip():
                    continue
                try:
                    yield path, json.loads(raw.decode("utf-8"))
                except ValueError as exc:
                    raise StoreError("%s line %d is not valid JSON (%s). Fix or delete that line." % (path, number, exc))


def drop_error_lines(folder: Path) -> int:
    """Remove every line whose `error` is set (so those generations are retried). Returns lines removed.

    Non-error lines are copied byte for byte. Each file is replaced atomically; a part left empty is deleted.
    """
    removed = 0
    for path in part_files(folder):
        kept: List[bytes] = []
        dropped_here = 0
        with open(path, "rb") as handle:
            for raw in handle:
                if not raw.strip():
                    continue
                if json.loads(raw.decode("utf-8")).get("error") is not None:
                    dropped_here += 1
                else:
                    kept.append(raw if raw.endswith(b"\n") else raw + b"\n")
        if dropped_here == 0:
            continue
        removed += dropped_here
        if not kept:
            path.unlink()
            continue
        tmp = path.with_name(path.name + ".tmp")
        with open(tmp, "wb") as handle:
            handle.writelines(kept)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    return removed


class PartWriter:
    """Appends one JSON line at a time (flush + fsync) and rotates to a new part every `part_size` lines."""

    def __init__(self, folder: Path, base_index: int = 0, part_size: int = DEFAULT_PART_SIZE):
        if part_size < 1:
            raise ValueError("part_size must be at least 1")
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.part_size = part_size
        mine = [p for p in part_files(self.folder) if base_index <= part_number(p) < base_index + SHARD_STRIDE]
        if mine:
            self._number = part_number(mine[-1])
            self._count = count_lines(mine[-1])
            if self._count >= part_size:
                self._number += 1
                self._count = 0
        else:
            self._number = base_index
            self._count = 0
        self._handle: Optional[Any] = None

    def _open(self) -> None:
        self._handle = open(self.folder / part_name(self._number), "ab")

    def write(self, line: Dict[str, Any]) -> None:
        if self._handle is None:
            self._open()
        data = (json.dumps(line, sort_keys=True, ensure_ascii=True) + "\n").encode("ascii")
        self._handle.write(data)
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self._count += 1
        if self._count >= self.part_size:
            self._handle.close()
            self._handle = None
            self._number += 1
            self._count = 0

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None


def scan_folder(folder: Path) -> Dict[str, Any]:
    """Whole-folder statistics used for resuming and for the manifest."""
    done: Set[Tuple[str, int]] = set()
    models: Set[str] = set()
    digests: Set[str] = set()
    versions: Set[str] = set()
    lines = errors = mismatches = without_top = truncated = duplicates = 0
    for _path, line in iter_lines(folder):
        key = (line["input_key"], line["sample_idx"])
        if key in done:
            duplicates += 1
        done.add(key)
        lines += 1
        models.add(line.get("model", ""))
        versions.add(line.get("ollama_version", ""))
        if line.get("model_digest"):
            digests.add(line["model_digest"])
        if line.get("error") is not None:
            errors += 1
            continue
        if "".join(token["t"] for token in line["tokens"]) != line["content"]:
            mismatches += 1
        if line["tokens"] and all(token.get("top") is None for token in line["tokens"]):
            without_top += 1
        if line.get("done_reason") == "length":
            truncated += 1
    return {
        "done": done, "models": sorted(models), "digests": sorted(digests), "ollama_versions": sorted(versions),
        "lines": lines, "errors": errors, "text_token_mismatches": mismatches, "lines_without_top": without_top,
        "truncated_by_length": truncated, "duplicates": duplicates,
    }


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(data, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("ascii"))
