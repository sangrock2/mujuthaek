import itertools
import re
import time

from mujuthaek_collector.core.robots import MAX_ROBOTS_CHARS, RobotRules

RULES = """User-agent: *
Disallow: /*.xls$
Disallow: /mypage/
Allow: /mypage/public/
"""


def test_star_and_dollar_patterns():
    rules = RobotRules(RULES, "MujuthaekBot/0.1")
    assert not rules.can_fetch("https://a.kr/files/list.xls")
    assert rules.can_fetch("https://a.kr/files/list.xlsx")  # $는 끝을 뜻해서 .xlsx는 허용
    assert not rules.can_fetch("https://a.kr/mypage/info")


def test_longest_rule_wins():
    assert RobotRules(RULES, "MujuthaekBot/0.1").can_fetch("https://a.kr/mypage/public/a")


def test_own_group_beats_star_group():
    text = "User-agent: Googlebot\nDisallow: /main/bbs/\n\nUser-agent: *\nDisallow:\n"
    assert RobotRules(text, "MujuthaekBot/0.1").can_fetch("https://www.ih.co.kr/main/bbs/bbsMsgList.do")  # iH: 구글만 막음
    assert not RobotRules(text, "Googlebot/2.1").can_fetch("https://www.ih.co.kr/main/bbs/bbsMsgList.do")


def test_query_is_part_of_path():
    rules = RobotRules("User-agent: *\nDisallow: /*?print=", "MujuthaekBot")
    assert not rules.can_fetch("https://a.kr/view.do?print=1")
    assert rules.can_fetch("https://a.kr/view.do?id=1")


def _old_regex_match(pattern: str, path: str) -> bool:
    """예전 정규식 방식 (뜻 비교용). 겹치는 '*'가 많으면 역추적이 폭증해서 운영에서는 쓰지 않아요."""
    regex = re.escape(pattern).replace(r"\*", ".*")
    if regex.endswith(r"\$"):
        regex = regex[:-2] + "$"
    return re.match(regex, path) is not None


def test_glob_matcher_agrees_with_the_old_regex_semantics():
    patterns = [
        "/", "/a", "/a$", "/*", "/*$", "/a*", "/a*b", "/a*b$", "/*a*a$", "/a*a$", "/*.xls$", "/a$b",
        "/a$b$", "/*?print=", "/**a", "/a**b$", "$", "/*/*", "/x*y*z",
    ]
    paths = ["/", "/a", "/aa", "/ab", "/aab", "/aba", "/a$b", "/files/list.xls", "/files/list.xlsx",
             "/view.do?print=1", "/x/y/z", "/xyz", "/xzy", "/b", "/a/b/"]
    for pattern, path in itertools.product(patterns, paths):
        assert RobotRules._matches(pattern, path) == _old_regex_match(pattern, path), (pattern, path)


def test_overlapping_wildcards_cannot_stall_the_collector():
    # 예전 정규식은 '*a'가 7개일 때 40자 경로에 0.3초, 하나 늘 때마다 약 5배 늘었어요(14개면 수 시간)
    text = "User-agent: *\nDisallow: /" + "*a" * 30 + "*b\n"
    rules = RobotRules(text, "MujuthaekBot/0.1")
    started = time.perf_counter()
    assert rules.can_fetch("https://evil.example/" + "a" * 20_000)
    assert not rules.can_fetch("https://evil.example/" + "a" * 40 + "b")
    assert time.perf_counter() - started < 1.0


def test_reads_only_the_first_500_kib():
    padding = "#" + "x" * MAX_ROBOTS_CHARS + "\n"
    text = "User-agent: *\nDisallow: /early\n" + padding + "Disallow: /late\n"
    rules = RobotRules(text, "MujuthaekBot/0.1")
    assert not rules.can_fetch("https://a.kr/early")
    assert rules.can_fetch("https://a.kr/late")
