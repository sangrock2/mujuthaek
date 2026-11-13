package kr.mujuthaek.api.user.controller.spec;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.UUID;
import kr.mujuthaek.api.common.dto.response.CursorPageResponse;
import kr.mujuthaek.api.user.controller.PreparationController.AcknowledgementRequest;
import kr.mujuthaek.api.user.controller.PreparationController.AddTaskRequest;
import kr.mujuthaek.api.user.controller.PreparationController.DocumentRequest;
import kr.mujuthaek.api.user.controller.PreparationController.StatusRequest;
import kr.mujuthaek.api.user.controller.PreparationController.UpdateTaskRequest;
import kr.mujuthaek.api.user.service.LoginUser;
import kr.mujuthaek.api.user.service.PreparationService.Response;
import org.springframework.http.ResponseEntity;

@Tag(name = "신청 준비함", description = "공고별 서류·일정과 사용자 준비 상태")
public interface PreparationApiSpec {
  @Operation(summary = "신청 준비함 목록", description = "현재 공고와 동기화하고 상태별 커서 목록을 반환합니다.")
  @ApiResponse(
      responseCode = "400",
      description = "INVALID_CURSOR — 잘못된 커서예요. 크기·상태 오류는 VALIDATION_FAILED예요")
  CursorPageResponse<Response> list(
      @Parameter(hidden = true) LoginUser user, String status, String cursor, Integer size);

  @Operation(
      summary = "공고의 신청 준비 시작",
      description = "새 준비함과 관심 공고를 함께 저장합니다. 기존 준비함이면 관심을 다시 등록하지 않습니다.")
  @ApiResponse(responseCode = "201", description = "준비함을 생성했어요")
  @ApiResponse(responseCode = "200", description = "기존 준비함이에요")
  @ApiResponse(responseCode = "404", description = "NOTICE_NOT_FOUND — 공개 공고가 없어요")
  @ApiResponse(
      responseCode = "409",
      description = "PREPARATION_LIMIT_EXCEEDED — 준비함 200개 한도예요. 관심 한도는 FAVORITE_LIMIT_EXCEEDED예요")
  ResponseEntity<Response> create(@Parameter(hidden = true) LoginUser user, UUID noticeId);

  @Operation(summary = "신청 준비 기록 상세")
  @ApiResponse(responseCode = "404", description = "PREPARATION_NOT_FOUND — 본인 준비 기록이 없어요")
  Response get(@Parameter(hidden = true) LoginUser user, UUID id);

  @Operation(
      summary = "준비 상태 변경",
      description = "보관 전 상태 복원은 restore=true입니다. expectedRevision을 확인합니다.")
  @ApiResponse(responseCode = "409", description = "PREPARATION_CONFLICT — 최신 기록을 다시 확인하세요")
  Response change(@Parameter(hidden = true) LoginUser user, UUID id, StatusRequest request);

  @Operation(
      summary = "서류 준비 상태 변경",
      description = "sourceRevision과 expectedRevision이 최신일 때만 저장합니다.")
  @ApiResponse(responseCode = "409", description = "PREPARATION_CONFLICT — 공고·서류·준비 기록이 바뀌었어요")
  Response document(
      @Parameter(hidden = true) LoginUser user,
      UUID id,
      String documentId,
      DocumentRequest request);

  @Operation(summary = "변경된 공고 확인", description = "서류를 준비 완료로 바꾸지 않고 공고 변경 확인만 기록합니다.")
  @ApiResponse(responseCode = "409", description = "PREPARATION_CONFLICT — 확인 중 공고나 기록이 바뀌었어요")
  Response acknowledge(
      @Parameter(hidden = true) LoginUser user, UUID id, AcknowledgementRequest request);

  @Operation(
      summary = "신청 준비 기록 삭제",
      description = "본인 기록만 삭제하며 관심 공고와 알림 설정은 유지합니다. 기록이 없어도 204입니다.")
  @ApiResponse(responseCode = "204", description = "삭제했어요")
  ResponseEntity<Void> delete(@Parameter(hidden = true) LoginUser user, UUID id);

  @Operation(
      summary = "신청 준비 할 일 추가",
      description = "직접 정한 할 일과 선택 기한을 저장합니다. 공고의 공식 제출 서류와 구분합니다.")
  @ApiResponse(
      responseCode = "409",
      description = "PREPARATION_TASK_LIMIT_EXCEEDED — 할 일 30개 한도예요. 동시 수정은 PREPARATION_CONFLICT예요")
  Response addTask(@Parameter(hidden = true) LoginUser user, UUID id, AddTaskRequest request);

  @Operation(
      summary = "신청 준비 할 일 수정·완료",
      description = "제목·기한·완료 상태를 바꾸고 expectedRevision으로 동시 수정을 확인합니다.")
  @ApiResponse(responseCode = "404", description = "PREPARATION_TASK_NOT_FOUND — 본인 준비함의 할 일이 없어요")
  @ApiResponse(responseCode = "409", description = "PREPARATION_CONFLICT — 최신 준비 기록을 다시 확인하세요")
  Response updateTask(
      @Parameter(hidden = true) LoginUser user, UUID id, UUID taskId, UpdateTaskRequest request);

  @Operation(summary = "신청 준비 할 일 삭제", description = "선택한 할 일만 삭제합니다. 공식 제출 서류와 준비함은 유지합니다.")
  @ApiResponse(responseCode = "404", description = "PREPARATION_TASK_NOT_FOUND — 본인 준비함의 할 일이 없어요")
  @ApiResponse(responseCode = "409", description = "PREPARATION_CONFLICT — 최신 준비 기록을 다시 확인하세요")
  Response deleteTask(
      @Parameter(hidden = true) LoginUser user, UUID id, UUID taskId, long expectedRevision);
}
