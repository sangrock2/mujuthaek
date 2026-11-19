"""PDF 전용 자식. 운영 자격증명은 전달받지 않고 원문·오류 내용을 출력하지 않습니다."""

import json
import sys
from dataclasses import asdict
from pathlib import Path


def main() -> int:
    if sys.platform == "linux":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024,) * 2)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from mujuthaek_extraction.intake import pdf_reader

    source, mode, pages = sys.argv[1:]
    pdf_reader.MAX_PAGES = min(300, max(0, int(pages)))
    data = Path(source).read_bytes()
    if mode == "document":
        document = pdf_reader._read_pdf_inline(data)
        result = asdict(document) if document is not None else None  # filled 등 병합 칸 정보도 보존합니다
    elif mode == "images":
        result = pdf_reader._find_image_pages_inline(data)
    else:
        return 1
    json.dump(result, sys.stdout, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit(1) from None
