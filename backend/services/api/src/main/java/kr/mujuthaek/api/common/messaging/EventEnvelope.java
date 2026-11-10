package kr.mujuthaek.api.common.messaging;

import java.util.UUID;
import tools.jackson.databind.JsonNode;

/**
 * 파이썬 프로그램(collector·extraction)이 보내는 이벤트 봉투. 모양은 contracts/events/*.json과 같아요.
 *
 * @param payload 이벤트 종류마다 다른 본문. {@link EventInbox}가 받는 쪽 record로 바꿔 줘요
 */
public record EventEnvelope(
    UUID eventId,
    String eventType,
    int schemaVersion,
    String occurredAt,
    String producer,
    JsonNode payload) {}
