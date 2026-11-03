"""Offline micro-benchmark of the vault: write N notes, sync, full-text search.

No network, no API keys, no LLM. It measures only the local storage layer
(markdown files + SQLite FTS5) that every research run reads and writes.

    python scripts/bench_vault.py            # 1000 notes, 200 queries
    python scripts/bench_vault.py --notes 5000 --queries 500

The vault is created in a temporary directory and deleted afterwards.
"""

from __future__ import annotations

import argparse
import platform
import random
import statistics
import sys
import tempfile
import time
from pathlib import Path

from hyperresearch.core.note import write_note
from hyperresearch.core.sync import compute_sync_plan, execute_sync
from hyperresearch.core.vault import Vault
from hyperresearch.search.fts import search_fts

WORDS = [
    "battery", "lithium", "supply", "chain", "tariff", "semiconductor", "inflation",
    "yield", "bond", "equity", "merger", "regulation", "clinical", "trial", "vaccine",
    "protein", "climate", "carbon", "emission", "subsidy", "labor", "wage", "housing",
    "rent", "mortgage", "logistics", "freight", "port", "shipping", "energy", "solar",
    "wind", "grid", "storage", "policy", "court", "ruling", "patent",
]


def _body(rng: random.Random, n_words: int) -> str:
    return " ".join(rng.choice(WORDS) for _ in range(n_words))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--notes", type=int, default=1000)
    ap.add_argument("--words", type=int, default=300, help="words per note body")
    ap.add_argument("--queries", type=int, default=200)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    rng = random.Random(args.seed)
    with tempfile.TemporaryDirectory() as tmp:
        vault = Vault.init(Path(tmp) / "bench-vault", name="bench")

        t0 = time.perf_counter()
        for i in range(args.notes):
            write_note(
                vault.notes_dir,
                f"Bench note {i:05d}",
                body=f"# Bench note {i:05d}\n\n{_body(rng, args.words)}\n",
                tags=[rng.choice(WORDS), rng.choice(WORDS)],
            )
        t_write = time.perf_counter() - t0

        t0 = time.perf_counter()
        result = execute_sync(vault, compute_sync_plan(vault, force=True))
        t_sync = time.perf_counter() - t0

        queries = [" ".join(rng.sample(WORDS, 2)) for _ in range(args.queries)]
        lat_ms: list[float] = []
        hits = 0
        for q in queries:
            t0 = time.perf_counter()
            rows = search_fts(vault.db, q, limit=20)
            lat_ms.append((time.perf_counter() - t0) * 1000)
            hits += bool(rows)
        n_indexed = vault.db.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        vault.close()

    lat_ms.sort()
    p95 = lat_ms[max(0, int(len(lat_ms) * 0.95) - 1)]
    print(f"python            {platform.python_version()} ({platform.system()})")
    print(f"notes written     {args.notes} x {args.words} words")
    print(f"notes indexed     {n_indexed}  (sync added={result.added})")
    print(f"write             {t_write:.2f} s  ({args.notes / t_write:.0f} notes/s)")
    print(f"sync (index)      {t_sync:.2f} s  ({args.notes / t_sync:.0f} notes/s)")
    print(f"search queries    {len(queries)}  (with >=1 hit: {hits})")
    print(f"search latency    median {statistics.median(lat_ms):.2f} ms, p95 {p95:.2f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
