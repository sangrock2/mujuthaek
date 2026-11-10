/**
 * 트래픽: 관리자 「트래픽」 화면. 방문·유입·기기·이용 흐름은 Google Analytics 4(Data API)에서 가져오고, GA가 볼 수 없는 봇·도구·요청 많은
 * IP·로그인 실패·관리자 접근은 api 서버 요청 기록으로 셉니다. 회원 한 명 단위 활동은 기록하지 않아요(회원 ID를 저장하지 않음). 원본 IP는 보안 대응용으로 짧게만
 * 보관해요.
 */
@org.springframework.modulith.ApplicationModule(displayName = "트래픽")
package kr.mujuthaek.api.traffic;
