from mujuthaek_collector.sources.local.apply_center import ApplyCenterSource, page_soup


def test_gh_sso_document_does_not_hide_the_following_notice_document():
    source = ApplyCenterSource("gh")
    prefix = "<!doctype html><html><head><script>var sso=true;</script></head></html>"
    body = (
        prefix
        + """<!doctype html><html><body><table><tbody><tr>
        <td>1</td><td>임대</td><td><a class="text_cut" data-pbancNo="123">행복주택 모집공고</a></td>
        <td>수원</td><td>2026-11-14</td><td>2026-12-01</td><td>접수예정</td>
        </tr></tbody></table></body></html>"""
    )
    items = source.parse_list(source.boards[0], body, source.base)
    assert len(items) == 1 and items[0].post_key == "rent-123"
    assert items[0].title == "행복주택 모집공고"
    assert page_soup(prefix + "<!doctype html><html><body><table><tr><td>상세</td></tr></table></body></html>").find("td").get_text() == "상세"
