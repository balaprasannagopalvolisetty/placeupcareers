"""
PlaceUp Career — Resume Parser Service
Extracts text from PDF and DOCX resume files.
"""

import io
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


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
    try:
        from PyPDF2 import PdfReader

        reader = PdfReader(io.BytesIO(content))
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
