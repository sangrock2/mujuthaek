package kr.mujuthaek.api.common.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

/** 정해진 시각에 도는 작업(@Scheduled)을 켜요. 예: 만료된 로그인 토큰 정리. */
@Configuration
@EnableScheduling
class SchedulingConfig {}
