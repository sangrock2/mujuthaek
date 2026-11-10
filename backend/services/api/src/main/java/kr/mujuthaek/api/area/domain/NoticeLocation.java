package kr.mujuthaek.api.area.domain;

import java.util.UUID;

/**
 * 좌표를 찾을 공고 위치 하나. notice가 보내는 NoticeLocationsChanged의 위치 한 줄과 같아요(연결은 연결 PR).
 *
 * @param noticeLocationId 공고 안에서 위치를 가리키는 ID (공고 상세 locations[].id, 예: building-a)
 * @param kind 위치 종류 (COMPLEX, BUILDING, SITE, UNKNOWN)
 * @param address 원문 주소 (모르면 null)
 * @param bjdCode 공고가 준 법정동코드 10자리 (모르면 null)
 */
public record NoticeLocation(
    UUID noticeId,
    int noticeVersion,
    String noticeLocationId,
    String kind,
    String address,
    String bjdCode) {}
