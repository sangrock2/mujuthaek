"""수집기 오류 네 가지. 오류 종류에 따라 반응이 달라요."""


class CollectorError(Exception):
    pass


class BlockedError(CollectorError):
    """robots.txt 금지, 403·429, 대기실 화면. 그 출처의 이번 회차를 멈춰요 (crawl_runs = BLOCKED)."""


class FileRejected(CollectorError):
    """이 파일은 받지 않아요: robots.txt가 막은 경로로 넘겨짐, 크기 초과, 파일 대신 웹페이지가 옴."""


class FileUnavailable(CollectorError):
    """첨부를 잠시 받지 못했어요(연결 오류·5xx). 그 파일 없이 새 버전을 만들지 않고 다음에 다시 받아요."""


class ParseError(CollectorError):
    """화면 구조가 예상과 달라요. 그 글만 건너뛰고 경고를 남겨요 (사이트 구조 변경 신호)."""
