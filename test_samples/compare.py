"""Porovná Whisper přepis vs ground truth — počítá WER a ukáže diff."""

import re
import sys
import unicodedata
from difflib import unified_diff
from pathlib import Path


def normalize(text: str) -> list[str]:
    """Lower-case, odstranit interpunkci, rozdělit na slova. Zachovat diakritiku."""
    text = text.lower()
    # Odstranit interpunkci
    text = re.sub(r"[-.,!?;:„""'\"—()\[\]…]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.split()


def normalize_ascii(text: str) -> list[str]:
    """Stejné jako normalize ale bez diakritiky — méně přísné porovnání."""
    words = normalize(text)
    return [unicodedata.normalize("NFD", w).encode("ascii", "ignore").decode("ascii") for w in words]


def wer(reference: list[str], hypothesis: list[str]) -> tuple[float, dict]:
    """Word Error Rate přes Levenshtein. Vrátí (WER, {sub, del, ins})."""
    R = len(reference)
    H = len(hypothesis)
    if R == 0:
        return float(H > 0), {"sub": 0, "del": 0, "ins": H}

    # DP matice
    d = [[0] * (H + 1) for _ in range(R + 1)]
    for i in range(R + 1):
        d[i][0] = i
    for j in range(H + 1):
        d[0][j] = j
    for i in range(1, R + 1):
        for j in range(1, H + 1):
            if reference[i - 1] == hypothesis[j - 1]:
                d[i][j] = d[i - 1][j - 1]
            else:
                d[i][j] = 1 + min(d[i - 1][j], d[i][j - 1], d[i - 1][j - 1])

    # Backtrack pro typ chyb
    i, j = R, H
    sub = dele = ins = 0
    while i > 0 or j > 0:
        if i > 0 and j > 0 and reference[i - 1] == hypothesis[j - 1]:
            i -= 1
            j -= 1
        elif i > 0 and j > 0 and d[i][j] == d[i - 1][j - 1] + 1:
            sub += 1
            i -= 1
            j -= 1
        elif i > 0 and d[i][j] == d[i - 1][j] + 1:
            dele += 1
            i -= 1
        else:
            ins += 1
            j -= 1

    return d[R][H] / R, {"sub": sub, "del": dele, "ins": ins}


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: compare.py <ground_truth.txt> <hypothesis.txt>")
        sys.exit(2)

    gt = Path(sys.argv[1]).read_text(encoding="utf-8")
    hyp = Path(sys.argv[2]).read_text(encoding="utf-8")

    gt_words = normalize(gt)
    hyp_words = normalize(hyp)

    wer_full, errs = wer(gt_words, hyp_words)
    wer_ascii, errs_ascii = wer(normalize_ascii(gt), normalize_ascii(hyp))

    print(f"Ground truth slov: {len(gt_words)}")
    print(f"Whisper slov:      {len(hyp_words)}")
    print()
    print(f"WER (s diakritikou):  {wer_full * 100:5.1f}%  ({errs['sub']} sub, {errs['del']} del, {errs['ins']} ins)")
    print(f"WER (bez diakritiky): {wer_ascii * 100:5.1f}%  ({errs_ascii['sub']} sub, {errs_ascii['del']} del, {errs_ascii['ins']} ins)")
    print()
    print("=" * 80)
    print("UNIFIED DIFF (referenčně po větách):")
    print("=" * 80)

    # Diff po větách pro lidskou kontrolu — text bez interpunkce, ale s mezerami zakon. pol.
    def by_word_chunks(words: list[str], n: int = 8) -> list[str]:
        return [" ".join(words[i : i + n]) for i in range(0, len(words), n)]

    diff = list(unified_diff(
        by_word_chunks(gt_words),
        by_word_chunks(hyp_words),
        fromfile="ground_truth",
        tofile="whisper",
        lineterm="",
        n=2,
    ))
    print("\n".join(diff[:80]))  # první 80 řádků diff


if __name__ == "__main__":
    main()
