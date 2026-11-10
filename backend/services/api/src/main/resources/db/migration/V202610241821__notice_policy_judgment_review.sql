-- 정책 판정 틀의 검수 상태 (2026-10-22 리뷰): 같은 버전의 승인본(APPROVED)을 다시 받은 자동·검수 대기 결과로 덮지 않게 저장해요.
alter table notice.policy_judgments
    add column review_status text not null default 'AUTO_PASSED'
        check (review_status in ('AUTO_PASSED', 'PARTIALLY_PASSED', 'IN_REVIEW', 'APPROVED'));
