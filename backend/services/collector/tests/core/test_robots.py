from mujuthaek_collector.core.robots import RobotRules

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
