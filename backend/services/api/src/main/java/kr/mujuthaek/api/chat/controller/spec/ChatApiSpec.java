package kr.mujuthaek.api.chat.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.UUID;
import kr.mujuthaek.api.chat.dto.request.ReportRequest;
import kr.mujuthaek.api.chat.dto.request.SendMessageRequest;
import kr.mujuthaek.api.chat.dto.response.ChatMessageResponse;
import kr.mujuthaek.api.chat.dto.response.ChatRoomResponse;
import kr.mujuthaek.api.chat.dto.response.LikeResponse;
import kr.mujuthaek.api.common.dto.response.CursorPageResponse;
import kr.mujuthaek.api.user.service.LoginUser;
import org.springframework.http.ResponseEntity;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@Tag(
    name = "공고 채팅",
    description =
        "공고마다 하나인 채팅방이에요. 방 정보·메시지 목록·실시간 받기(SSE)는 로그인 없이, " + "보내기·삭제·좋아요·신고는 로그인한 회원만 돼요.")
public interface ChatApiSpec {

  @Operation(
      summary = "채팅방 정보",
      description =
          "읽기 전용인지, 읽기 전용이 되는 날(접수 마감일 + 31일, 상시 공고는 null), 늘 보여줄 안내 문구를 줘요. "
              + "다른 공고에 합쳐진 공고면 남은 공고의 방이라 noticeId가 물은 ID와 달라요.")
  @ApiResponse(responseCode = "200", description = "채팅방 정보")
  @ApiResponse(responseCode = "404", description = "NOTICE_NOT_FOUND — 공고가 없거나 공개되지 않았어요")
  ChatRoomResponse room(@Parameter(description = "공고 ID") UUID noticeId);

  @Operation(
      summary = "메시지 목록",
      description =
          "최신순이고 답장도 같은 목록에 섞여요. 응답의 nextCursor를 다음 요청의 cursor로 넘기면 이어서 받아요(hasNext가 false면 끝). "
              + "로그인했으면 likedByMe·mine이 채워지고, 아니면 false예요.")
  @ApiResponse(responseCode = "200", description = "메시지 목록")
  @ApiResponse(
      responseCode = "400",
      description = "VALIDATION_FAILED — size가 1~100 밖이에요. INVALID_CURSOR — cursor가 올바르지 않아요")
  @ApiResponse(responseCode = "404", description = "NOTICE_NOT_FOUND — 공고가 없거나 공개되지 않았어요")
  CursorPageResponse<ChatMessageResponse> messages(
      @Parameter(description = "공고 ID") UUID noticeId,
      @Parameter(description = "이전 응답의 nextCursor. 첫 요청이면 비워요") String cursor,
      @Parameter(description = "한 번에 받을 개수 (기본 30, 1~100)", example = "30") Integer size,
      @Parameter(hidden = true) LoginUser user);

  @Operation(
      summary = "메시지 보내기·답장",
      description =
          "content는 앞뒤 공백을 지우고 1~500자예요(이모지도 한 글자). 답장이면 parentId에 같은 방의 보이는 메시지 ID를 넣어요. "
              + "만든 메시지(mine = true)를 돌려주고, 같은 메시지가 SSE message.created로도 와요(화면은 ID로 한 번 걸러요).")
  @ApiResponse(responseCode = "201", description = "보낸 메시지")
  @ApiResponse(
      responseCode = "400",
      description =
          "CHAT_INVALID_CONTENT — 본문이 비었거나 500자를 넘어요. "
              + "CHAT_PERSONAL_INFO — 휴대폰 번호·주민등록번호가 있어요. "
              + "CHAT_REPLY_DEPTH — 답장에는 답장할 수 없어요")
  @ApiResponse(responseCode = "401", description = "UNAUTHENTICATED — 로그인하지 않았어요")
  @ApiResponse(
      responseCode = "404",
      description =
          "NOTICE_NOT_FOUND — 공고가 없거나 공개되지 않았어요. "
              + "CHAT_MESSAGE_NOT_FOUND — 답장 대상이 없거나, 다른 방 메시지거나, 보이지 않는 메시지예요")
  @ApiResponse(responseCode = "409", description = "CHAT_READ_ONLY — 읽기 전용이 된 채팅방이에요")
  @ApiResponse(
      responseCode = "429",
      description = "CHAT_RATE_LIMITED — 1분에 5개를 넘었어요. Retry-After 헤더에 다시 보낼 수 있을 때까지의 초가 있어요")
  ResponseEntity<ChatMessageResponse> send(
      @Parameter(description = "공고 ID") UUID noticeId,
      SendMessageRequest request,
      @Parameter(hidden = true) LoginUser user);

  @Operation(
      summary = "내 메시지 삭제",
      description =
          "읽기 전용 방에서도 돼요. 목록에는 DELETED 상태로 본문 없이 남고, 방에 붙은 연결에는 SSE message.deleted가 가요. "
              + "이미 지운 메시지여도 204예요.")
  @ApiResponse(responseCode = "204", description = "지웠어요")
  @ApiResponse(responseCode = "401", description = "UNAUTHENTICATED — 로그인하지 않았어요")
  @ApiResponse(responseCode = "403", description = "CHAT_NOT_OWNER — 내가 쓴 메시지가 아니에요")
  @ApiResponse(responseCode = "404", description = "CHAT_MESSAGE_NOT_FOUND — 없는 메시지예요")
  ResponseEntity<Void> delete(
      @Parameter(description = "메시지 ID") UUID id, @Parameter(hidden = true) LoginUser user);

  @Operation(
      summary = "좋아요",
      description = "여러 번 불러도 결과가 같아요. 바뀐 좋아요 수와 내 좋아요 상태를 돌려주고, 수가 바뀌면 SSE like.updated가 가요.")
  @ApiResponse(responseCode = "200", description = "좋아요 결과")
  @ApiResponse(responseCode = "401", description = "UNAUTHENTICATED — 로그인하지 않았어요")
  @ApiResponse(
      responseCode = "404",
      description =
          "CHAT_MESSAGE_NOT_FOUND — 없거나 보이지 않는(삭제·가림) 메시지예요. "
              + "NOTICE_NOT_FOUND — 메시지가 있는 공고가 공개되지 않았어요")
  @ApiResponse(responseCode = "409", description = "CHAT_READ_ONLY — 읽기 전용이 된 채팅방이에요")
  LikeResponse like(
      @Parameter(description = "메시지 ID") UUID id, @Parameter(hidden = true) LoginUser user);

  @Operation(
      summary = "좋아요 취소",
      description = "여러 번 불러도 결과가 같아요. 바뀐 좋아요 수와 내 좋아요 상태를 돌려주고, 수가 바뀌면 SSE like.updated가 가요.")
  @ApiResponse(responseCode = "200", description = "좋아요 취소 결과")
  @ApiResponse(responseCode = "401", description = "UNAUTHENTICATED — 로그인하지 않았어요")
  @ApiResponse(
      responseCode = "404",
      description = "CHAT_MESSAGE_NOT_FOUND — 없는 메시지예요. NOTICE_NOT_FOUND — 메시지가 있는 공고가 공개되지 않았어요")
  @ApiResponse(responseCode = "409", description = "CHAT_READ_ONLY — 읽기 전용이 된 채팅방이에요")
  LikeResponse unlike(
      @Parameter(description = "메시지 ID") UUID id, @Parameter(hidden = true) LoginUser user);

  @Operation(
      summary = "메시지 신고",
      description =
          "읽기 전용 방에서도 돼요. reason은 꼭 있어야 하고, detail(기타 사유)은 200자까지예요. "
              + "검토 전 신고가 3건이 되면 메시지를 자동으로 가리고(HIDDEN_REPORTED) 관리자 검토를 기다려요.")
  @ApiResponse(responseCode = "201", description = "신고했어요")
  @ApiResponse(
      responseCode = "400",
      description = "VALIDATION_FAILED — reason이 없거나 detail이 200자를 넘어요")
  @ApiResponse(responseCode = "401", description = "UNAUTHENTICATED — 로그인하지 않았어요")
  @ApiResponse(responseCode = "404", description = "CHAT_MESSAGE_NOT_FOUND — 없거나 삭제된 메시지예요")
  @ApiResponse(responseCode = "409", description = "CHAT_ALREADY_REPORTED — 이미 신고한 메시지예요")
  ResponseEntity<Void> report(
      @Parameter(description = "메시지 ID") UUID id,
      ReportRequest request,
      @Parameter(hidden = true) LoginUser user);

  @Operation(
      summary = "실시간 받기 (SSE)",
      description =
          "text/event-stream이에요. 로그인이 필요 없어서 EventSource로 바로 붙어요. 합쳐진 공고 ID로 붙어도 남은 공고의 방이에요. "
              + "이벤트: message.created(id = 메시지 ID)·message.restored는 메시지 하나, "
              + "message.deleted·message.hidden은 {id}, like.updated는 {id, likeCount}예요. "
              + "붙자마자 주석 connected, 25초마다 주석 ping이 와요(화면은 무시해요). "
              + "연결은 30분 뒤 정상으로 닫히고 브라우저가 다시 붙어요. "
              + "다시 붙을 때 Last-Event-ID가 있으면 그 메시지 뒤에 온 메시지를 최대 100개까지 message.created로 먼저 보내요.")
  @ApiResponse(
      responseCode = "200",
      description = "이벤트 스트림 (위 설명의 이벤트가 연결이 닫힐 때까지 이어서 와요)",
      content =
          @Content(
              mediaType = "text/event-stream",
              schema = @Schema(type = "string"),
              examples =
                  @ExampleObject(
                      value =
                          """
                          : connected

                          event: message.created
                          id: 0193f0c2-6a1e-7c3d-9a4b-2f1e8d7c6b5a
                          data: {"id":"0193f0c2-6a1e-7c3d-9a4b-2f1e8d7c6b5a","noticeId":"…","content":"…"}

                          event: like.updated
                          data: {"id":"0193f0c2-6a1e-7c3d-9a4b-2f1e8d7c6b5a","likeCount":3}

                          event: message.hidden
                          data: {"id":"0193f0c2-6a1e-7c3d-9a4b-2f1e8d7c6b5a"}
                          """)))
  @ApiResponse(responseCode = "404", description = "NOTICE_NOT_FOUND — 공고가 없거나 공개되지 않았어요")
  SseEmitter stream(
      @Parameter(description = "공고 ID") UUID noticeId,
      @Parameter(
              description =
                  "재연결이면 브라우저가 보내는 마지막 메시지 ID(message.created의 id). 첫 연결이면 비워요. UUID가 아니면 무시해요")
          String lastEventId);
}
