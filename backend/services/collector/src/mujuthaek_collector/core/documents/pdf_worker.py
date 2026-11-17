"""No network client or service configuration: only a bounded local PDF input/output."""

import json
import sys
from pathlib import Path


def main() -> int:
    if sys.platform == "linux":
        import resource

        # 파서가 작은 PDF의 압축 스트림/도형을 크게 펼쳐도 부모 수집기는 살아 있어요.
        resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024 * 1024,) * 2)
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from mujuthaek_collector.core.documents.text import _pdf_text

    try:
        result = _pdf_text(Path(sys.argv[1]))
        sys.stdout.write(json.dumps(result))
        return 0
    except Exception:
        # 문서 내용·파일 경로·파서 예외의 원문은 부모나 로그에 전달하지 않아요.
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
