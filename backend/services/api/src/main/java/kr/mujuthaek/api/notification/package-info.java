/**
 * 웹 푸시 알림 모듈.
 *
 * <p>다른 모듈은 이 모듈의 service 패키지(조회 메서드)만 불러요. controller, repository, domain 같은 나머지 하위 패키지는 이 모듈 안에서만
 * 써요. 다른 모듈에 영향을 주는 변경은 common/event의 이벤트로 알려요.
 */
@org.springframework.modulith.ApplicationModule(displayName = "웹 푸시 알림")
package kr.mujuthaek.api.notification;
