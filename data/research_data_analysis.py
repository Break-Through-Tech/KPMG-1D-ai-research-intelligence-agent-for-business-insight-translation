"""Summarize a folder of research-paper PDFs into a CSV and two charts.

Usage:
    python corpus_summary.py                  # auto-detects a ./data folder with PDFs
    python corpus_summary.py --data-dir path/to/pdfs
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # works without a display (servers, notebooks, scripts)
import matplotlib.pyplot as plt
import pandas as pd
from pypdf import PdfReader

STOPWORDS = {
    "about", "above", "across", "after", "again", "against", "also", "among", "and",
    "any", "are", "based", "been", "being", "between", "both", "but", "can", "could",
    "did", "does", "doing", "down", "during", "each", "few", "for", "from", "further",
    "had", "has", "have", "having", "here", "how", "into", "its", "itself", "just",
    "more", "most", "much", "must", "new", "nor", "not", "now", "off", "once", "only",
    "other", "our", "out", "over", "own", "paper", "papers", "research", "results",
    "same", "should", "some", "study", "such", "task", "tasks", "than", "that", "the",
    "their", "them", "then", "there", "these", "they", "this", "those", "through",
    "too", "under", "until", "used", "using", "very", "was", "were", "what", "when",
    "where", "which", "while", "who", "why", "will", "with", "within", "without",
    "work", "model", "models", "you", "your",
}

THEME_MAP = {
    "Inference routing & model efficiency": [
        "route", "routing", "inference", "cost", "allocation", "efficiency", "model selection",
    ],
    "AI agents & self-improvement": [
        "agent", "agents", "recursive", "self-improvement", "computer-use", "task model",
    ],
    "Behavior modeling & forecasting": [
        "travel", "behavior", "demand", "forecast", "weather", "survey", "data collection",
    ],
    "Medical AI & patient communication": [
        "medical", "patient", "clinical", "healthcare", "checklist", "radiology",
    ],
}

BAD_TITLE_HINTS = ("microsoft word", ".docx", ".tex", ".dvi", "untitled", "untitled document")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def find_data_dir(cli_value: str | None) -> Path:
    """Use --data-dir if given, otherwise look for a folder of PDFs in likely spots."""
    if cli_value:
        return Path(cli_value).expanduser().resolve()

    candidates: list[Path] = []
    try:
        here = Path(__file__).resolve().parent
        candidates += [here / "data", here.parent / "data", here]
    except NameError:  # __file__ is undefined in notebooks / REPLs
        pass
    candidates += [Path.cwd() / "data", Path.cwd()]

    for candidate in candidates:
        if candidate.is_dir() and any(candidate.glob("*.pdf")):
            return candidate

    tried = "\n  ".join(str(c) for c in candidates)
    sys.exit(f"No PDFs found. Looked in:\n  {tried}\nPass --data-dir to point at your PDFs.")


def normalize_title(filename: str) -> str:
    stem = re.sub(r"\.pdf$", "", filename, flags=re.I)
    if "_" in stem:
        stem = stem.split("_", 1)[1]
    stem = re.sub(r"v\d+$", "", stem)  # trailing version tag like "v1"
    return re.sub(r"[-_]+", " ", stem).strip()


def clean_title(metadata_title: str | None, filename: str) -> str:
    """Prefer PDF metadata, but fall back to the filename if it looks like junk."""
    if metadata_title:
        t = " ".join(metadata_title.split())
        if 5 <= len(t) <= 200 and not any(h in t.lower() for h in BAD_TITLE_HINTS):
            return t
    return normalize_title(filename)


def extract_abstract(text: str, max_chars: int = 1200) -> str:
    text = text.replace("\x00", " ")
    match = re.search(
        r"\babstract\b[\s:.\-—]*(.*?)(?=\n\s*(?:1\.?\s+)?introduction\b|\n\s*keywords\b|\n\s*1\.\s)",
        text,
        flags=re.S | re.I,
    )
    if match and match.group(1).strip():
        return " ".join(match.group(1).split())[:max_chars]
    return " ".join(text.split())[:max_chars]  # fallback: start of the paper


def count_words(text: str) -> int:
    return len(re.findall(r"\b[\w\-]+\b", text, flags=re.UNICODE))


def top_keywords(text: str, limit: int = 8) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z'-]+", text.lower())
    counts = Counter(t for t in tokens if len(t) > 3 and t not in STOPWORDS)
    return [word for word, _ in counts.most_common(limit)]


def infer_theme(title: str, abstract: str) -> str:
    combined = f"{title} {abstract}".lower()
    scores = {
        theme: sum(1 for kw in kws if re.search(rf"\b{re.escape(kw)}\b", combined))
        for theme, kws in THEME_MAP.items()
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "General AI research"


def shorten(label: str, width: int = 40) -> str:
    return label if len(label) <= width else label[: width - 1].rstrip() + "…"


# --------------------------------------------------------------------------- #
# Main pipeline
# --------------------------------------------------------------------------- #
def analyze_pdf(pdf_path: Path) -> dict:
    reader = PdfReader(str(pdf_path))
    if reader.is_encrypted:
        # Many "encrypted" PDFs just use an empty password
        if not reader.decrypt(""):
            raise ValueError("PDF is password-protected")

    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    meta = reader.metadata
    title = clean_title(getattr(meta, "title", None), pdf_path.name)
    author = getattr(meta, "author", None) or "Unknown"
    abstract = extract_abstract(text)

    return {
        "file_name": pdf_path.name,
        "title": title,
        "authors": author,
        "pages": len(reader.pages),
        "word_count": count_words(text),
        "abstract_preview": abstract[:300],
        "top_keywords": ", ".join(top_keywords(f"{title} {abstract}")),
        "theme": infer_theme(title, abstract),
        "text_extracted": bool(text.strip()),
    }


def make_charts(df: pd.DataFrame, out_dir: Path) -> None:
    palette = plt.get_cmap("tab10").colors

    # Theme distribution
    theme_counts = df["theme"].value_counts()
    fig, ax = plt.subplots(figsize=(10, 5))
    theme_counts.plot(kind="bar", ax=ax, color=[palette[i % len(palette)] for i in range(len(theme_counts))])
    ax.set_title("Theme Distribution in the Research Corpus")
    ax.set_xlabel("Theme")
    ax.set_ylabel("Number of Papers")
    ax.yaxis.get_major_locator().set_params(integer=True)
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    fig.tight_layout()
    fig.savefig(out_dir / "research_theme_distribution.png", dpi=200)
    plt.close(fig)

    # Word count per paper
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar([shorten(t) for t in df["title"]], df["word_count"], color=palette[0])
    ax.set_title("Word Count by Research Paper")
    ax.set_xlabel("Paper")
    ax.set_ylabel("Words")
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    fig.tight_layout()
    fig.savefig(out_dir / "research_word_counts.png", dpi=200)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", help="Folder containing the PDFs (default: auto-detect)")
    args = parser.parse_args()

    data_dir = find_data_dir(args.data_dir)
    pdfs = sorted(data_dir.glob("*.pdf"))
    print(f"Looking in: {data_dir} | PDFs found: {len(pdfs)}")
    if not pdfs:
        sys.exit("No PDF files in that folder.")

    records, failures = [], []
    for pdf_path in pdfs:
        try:
            records.append(analyze_pdf(pdf_path))
        except Exception as exc:  # keep going if one file is corrupt
            failures.append((pdf_path.name, exc))
            print(f"  ! Skipped {pdf_path.name}: {exc}")

    if not records:
        sys.exit("None of the PDFs could be processed.")

    df = (
        pd.DataFrame(records)
        .sort_values("word_count", ascending=False)
        .reset_index(drop=True)
    )

    output_csv = data_dir / "research_corpus_summary.csv"
    df.to_csv(output_csv, index=False)
    make_charts(df, data_dir)

    print(f"\nCorpus summary saved to: {output_csv}")
    print(df[["title", "pages", "word_count", "theme", "top_keywords"]].to_string(index=False))
    print(f"\nAverage pages per paper: {df['pages'].mean():.1f}")
    print(f"Average words per paper: {df['word_count'].mean():.0f}")
    print("\nTheme distribution:")
    print(df["theme"].value_counts().to_string())

    scanned = df.loc[~df["text_extracted"], "file_name"].tolist()
    if scanned:
        print(f"\nNote: no text extracted from {len(scanned)} file(s) (likely scanned images): {', '.join(scanned)}")
    if failures:
        print(f"\n{len(failures)} file(s) failed: {', '.join(name for name, _ in failures)}")


if __name__ == "__main__":
    main()