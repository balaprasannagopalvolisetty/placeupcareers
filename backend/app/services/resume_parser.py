"""
PlaceUp Career — Resume Parser Service
Extracts text from PDF and DOCX resume files.
"""

import io
import logging
import re
from typing import Optional
from zipfile import is_zipfile

logger = logging.getLogger(__name__)

MAX_PDF_PAGES = 8
PDF_ACTIVE_CONTENT_MARKERS = (
    b"/JavaScript",
    b"/JS",
    b"/OpenAction",
    b"/AA",
    b"/Launch",
    b"/EmbeddedFile",
)


async def parse_resume_file(
    file_content: bytes,
    filename: str,
) -> dict:
    """Parse a resume file and extract raw text + metadata.

    Supports PDF and DOCX file formats. Cleans extracted text
    and provides basic document statistics.

    Args:
        file_content: Raw file bytes
        filename: Original filename (used to detect format)

    Returns:
        Dict with keys: text, word_count, page_count, format
    """
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if "\x00" in filename or "/" in filename or "\\" in filename:
        raise ValueError("Invalid filename.")

    if ext == "pdf":
        return await _parse_pdf(file_content)
    elif ext in ("docx", "doc"):
        return await _parse_docx(file_content)
    else:
        raise ValueError(f"Unsupported file format: .{ext}. Please upload a PDF or DOCX file.")


async def _parse_pdf(content: bytes) -> dict:
    """Extract text from a PDF file using PyPDF2.

    Handles multi-page PDFs, removing headers/footers
    and normalizing whitespace.

    Args:
        content: Raw PDF bytes

    Returns:
        Dict with text, word_count, page_count
    """
    if not content.startswith(b"%PDF"):
        raise ValueError("Uploaded file is not a valid PDF.")
    lower_probe = content[: min(len(content), 2_000_000)]
    if any(marker in lower_probe for marker in PDF_ACTIVE_CONTENT_MARKERS):
        raise ValueError("PDF contains active or embedded content and cannot be accepted.")
    try:
        from PyPDF2 import PdfReader

        reader = PdfReader(io.BytesIO(content))
        if getattr(reader, "is_encrypted", False):
            raise ValueError("Encrypted PDFs are not supported.")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise ValueError(f"Resume PDF is too long. Please upload {MAX_PDF_PAGES} pages or fewer.")
        pages = []

        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text.strip())

        full_text = "\n\n".join(pages)
        full_text = _clean_resume_text(full_text)

        return {
            "text": full_text,
            "word_count": len(full_text.split()),
            "page_count": len(reader.pages),
            "format": "pdf",
        }

    except ImportError:
        logger.error("PyPDF2 not installed. Run: pip install PyPDF2")
        raise
    except Exception as e:
        logger.error(f"PDF parsing error: {e}")
        raise ValueError(f"Failed to parse PDF: {str(e)}")


async def _parse_docx(content: bytes) -> dict:
    """Extract text from a DOCX file using python-docx.

    Extracts text from paragraphs and tables.

    Args:
        content: Raw DOCX bytes

    Returns:
        Dict with text, word_count, page_count
    """
    if not content.startswith(b"PK") or not is_zipfile(io.BytesIO(content)):
        raise ValueError("Uploaded file is not a valid DOCX document.")
    try:
        from docx import Document

        doc = Document(io.BytesIO(content))
        paragraphs = []

        # Extract paragraph text
        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                paragraphs.append(text)

        # Extract table text
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                if row_text:
                    paragraphs.append(row_text)

        full_text = "\n".join(paragraphs)
        full_text = _clean_resume_text(full_text)

        return {
            "text": full_text,
            "word_count": len(full_text.split()),
            "page_count": max(1, len(full_text) // 3000),  # Estimate
            "format": "docx",
        }

    except ImportError:
        logger.error("python-docx not installed. Run: pip install python-docx")
        raise
    except Exception as e:
        logger.error(f"DOCX parsing error: {e}")
        raise ValueError(f"Failed to parse DOCX: {str(e)}")


def _clean_resume_text(text: str) -> str:
    """Clean and normalize extracted resume text.

    Removes common PDF artifacts like page numbers,
    excessive whitespace, and control characters.

    Args:
        text: Raw extracted text

    Returns:
        Cleaned text
    """
    # Remove page numbers (e.g., "Page 1 of 3", "1/3", standalone numbers)
    text = re.sub(r"(?i)page\s+\d+\s*(of\s*\d+)?", "", text)
    text = re.sub(r"^\s*\d+\s*/\s*\d+\s*$", "", text, flags=re.MULTILINE)

    # Remove control characters
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # Normalize whitespace (preserve paragraph breaks)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def _section_lines(text: str) -> dict[str, list[str]]:
    headings = {
        "summary": r"summary|profile|objective",
        "skills": r"skills|technical skills|core competencies|technologies",
        "experience": r"experience|work experience|professional experience|employment",
        "education": r"education|academic background",
        "projects": r"projects|portfolio",
        "certifications": r"certifications|licenses|credentials",
    }
    sections: dict[str, list[str]] = {key: [] for key in headings}
    current = "summary"
    for raw in text.splitlines():
        line = raw.strip(" -\t")
        if not line:
            continue
        matched = None
        for key, pattern in headings.items():
            if re.fullmatch(pattern, line, flags=re.I):
                matched = key
                break
        if matched:
            current = matched
            continue
        sections.setdefault(current, []).append(line)
    return {key: value[:40] for key, value in sections.items() if value}


def _first_match(pattern: str, text: str) -> str:
    match = re.search(pattern, text, flags=re.I)
    return match.group(0).strip() if match else ""


def resume_text_to_json(text: str, *, metadata: Optional[dict] = None) -> dict:
    """Convert parsed resume text into a stable private JSON shape."""
    cleaned = _clean_resume_text(text or "")
    sections = _section_lines(cleaned)
    try:
        from app.utils.text_processing import extract_relevant_keywords, extract_skills_from_text

        skills = extract_skills_from_text(cleaned)
        keywords = extract_relevant_keywords(cleaned, top_n=60)
    except Exception:
        skills = []
        keywords = []

    urls = sorted(set(re.findall(r"https?://[^\s)>\]]+|(?:linkedin|github)\.com/[^\s)>\]]+", cleaned, flags=re.I)))
    phone = _first_match(r"(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}", cleaned)
    email = _first_match(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", cleaned)

    return {
        "schema_version": "placeup_resume_v1",
        "contact": {
            "email": email,
            "phone": phone,
            "links": urls[:10],
        },
        "summary": " ".join(sections.get("summary", [])[:4])[:1200],
        "skills": sorted(set(skills)),
        "keywords": keywords,
        "sections": sections,
        "experience": sections.get("experience", [])[:30],
        "education": sections.get("education", [])[:20],
        "projects": sections.get("projects", [])[:20],
        "certifications": sections.get("certifications", [])[:20],
        "metadata": metadata or {},
    }
