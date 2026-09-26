"""
PDF extraction script — run once before deploying (or at deploy time).

Usage:
    python extract.py

Reads:
    source_docs/paper.pdf  — main 80-page consultation paper
    source_docs/data.pdf   — 41-page supporting data paper

Writes:
    extracted/paper.json
    extracted/data.json

Each JSON file has the shape:
    {
        "source": "paper" | "data",
        "extracted_at": "<ISO timestamp>",
        "full_text": "<full extracted text with markers inline>",
        "sections": [{"marker": "...", "text": "..."}, ...],
        "markers": ["Section 1", "Para 1", "Table 1", ...]
    }

Marker extraction strategy:
    The IRDAI paper uses explicit paragraph numbering (1, 2, 3 ... ~163),
    section headers (Section 1 through Section N), table labels (Table 1, Table 4, etc.),
    and annexures (Annexure 1, Annexure 3, etc.).  These already appear verbatim in
    the PDF text — we extract what is there, we do NOT invent numbering.
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
# Regex patterns for IRDAI document markers
# Order matters: more specific patterns first.
# ---------------------------------------------------------------------------

# Section headers — e.g. "Section 1", "SECTION 2 —", "Section 9 – Title"
_RE_SECTION = re.compile(
    r'(?m)^[ \t]*(?:SECTION|Section)\s+(\d+(?:\.\d+)*)\s*(?:[-–—].*)?$'
)

# Paragraph numbers — lines that begin with a bare integer followed by a period
# or lines explicitly labelled "Para N" / "Paragraph N"
_RE_PARA_LABEL = re.compile(
    r'\b(?:Para(?:graph)?)\s+(\d+)\b', re.IGNORECASE
)
_RE_PARA_LINE = re.compile(
    r'(?m)^[ \t]*(\d{1,3})\.[ \t]'
)

# Table labels — "Table 1", "TABLE 1", "Table 1:", "Table 1 –" etc.
_RE_TABLE = re.compile(
    r'\b(?:TABLE|Table)\s+(\d+)\b'
)

# Annexure / Annex labels
_RE_ANNEXURE = re.compile(
    r'\b(?:Annexure|Annex(?:ure)?)\s+(\d+|[IVX]+)\b', re.IGNORECASE
)

# Combined pattern for splitting the text into sections
# We split on the *same* marker types so every split point is a named marker
_RE_SPLIT = re.compile(
    r'(?m)'
    r'(?:'
    # "Section N" at start of line (possibly indented)
    r'(?:^[ \t]*(?:SECTION|Section)\s+\d+(?:\.\d+)*(?:[ \t]*[-–—][^\n]*)?)'
    r'|'
    # "Para N" / "Paragraph N" inline
    r'(?:\bPara(?:graph)?\s+\d+\b)'
    r'|'
    # "Table N" inline
    r'(?:\b(?:TABLE|Table)\s+\d+\b)'
    r'|'
    # "Annexure N" / "Annex N" inline
    r'(?:\b(?:Annexure|Annex(?:ure)?)\s+(?:\d+|[IVX]+)\b)'
    r')',
    re.IGNORECASE
)


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract plain text from a PDF, cleaning up common PDF artefacts."""
    doc = fitz.open(str(pdf_path))
    pages = []
    for page in doc:
        text = page.get_text("text")
        pages.append(text)
    doc.close()
    full = "\n".join(pages)

    # Normalise line endings
    full = full.replace("\r\n", "\n").replace("\r", "\n")

    # Collapse runs of blank lines to at most two
    full = re.sub(r'\n{3,}', '\n\n', full)

    # Remove soft hyphens at line breaks (PDF hyphenation artefact)
    full = re.sub(r'-\n(?=[a-z])', '', full)

    return full


def build_marker_label(match_text: str) -> str:
    """Normalise a raw matched marker string to a canonical label."""
    s = match_text.strip()
    # Collapse internal whitespace
    s = re.sub(r'\s+', ' ', s)
    # Capitalise first word uniformly
    if s.lower().startswith('section'):
        s = 'Section ' + s.split(None, 1)[1] if len(s.split()) > 1 else s
    elif re.match(r'para', s, re.I):
        s = 'Para ' + re.sub(r'^para(?:graph)?\s+', '', s, flags=re.I)
    elif re.match(r'table', s, re.I):
        s = 'Table ' + re.sub(r'^table\s+', '', s, flags=re.I)
    elif re.match(r'annex', s, re.I):
        s = 'Annexure ' + re.sub(r'^ann(?:ex(?:ure)?)?\s+', '', s, flags=re.I)
    return s


def split_into_sections(full_text: str) -> list[dict]:
    """
    Split full_text into sections at every marker boundary.
    Returns list of {"marker": str, "text": str}.
    Text before the first marker is stored under marker "Preamble".
    """
    splits = list(_RE_SPLIT.finditer(full_text))

    if not splits:
        # No markers found — return entire text as one section
        return [{"marker": "Full Text", "text": full_text.strip()}]

    sections = []

    # Text before the very first marker
    preamble = full_text[: splits[0].start()].strip()
    if preamble:
        sections.append({"marker": "Preamble", "text": preamble})

    for i, match in enumerate(splits):
        marker_label = build_marker_label(match.group(0))
        start = match.end()
        end = splits[i + 1].start() if i + 1 < len(splits) else len(full_text)
        body = full_text[start:end].strip()
        # Include the marker text itself at the top of the body for context
        section_text = match.group(0).strip() + "\n" + body
        sections.append({"marker": marker_label, "text": section_text})

    return sections


def collect_unique_markers(sections: list[dict]) -> list[str]:
    """Return de-duplicated list of all marker labels, preserving order."""
    seen = set()
    markers = []
    for s in sections:
        m = s["marker"]
        if m not in seen:
            seen.add(m)
            markers.append(m)
    return markers


def process_pdf(name: str, pdf_path: Path, out_path: Path) -> None:
    print(f"  Extracting {name} from {pdf_path} …")
    full_text = extract_text_from_pdf(pdf_path)
    sections = split_into_sections(full_text)
    markers = collect_unique_markers(sections)

    result = {
        "source": name,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "full_text": full_text,
        "sections": sections,
        "markers": markers,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ {len(sections)} sections, {len(markers)} unique markers → {out_path}")


def main():
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

    print("Starting PDF extraction…")
    for name, pdf_path in sources.items():
        out_path = base / "extracted" / f"{name}.json"
        process_pdf(name, pdf_path, out_path)

    print("\nExtraction complete. Re-start the server to pick up the new text.")


if __name__ == "__main__":
    main()
