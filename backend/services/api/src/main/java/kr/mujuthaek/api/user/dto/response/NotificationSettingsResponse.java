package kr.mujuthaek.api.user.dto.response;

/** 알림 종류별 켬·끔과 조용한 시간. 끈 종류도 알림함에는 남아요 (푸시·이메일로 보내지 않을 뿐). */
public record NotificationSettingsResponse(
    boolean newNotice,
    boolean newSupport,
    boolean deadline,
    boolean correction,
    boolean followUp,
    boolean quietEnabled) {}
