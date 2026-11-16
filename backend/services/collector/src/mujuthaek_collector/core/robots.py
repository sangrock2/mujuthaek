"""robots.txt 해석 (RFC 9309).

파이썬 기본 해석기(urllib.robotparser)는 '/*.xls$' 같은 * · $ 패턴을 이해하지 못해서 직접 구현해요.
- 우리 수집기 이름과 맞는 그룹이 있으면 그 그룹, 없으면 '*' 그룹
- 주소의 경로+쿼리에 맞는 규칙 중 가장 긴 것을 따르고, 길이가 같으면 Allow
- 맞는 규칙이 없으면 허용

패턴은 정규식으로 바꾸지 않고 앞에서부터 차례로 찾아 맞춰요(입력 길이에 비례하는 시간). 예전엔 '*'를 '.*'로 바꿔
re.match로 맞췄는데, 'Disallow: /*a*a*a…b' 같은 몇십 바이트 규칙 하나로 역추적이 폭증해 수집기 전체가 멈췄어요
(2026-11-16 보안 감사 H-4). robots.txt는 RFC 9309가 요구하는 앞 500KiB까지만 읽어요.
"""

import urllib.parse

MAX_ROBOTS_CHARS = 500 * 1024


class RobotRules:
    def __init__(self, text: str, agent: str):
        groups: list[dict] = []
        current: dict | None = None
        rules_started = False
        for raw in text[:MAX_ROBOTS_CHARS].splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            field, value = (part.strip() for part in line.split(":", 1))
            field = field.lower()
            if field == "user-agent":
                if current is None or rules_started:
                    current, rules_started = {"agents": [], "rules": []}, False
                    groups.append(current)
                current["agents"].append(value.lower())
            elif field in ("allow", "disallow") and current is not None:
                rules_started = True
                if value:  # 빈 Disallow는 '전부 허용'이라 규칙으로 넣지 않음
                    current["rules"].append((field == "allow", value))
        token = agent.lower().split("/")[0]
        mine = [g for g in groups if any(a != "*" and a in token for a in g["agents"])]
        chosen = mine or [g for g in groups if "*" in g["agents"]]
        self.rules: list[tuple[bool, str]] = [rule for group in chosen for rule in group["rules"]]

    @staticmethod
    def _matches(pattern: str, path: str) -> bool:
        """경로가 패턴으로 시작하는지. '*'는 아무 글자나 0개 이상, 끝의 '$'는 경로의 끝이에요(가운데 '$'는 글자 그대로).

        '*'로 나눈 조각을 왼쪽부터 가장 먼저 나오는 자리에 맞춰요. 앞 조각을 가장 이르게 맞춰야 뒤 조각이 맞을 자리가 가장 넓어서,
        맞는 방법이 하나라도 있으면 이 방법도 맞아요.
        """
        anchored = pattern.endswith("$")
        if anchored:
            pattern = pattern[:-1]
        first, *rest = pattern.split("*")
        if not path.startswith(first):
            return False
        position = len(first)
        if not rest:
            return not anchored or position == len(path)
        *middle, last = rest
        for part in middle:
            found = path.find(part, position)
            if found < 0:
                return False
            position = found + len(part)
        if anchored:
            return len(path) - len(last) >= position and path.endswith(last)
        return path.find(last, position) >= 0

    def can_fetch(self, url: str) -> bool:
        parts = urllib.parse.urlsplit(url)
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        hits = [(len(pattern), allow) for allow, pattern in self.rules if self._matches(pattern, path)]
        if not hits:
            return True
        longest = max(length for length, _ in hits)
        return any(allow for length, allow in hits if length == longest)


ALLOW_ALL = RobotRules("", "any")
