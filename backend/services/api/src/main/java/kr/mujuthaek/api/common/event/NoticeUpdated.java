package kr.mujuthaek.api.common.event;

import java.util.List;
import java.util.UUID;

/**
 * 공개된 공고가 바뀜. 정정·새 버전 외에 후속 안내가 붙거나 공고를 합치거나 되돌린 때도 보내요. 바뀐 값 자체는 싣지 않으니 NoticeQueryService로 조회하세요.
 *
 * <p>changedFields에는 칸 이름(applyEnd 등)이 아니라 바뀐 부분의 이름이 들어가요. 들어갈 수 있는 값:
 *
 * <ul>
 *   <li>새 버전(정정 등)일 때 이전 공개 버전과 비교해 달라진 섹션, 정해진 순서대로: notice(공고 개요: 제목·기관·공고일 등), locations(단지·건물
 *       위치), supplyGroups(주택형별 공급), schedules(일정), eligibility(자격 조건), selectionRules(선정 기준),
 *       requiredDocuments(제출 서류), guidance(유의 사항 등 안내), conditions(판정용 조건), heldItems(원문 확인 전까지 보류한
 *       항목), applicationWindows(접수 기간), judgment(판정 틀). 새 버전이면 하나 이상 들어가요
 *   <li>followUps 하나만: 후속 안내(서류심사 대상자 발표 등)가 붙거나 바뀜. 공고 버전은 그대로예요
 *   <li>sources 하나만: 같은 공고를 합치거나(noticeId는 남은 공고) 합치기를 되돌림(두 공고 모두에 보내요). 공고 버전은 바뀌지 않을 수도 있어요
 * </ul>
 *
 * @param field 공고 분야 HOUSING · BUSINESS_SPACE
 * @param changedFields 바뀐 부분의 이름 (위 목록)
 * @param reprocess 과거 공고 재처리 중 바뀐 것이면 true (사용자 알림을 보내지 않아요)
 */
public record NoticeUpdated(
    UUID noticeId, String field, List<String> changedFields, boolean reprocess) {}
