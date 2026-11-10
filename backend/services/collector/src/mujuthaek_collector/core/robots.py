"""robots.txt 해석 (RFC 9309).

파이썬 기본 해석기(urllib.robotparser)는 '/*.xls$' 같은 * · $ 패턴을 이해하지 못해서 직접 구현해요.
- 우리 수집기 이름과 맞는 그룹이 있으면 그 그룹, 없으면 '*' 그룹
- 주소의 경로+쿼리에 맞는 규칙 중 가장 긴 것을 따르고, 길이가 같으면 Allow
- 맞는 규칙이 없으면 허용
"""

import re
import urllib.parse


class RobotRules:
    def __init__(self, text: str, agent: str):
        groups: list[dict] = []
        current: dict | None = None
        rules_started = False
        for raw in text.splitlines():
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
        regex = re.escape(pattern).replace(r"\*", ".*")
        if regex.endswith(r"\$"):
            regex = regex[:-2] + "$"
        return re.match(regex, path) is not None

    def can_fetch(self, url: str) -> bool:
        parts = urllib.parse.urlsplit(url)
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        hits = [(len(pattern), allow) for allow, pattern in self.rules if self._matches(pattern, path)]
        if not hits:
            return True
        longest = max(length for length, _ in hits)
        return any(allow for length, allow in hits if length == longest)


ALLOW_ALL = RobotRules("", "any")
