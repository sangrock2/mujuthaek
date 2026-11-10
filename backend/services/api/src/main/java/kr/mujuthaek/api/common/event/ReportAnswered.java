package kr.mujuthaek.api.common.event;

import java.util.UUID;

/**
 * 관리자가 회원의 제보를 처리하고 답을 남김 (공고·혜택·창업 사업·생활권 제보 공통). 알림 쪽은 이 타입 하나로 네 이벤트를 모두 받을 수 있어요
 * ({@code @TransactionalEventListener} 인자를 ReportAnswered로). 대상별로 다른 값(공고 ID 등)은 각 이벤트에서 꺼내요.
 *
 * <p>답이 있을 때만, 제보한 회원마다 한 번 나가요. 이미 처리한 제보는 다시 처리할 수 없어서(409) 같은 제보로 두 번 나가지 않아요.
 */
public sealed interface ReportAnswered
    permits NoticeReportAnswered,
        BenefitReportAnswered,
        ProgramReportAnswered,
        AreaReportAnswered,
        GeneralReportAnswered {

  /** 제보 ID (UUID v7). 생활권 제보는 다른 표라 공고·혜택·사업 제보와 ID가 겹칠 수 있으니 종류와 함께 써요 */
  UUID reportId();

  /** 제보한 회원 (받는 사람) */
  UUID reporterId();

  /** 제보한 칸 이름 (보증금, 역까지 거리 …) */
  String field();

  /** FIXED 고침 · KEPT 원문대로 그대로 둠 */
  String result();

  /** 관리자 답변 원문. 회원 개인정보가 들어갈 수 있어 로그·푸시에 싣지 않아요 */
  String reply();

  /** 대상 제목 (공고·혜택 정책·창업 사업 제목). 모르면 null (생활권 제보는 항상 null) */
  String targetTitle();
}
