package kr.mujuthaek.api.common.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

/** 모듈 사이 이벤트를 커밋 뒤 비동기로 처리하기 위한 설정. */
@Configuration
@EnableAsync
class AsyncConfig {}
