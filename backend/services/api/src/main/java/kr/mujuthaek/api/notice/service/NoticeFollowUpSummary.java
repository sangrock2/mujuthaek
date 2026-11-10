package kr.mujuthaek.api.notice.service;

import java.time.LocalDate;
import java.util.UUID;

/**
 * 다른 모듈(알림)이 조회하는 후속 안내 한 건 (NoticeQueryService.findLatestFollowUp).
 *
 * @param followUpId 후속 안내 글 ID (수집 원본 글 ID). 같은 글이 새 버전으로 바뀌어도 같아요
 * @param title 후속 안내 글 제목
 * @param postedOn 게시일 (모르면 null)
 */
public record NoticeFollowUpSummary(UUID followUpId, String title, LocalDate postedOn) {}
