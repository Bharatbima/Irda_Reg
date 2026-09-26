"""
PDF extraction script — run once before deploying (or at deploy time).

Usage:
    python extract.py

Reads:
    source_docs/paper.pdf  — main ~80-page consultation paper
    source_docs/data.pdf   — ~41-page supporting data paper

Writes:
    extracted/paper.json
    extracted/data.json

Each JSON file:
    {
        "source": "paper",
        "extracted_at": "<ISO-8601>",
        "full_text": "...",            # cleaned text with [Para N] labels injected
        "sections": [{"marker": "Section 3", "text": "..."}, ...],
        "markers": ["Section 3", "Para 40", "Table 1", ...]
    }

Extraction strategy (IRDAI paper format):
  - Paragraphs are numbered 1-163 as standalone lines: "40.<LF>text..."
    → injected as "[Para 40]" labels in the output text
  - Section headers: "Section N - Title" at the start of a line
    (TOC entries — lines with long dot-runs — are excluded)
  - Tables: "Table N" or "Table N:" inline labels
  - Annexures: "Annexure N" or "Annexure" headings
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    print("ERROR: PyMuPDF is not installed. Run: pip install PyMuPDF")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Encoding fix
# ---------------------------------------------------------------------------

def fix_encoding(text: str) -> str:
    """
    Fix mojibake: the PDF stores UTF-8 but some glyph maps cause PyMuPDF to
    return the raw bytes decoded as cp1252.  Round-tripping via cp1252 -> utf-8
    recovers the original characters.  Falls back silently if the text is already
    clean ASCII/UTF-8.
    """
    try:
        return text.encode("cp1252").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    try:
        return text.encode("latin-1").decode("utf-8", errors="replace")
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    return text


# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------

def extract_raw_text(pdf_path: Path) -> str:
    doc = fitz.open(str(pdf_path))
    pages = []
    for page in doc:
        pages.append(page.get_text("text"))
    doc.close()

    text = "\n".join(pages)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = fix_encoding(text)
    text = re.sub(r"\n{3,}", "\n\n", text)       # collapse blank lines
    text = re.sub(r"-\n(?=[a-z])", "", text)      # de-hyphenate line breaks
    return text


# ---------------------------------------------------------------------------
# Detect and inject [Para N] labels
# ---------------------------------------------------------------------------

# A standalone paragraph-number line looks like:  \n40. \n
# Criteria: a line that contains ONLY digits + period + optional whitespace.
# We exclude lines that are pure integers without a period (page numbers in some PDFs).
_RE_PARA_STANDALONE = re.compile(
    r"(?m)^[ \t]*(\d{1,3})\.[ \t]*$"
)


def _is_plausible_para_num(n: int) -> bool:
    """Filter out false positives: list bullets (1-6), page numbers (1-80)."""
    return 1 <= n <= 200   # IRDAI paper has ~163 paras; give headroom


def inject_para_labels(text: str) -> tuple[str, list[str]]:
    """
    Replace standalone 'N.' lines with '[Para N]' labels inline.
    Returns (modified_text, sorted_list_of_para_markers).
    """
    para_markers: list[str] = []

    def replacer(m: re.Match) -> str:
        n = int(m.group(1))
        if not _is_plausible_para_num(n):
            return m.group(0)   # leave unchanged
        label = f"Para {n}"
        if label not in para_markers:
            para_markers.append(label)
        return f"\n[{label}] "

    modified = _RE_PARA_STANDALONE.sub(replacer, text)
    # Sort numerically so markers come out in document order
    para_markers.sort(key=lambda s: int(s.split()[1]))
    return modified, para_markers


# ---------------------------------------------------------------------------
# Detect section headers
# ---------------------------------------------------------------------------

# TOC entries have long dot-runs: "Section 1 - Overview ....... 5"
_RE_TOC_DOTS = re.compile(r"\.{4,}")

_RE_SECTION_HEADER = re.compile(
    r"(?m)^[ \t]*(Section\s+\d+(?:\.\d+)*)(?:[ \t]*[-–—][^\n]*)?\s*$",
    re.IGNORECASE,
)


def collect_section_markers(text: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for m in _RE_SECTION_HEADER.finditer(text):
        line = m.group(0).strip()
        # Skip if this looks like a TOC entry
        if _RE_TOC_DOTS.search(line):
            continue
        label = normalise_section_label(m.group(1).strip())
        if label not in seen:
            seen.add(label)
            result.append(label)
    return result


def normalise_section_label(raw: str) -> str:
    raw = re.sub(r"\s+", " ", raw.strip())
    # Capitalise "section" uniformly
    raw = re.sub(r"(?i)^section\s+", "Section ", raw)
    return raw


# ---------------------------------------------------------------------------
# Detect table and annexure references
# ---------------------------------------------------------------------------

_RE_TABLE = re.compile(r"\bTable\s+(\d+)\b", re.IGNORECASE)
_RE_ANNEXURE = re.compile(r"\bAnnexure\s+(\d+|[IVX]+)\b", re.IGNORECASE)
_RE_GRAPH = re.compile(r"\bGraph\s+(\d+)\b", re.IGNORECASE)
_RE_BOX = re.compile(r"\bBox\s+(\d+[A-Z]?)\b", re.IGNORECASE)


def collect_inline_markers(text: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    patterns: list[tuple[re.Pattern, str]] = [
        (_RE_TABLE,    "Table"),
        (_RE_ANNEXURE, "Annexure"),
        (_RE_GRAPH,    "Graph"),
        (_RE_BOX,      "Box"),
    ]
    # Collect all hits with their position so we can return them in document order
    hits: list[tuple[int, str]] = []
    for pat, prefix in patterns:
        for m in pat.finditer(text):
            label = f"{prefix} {m.group(1)}"
            if label not in seen:
                seen.add(label)
                hits.append((m.start(), label))

    hits.sort(key=lambda x: x[0])
    result = [label for _, label in hits]
    return result


# ---------------------------------------------------------------------------
# Build sections by splitting on [Para N] and Section headers
# ---------------------------------------------------------------------------

_RE_INJECTED_PARA = re.compile(r"\[Para (\d+)\]")
_RE_SECTION_SPLIT = re.compile(
    r"(?m)^[ \t]*(?:Section\s+\d+(?:\.\d+)*)(?:[ \t]*[-–—][^\n]*)?\s*$",
    re.IGNORECASE,
)


def split_into_sections(text: str) -> list[dict]:
    """
    Split text into sections using [Para N] and Section header markers.
    Both markers are 'anchors'; everything between consecutive anchors
    belongs to the earlier anchor's section.
    """
    # Gather all split points: (position, label)
    split_points: list[tuple[int, str]] = []

    for m in _RE_INJECTED_PARA.finditer(text):
        label = f"Para {m.group(1)}"
        split_points.append((m.start(), label))

    for m in _RE_SECTION_SPLIT.finditer(text):
        line = m.group(0).strip()
        if _RE_TOC_DOTS.search(line):
            continue
        label = normalise_section_label(
            re.search(r"Section\s+\d+(?:\.\d+)*", line, re.I).group(0)
        )
        split_points.append((m.start(), label))

    if not split_points:
        return [{"marker": "Full Text", "text": text.strip()}]

    split_points.sort(key=lambda x: x[0])

    sections: list[dict] = []

    # Text before the first marker
    preamble = text[: split_points[0][0]].strip()
    if preamble:
        sections.append({"marker": "Preamble", "text": preamble})

    for i, (pos, label) in enumerate(split_points):
        end = split_points[i + 1][0] if i + 1 < len(split_points) else len(text)
        body = text[pos:end].strip()
        sections.append({"marker": label, "text": body})

    return sections


# ---------------------------------------------------------------------------
# Main per-PDF processing
# ---------------------------------------------------------------------------

def process_pdf(name: str, pdf_path: Path, out_path: Path) -> None:
    print(f"  Extracting {name} from {pdf_path} ...")

    raw = extract_raw_text(pdf_path)
    labelled_text, para_markers = inject_para_labels(raw)

    sections = split_into_sections(labelled_text)
    section_markers = collect_section_markers(labelled_text)
    inline_markers = collect_inline_markers(labelled_text)

    # Deduplicated markers in document order: sections first, then paras, then tables/etc.
    all_markers: list[str] = []
    seen: set[str] = set()
    for m in section_markers + para_markers + inline_markers:
        if m not in seen:
            seen.add(m)
            all_markers.append(m)

    result = {
        "source": name,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "full_text": labelled_text,
        "sections": sections,
        "markers": all_markers,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"  OK: {len(sections)} sections, "
        f"{len(para_markers)} para markers, "
        f"{len(all_markers)} total markers -> {out_path}"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    base = Path(__file__).parent
    sources = {
        "paper": base / "source_docs" / "paper.pdf",
        "data":  base / "source_docs" / "data.pdf",
    }

    missing = [k for k, v in sources.items() if not v.exists()]
    if missing:
        print("ERROR: The following source PDFs are missing:")
        for m in missing:
            print(f"  source_docs/{m}.pdf")
        print("Place the PDFs in source_docs/ and re-run this script.")
        sys.exit(1)

    print("Starting PDF extraction...")
    for name, pdf_path in sources.items():
        out_path = base / "extracted" / f"{name}.json"
        process_pdf(name, pdf_path, out_path)

    print("\nExtraction complete. Re-start the server to pick up the new text.")


if __name__ == "__main__":
    main()
