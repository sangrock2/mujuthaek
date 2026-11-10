"""정책 수집 테스트용 가짜 부품 (tests/fakes.py의 정책판). 실제 DB 없이 정책 파이프라인 전체를 돌려볼 수 있어요."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from mujuthaek_collector.core.storage import MAX_ATTEMPTS, Intake
from mujuthaek_collector.sources.policy.base import PolicySource
from mujuthaek_collector.sources.policy.store import KnownPolicy
from mujuthaek_platform.ids import uuid7


def list_url(source: PolicySource, page: int = 1, segment: str | None = None) -> str:
    return source.list_request(page, segment).url


def detail_urls(source: PolicySource, item) -> list[str]:
    return [r.url for r in source.detail_requests(item)]


@dataclass
class PolicyMemoryStore:
    """store.PolicyStore 규격을 메모리로 구현해요. 저장된 버전·이벤트를 그대로 꺼내 볼 수 있어요."""

    runs: dict = field(default_factory=dict)
    policies: dict = field(default_factory=dict)
    versions: list = field(default_factory=list)
    intakes: dict = field(default_factory=dict)  # 처음 수집 개수 제한 (fakes.MemoryStore와 같아요)

    @property
    def events(self):
        return [v.event for v in self.versions if v.event]

    def by_key(self, policy_id):
        return next(p for p in self.policies.values() if p.policy_id == policy_id)

    def intake(self, group):
        return self.intakes.get(group, Intake())

    def start_run(self, source_code):
        run_id = uuid7()
        self.runs[run_id] = {"source": source_code}
        return run_id

    def finish_run(self, run_id, status, new_count, warnings):
        self.runs[run_id].update(status=status, new_count=new_count, warnings=list(warnings))

    def known_policies(self, source_code):
        return {p.policy_id: KnownPolicy(p.id, p.marker, p.status) for p in self.policies.values() if p.source_code == source_code}

    def insert_policy(self, policy):
        self.policies.setdefault(policy.id, policy)

    def _set(self, policy_id, title, marker, list_raw, status, kind):
        p = self.policies[policy_id]
        p.title, p.marker, p.list_raw, p.status, p.field, p.attempts, p.last_error = title, marker, list_raw, status, kind, 0, None

    def requeue_policy(self, policy_id, title, marker, list_raw, field, status="PENDING"):
        self._set(policy_id, title, marker, list_raw, status, field)

    def skip_policy(self, policy_id, title, marker, list_raw, field):
        self._set(policy_id, title, marker, list_raw, "SKIPPED", field)

    def queued_policies(self, source_code, limit):
        queued = [
            p
            for p in self.policies.values()
            if p.source_code == source_code and (p.status == "PENDING" or (p.status == "FAILED" and p.attempts < MAX_ATTEMPTS))
        ]
        return sorted(queued, key=lambda p: p.status != "PENDING")[:limit]

    def latest_hash(self, policy_id):
        mine = [v for v in self.versions if v.policy.id == policy_id]
        return (mine[-1].version, mine[-1].content_hash, mine[-1].origin_status) if mine else None

    def latest_files(self, policy_id):
        mine = [v for v in self.versions if v.policy.id == policy_id]
        return [replace(file) for file in mine[-1].files if file.s3_key] if mine else []

    def mark_done(self, policy_id):
        p = self.policies[policy_id]
        p.status, p.attempts, p.last_error = "DONE", 0, None

    def mark_failed(self, policy_id, error):
        p = self.policies[policy_id]
        p.status, p.attempts, p.last_error = "FAILED", p.attempts + 1, error

    def save_version(self, new):
        self.versions.append(new)
        p = self.policies[new.policy.id]
        p.status, p.latest_version, p.attempts, p.field = "DONE", new.version, 0, new.fields.field
