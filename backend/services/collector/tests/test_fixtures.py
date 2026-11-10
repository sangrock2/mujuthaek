"""실제 사이트에서 저장한 화면(tests/fixtures/<출처>/)으로 파서를 확인해요.

화면 저장: uv run python -m mujuthaek_collector save-fixtures <출처>
저장한 화면이 없는 출처는 건너뛰어요. 기관이 화면을 바꿔 수집기를 고칠 때는 화면도 다시 저장해요.
"""

from pathlib import Path

import pytest

from mujuthaek_collector.sources.base import ListItem
from mujuthaek_collector.sources.registry import SOURCES

FIXTURES = Path(__file__).parent / "fixtures"


def saved(code):
    folder = FIXTURES / code
    return sorted(folder.glob("*-list.*")) if folder.is_dir() else []


@pytest.mark.parametrize("code", sorted(SOURCES))
def test_saved_pages_parse(code):
    lists = saved(code)
    if not lists:
        pytest.skip(f"{code}: 저장한 화면이 없어요 (save-fixtures {code})")
    source = SOURCES[code]
    for path in lists:
        board_key = path.name.split("-list.")[0]
        board = next(b for b in source.boards if b.key == board_key)
        items = source.parse_list(board, path.read_text(encoding="utf-8"), source.list_request(board, 1).url)
        assert items, f"{path.name}: 목록이 비어 있어요"
        assert all(i.post_key and i.title for i in items), f"{path.name}: 글 키나 제목이 빈 글이 있어요"
        for detail_path in sorted(path.parent.glob(f"{board_key}-detail-*.html")):
            post_key = detail_path.stem.split("-detail-", 1)[1]
            item = next((i for i in items if i.post_key == post_key), None) or ListItem(board_key, post_key, "", None, None)
            detail = source.parse_detail(item, detail_path.read_text(encoding="utf-8"))
            assert detail.body_text, f"{detail_path.name}: 본문을 읽지 못했어요"
