package kr.mujuthaek.api.chat.service;

import static org.mockito.Mockito.*;

import java.time.Clock;
import java.time.OffsetDateTime;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.chat.domain.MessageStatus;
import kr.mujuthaek.api.chat.domain.ReviewAction;
import kr.mujuthaek.api.chat.repository.ChatMessageRepository;
import kr.mujuthaek.api.chat.repository.ChatMessageRepository.MessageRow;
import kr.mujuthaek.api.chat.repository.ChatReportRepository;
import org.junit.jupiter.api.Test;
import org.springframework.context.ApplicationEventPublisher;

class ChatModerationLockTest {
  @Test
  void moderationReadsStateOnlyAfterAcquiringTheDeleteLockAndDoesNotPublishDeletedContent() {
    var messages = mock(ChatMessageRepository.class);
    var reports = mock(ChatReportRepository.class);
    var events = mock(ApplicationEventPublisher.class);
    UUID id = UUID.randomUUID();
    when(messages.find(id, null))
        .thenReturn(
            Optional.of(
                new MessageRow(
                    id,
                    UUID.randomUUID(),
                    UUID.randomUUID(),
                    "alias",
                    null,
                    "private deleted content",
                    0,
                    3,
                    MessageStatus.DELETED,
                    OffsetDateTime.now(),
                    null,
                    null,
                    null,
                    false)));
    new ChatAdminService(messages, reports, events, Clock.systemUTC())
        .review(id, ReviewAction.RESTORE, UUID.randomUUID());
    var order = inOrder(messages);
    order.verify(messages).lockMessage(id);
    order.verify(messages).find(id, null);
    verify(messages, never()).review(any(), any(), anyBoolean());
    verifyNoInteractions(events);
  }
}
