/**
 * 공고 채팅 모듈. 공고마다 채팅방 하나(방 ID = 공고 ID)에서 질문·경험을 나눠요. 쓰기는 REST, 실시간 받기는 SSE예요.
 *
 * <p>다른 모듈은 이 모듈의 service 패키지(조회 메서드)만 불러요. controller, repository, domain 같은 나머지 하위 패키지는 이 모듈 안에서만
 * 써요. 이 모듈은 notice(공고 확인)와 user(로그인 회원)만 불러요.
 */
@org.springframework.modulith.ApplicationModule(displayName = "공고 채팅")
package kr.mujuthaek.api.chat;
