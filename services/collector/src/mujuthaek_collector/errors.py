"""수집기 오류 네 가지. 오류 종류에 따라 반응이 달라요."""


class CollectorError(Exception):
    pass


class BlockedError(CollectorError):
    """robots.txt 금지, 403·429, 대기실 화면. 그 출처의 이번 회차를 멈춰요 (crawl_runs = BLOCKED)."""


class RobotsUnavailable(BlockedError):
    """robots.txt를 받지 못함(연결 오류·5xx). 목록·상세면 회차를 멈추고, 첨부면 다음에 다시 받아요(FileNotReady)."""


class FileRejected(CollectorError):
    """이 파일은 받지 않아요: robots.txt가 막은 경로로 넘겨짐, 크기 초과."""


class FileNotReady(FileRejected):
    """지금은 받지 못했지만 다음엔 받아질 수 있는 첨부: 그 도메인의 robots.txt를 잠시 못 받음, 파일 대신 웹페이지(점검 화면 등)가 옴.
    수집 파이프라인은 다시 시도할 수 있으면 FileUnavailable처럼 다음 회차에 다시 받아요(2026-11-10 재검토: 그 파일 없이 새 버전이 생기고
    다음 회차에 되돌아갔음)."""


class FileUnavailable(CollectorError):
    """첨부를 잠시 받지 못했어요(연결 오류·5xx). 그 파일 없이 새 버전을 만들지 않고 다음에 다시 받아요."""


class ParseError(CollectorError):
    """화면 구조가 예상과 달라요. 그 글만 건너뛰고 경고를 남겨요 (사이트 구조 변경 신호)."""
