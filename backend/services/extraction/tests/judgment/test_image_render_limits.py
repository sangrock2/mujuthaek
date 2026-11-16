"""그림 판독용 쪽 그리기의 화소 상한 (2026-11-16 보안 감사 M-5).

pdfplumber는 자를 영역과 상관없이 쪽 전체를 그려서, 쪽 크기만 크게 적은 수백 바이트 PDF 하나가 수 GB를 그렸어요.
네트워크·유료 모델 없이 작은 PDF를 직접 만들어 씁니다.
"""

import io

from mujuthaek_extraction import image_reading


def image_page_pdf(width: int, height: int) -> bytes:
    """1×1 회색 그림을 쪽 전체에 늘려 그린 1쪽 PDF."""
    content = f"q {width} 0 0 {height} 0 0 cm /Im0 Do Q".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] /Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>").encode(),
        b"<< /Type /XObject /Subtype /Image /Width 1 /Height 1 /ColorSpace /DeviceGray /BitsPerComponent 8 /Length 1 >>\nstream\n\x80\nendstream",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(out.tell())
        out.write(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def test_a4_page_keeps_the_requested_resolution():
    picture = image_reading._picture(image_page_pdf(595, 842), 1, image_reading.RESOLUTION)
    assert abs(picture.size[0] - 595 * image_reading.RESOLUTION / 72) <= 2


def test_huge_page_is_drawn_within_the_pixel_budget():
    data = image_page_pdf(9000, 9000)
    assert len(data) < 1000
    for resolution in (image_reading.RESOLUTION, image_reading.TILE_RESOLUTION, image_reading.THIRD_RESOLUTION):
        picture = image_reading._picture(data, 1, resolution)
        assert picture.size[0] * picture.size[1] <= image_reading.MAX_RENDER_PIXELS


def test_all_resolutions_shrink_by_the_same_ratio():
    # 세 번째 판독은 200dpi 그림의 행 위치를 400/200배 해서 자르므로, 낮출 때도 비율이 같아야 해요
    data = image_page_pdf(4000, 4000)
    first = image_reading._picture(data, 1, image_reading.RESOLUTION).size[0]
    third = image_reading._picture(data, 1, image_reading.THIRD_RESOLUTION).size[0]
    assert abs(third / first - image_reading.THIRD_RESOLUTION / image_reading.RESOLUTION) < 0.01
