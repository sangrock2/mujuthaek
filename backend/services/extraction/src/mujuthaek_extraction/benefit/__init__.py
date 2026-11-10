"""주거·이주 혜택(정책 수집 field BENEFIT) 정제: 수집 글을 AI로 읽고 출처 코드 칸은 규칙으로 옮겨 policy.extracted를 만듭니다.

모양은 담당자3 초안(contracts/schemas/policy-extracted.draft.md, benefit-condition-types.draft.md)을 그대로 따르고, 계약은
contracts/events/policy.extracted.v1.json입니다(2026-10-25). 받는 쪽은 api benefit 모듈입니다.
"""
