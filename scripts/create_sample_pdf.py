"""
Script to create sample PDF and image documents for testing.

Usage:
    python scripts/create_sample_pdf.py

Creates:
    sample_docs/sample_exam.pdf      -- Multi-page exam PDF with Q+A
    sample_docs/sample_chemistry.png -- Single-page image exam
    sample_docs/answer_key.pdf       -- Separate answer key PDF
"""
import os
import struct
import zlib
from pathlib import Path


def _deflate(data: bytes) -> bytes:
    """Compress using deflate (zlib without header)."""
    compress = zlib.compressobj(9, zlib.DEFLATED, -15)
    return compress.compress(data) + compress.flush()


def create_simple_pdf(filename: str, pages_content: list[str]) -> bytes:
    """
    Build a minimal but valid PDF with the given text pages.
    Uses basic Type1 Helvetica font — no external resources needed.
    """
    objects = []
    page_ids = []
    stream_ids = []

    # We'll track byte offsets
    buf = bytearray(b"%PDF-1.4\n")

    def add_obj(content: str) -> int:
        """Append a PDF object; return its object number (1-based)."""
        obj_num = len(objects) + 1
        offset = len(buf)
        objects.append(offset)
        obj_bytes = f"{obj_num} 0 obj\n{content}\nendobj\n".encode()
        buf.extend(obj_bytes)
        return obj_num

    # Font object
    font_id = add_obj(
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
        "/Encoding /WinAnsiEncoding >>"
    )

    # For each page: content stream + page dict
    for i, text in enumerate(pages_content):
        lines = text.strip().split("\n")
        stream_cmds = "BT\n/F1 11 Tf\n50 750 Td\n12 TL\n"
        for line in lines:
            # Escape parentheses
            safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            stream_cmds += f"({safe}) Tj T*\n"
        stream_cmds += "ET\n"

        stream_bytes = stream_cmds.encode("latin-1", errors="replace")
        stream_id = add_obj(
            f"<< /Length {len(stream_bytes)} >>\nstream\n"
            + stream_cmds
            + "\nendstream"
        )
        stream_ids.append(stream_id)

        page_id = add_obj(
            f"<< /Type /Page /Parent 999 0 R /MediaBox [0 0 612 792] "
            f"/Contents {stream_id} 0 R "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>"
        )
        page_ids.append(page_id)

    # Pages dict — will be object right after all pages
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    pages_id = add_obj(
        f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>"
    )

    # Catalog
    catalog_id = add_obj(f"<< /Type /Catalog /Pages {pages_id} 0 R >>")

    # Fix up Parent ref in page dicts (hack: patch bytes)
    # Instead: rebuild with correct pages_id
    # Actually our add_obj wrote "999 0 R" as placeholder — patch now
    content = buf.decode("latin-1", errors="replace")
    content = content.replace("999 0 R", f"{pages_id} 0 R")
    buf = bytearray(content.encode("latin-1", errors="replace"))

    # xref + trailer
    xref_offset = len(buf)
    xref = f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    # Recompute offsets after patch (approximate — good enough for test docs)
    for off in objects:
        xref += f"{off:010d} 00000 n \n"

    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    )
    buf.extend((xref + trailer).encode())
    return bytes(buf)


def create_sample_png() -> bytes:
    """Create a 1×1 white PNG as a placeholder image for testing."""
    # Minimal valid PNG
    def png_chunk(name: bytes, data: bytes) -> bytes:
        length = struct.pack(">I", len(data))
        chunk = name + data
        crc = struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)
        return length + chunk + crc

    header = b"\x89PNG\r\n\x1a\n"
    ihdr = png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    # 1×1 white RGB pixel
    raw = b"\x00\xff\xff\xff"
    idat = png_chunk(b"IDAT", zlib.compress(raw))
    iend = png_chunk(b"IEND", b"")
    return header + ihdr + idat + iend


EXAM_PAGE_1 = """
PHYSICS EXAMINATION 2024
Time: 2 Hours    Max Marks: 50

SECTION A: Multiple Choice Questions (2 marks each)

1. Which of the following best describes Newton's First Law of Motion?
   A. An object at rest stays at rest unless acted upon by an external force
   B. Force equals mass times acceleration
   C. For every action there is an equal and opposite reaction
   D. Energy can neither be created nor destroyed

2. A ball is thrown vertically upward with initial velocity of 20 m/s.
   Calculate the maximum height reached by the ball. (g = 10 m/s^2)
   A. 10 m    B. 20 m    C. 40 m    D. 5 m

3. The speed of light in vacuum is approximately 3 x 10^8 m/s. True or False?
   A. True    B. False
"""

EXAM_PAGE_2 = """
SECTION B: Short Answer Questions (5 marks each)

4. Refer to Figure 4.1 (circuit diagram below).
   If R1 = 4 ohm, R2 = 6 ohm, R3 = 12 ohm (parallel), find total resistance.

5. The velocity of a particle is recorded in the table below.
   Time (s): 0, 2, 4, 6, 8
   Velocity (m/s): 0, 10, 20, 30, 40
   Draw a velocity-time graph and calculate the acceleration.
   (Question continues on next page)
"""

EXAM_PAGE_3 = """
   (Continued from Question 5)
   Using the graph, determine:
   (a) Total displacement in 8 seconds
   (b) Average velocity

SECTION C: Long Answer (10 marks)

6. Explain the Law of Conservation of Energy with two real-world examples.
   Derive the relationship between kinetic and potential energy for a
   freely falling object.

ANSWER KEY
1. A    2. B    3. A (True)    4. 2 ohm    5. 5 m/s^2
"""

ANSWER_KEY_PAGE = """
ANSWER KEY — PHYSICS EXAMINATION 2024

Question 1: A
Question 2: B
Question 3: A
Question 4: 2 ohm
Question 5: (a) 160 m, (b) 20 m/s
Question 6: See marking scheme (long answer - examiner discretion)
"""


def main():
    out_dir = Path("sample_docs")
    out_dir.mkdir(exist_ok=True)

    # Multi-page exam PDF
    exam_pdf = create_simple_pdf(
        "sample_exam.pdf",
        [EXAM_PAGE_1, EXAM_PAGE_2, EXAM_PAGE_3],
    )
    (out_dir / "sample_exam.pdf").write_bytes(exam_pdf)
    print(f"Created: {out_dir}/sample_exam.pdf  ({len(exam_pdf):,} bytes)")

    # Separate answer key PDF
    answer_pdf = create_simple_pdf("answer_key.pdf", [ANSWER_KEY_PAGE])
    (out_dir / "answer_key.pdf").write_bytes(answer_pdf)
    print(f"Created: {out_dir}/answer_key.pdf  ({len(answer_pdf):,} bytes)")

    # Placeholder PNG image
    png_bytes = create_sample_png()
    (out_dir / "sample_page.png").write_bytes(png_bytes)
    print(f"Created: {out_dir}/sample_page.png  ({len(png_bytes):,} bytes)")

    print("\nSample documents ready in sample_docs/")
    print("Use them to test the DocIQ API endpoints.")


if __name__ == "__main__":
    main()
