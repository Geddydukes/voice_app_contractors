from __future__ import annotations

import argparse
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parent
if str(MODULE_ROOT) not in sys.path:
    sys.path.append(str(MODULE_ROOT))

from ingestion import load_sample_corpus
from vector_store import VectorStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Local knowledge ingestion harness")
    parser.add_argument(
        "query",
        help="Query text to run against the ingested contractor corpus",
    )
    parser.add_argument(
        "--samples",
        type=Path,
        default=Path(__file__).parent / "samples",
        help="Optional directory containing website/, documents/, and faq.json",
    )
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    store = VectorStore()
    load_sample_corpus(store, args.samples)

    results = store.query(args.query, top_k=args.top_k)
    if not results:
        print("No snippets found for query", repr(args.query))
        return
    for rank, (chunk, score) in enumerate(results, start=1):
        print(f"[{rank}] score={score:.4f} source={chunk.source} metadata={chunk.metadata}")
        print(chunk.text)
        print("-")


if __name__ == "__main__":
    main()
