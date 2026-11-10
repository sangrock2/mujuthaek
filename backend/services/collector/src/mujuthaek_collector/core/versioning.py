"""원본이 바뀌었는지 판단하는 해시. 본문 + 첨부 파일 해시가 같으면 같은 버전이에요."""

import hashlib


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def content_hash(body_text: str, file_hashes: list[str]) -> str:
    digest = hashlib.sha256(body_text.encode("utf-8"))
    for value in sorted(file_hashes):
        digest.update(value.encode("ascii"))
    return digest.hexdigest()


def list_hash(keys: list[str]) -> str:
    """목록 1페이지가 지난번과 같은지 보는 해시 (글번호·제목·날짜·상태). 조회수는 매번 바뀌어서 넣지 않아요."""
    return hashlib.sha256("\n".join(keys).encode("utf-8")).hexdigest()
