package kr.mujuthaek.notification.delivery.push;

import java.io.IOException;

/** 기기 한 대에 푸시를 보내요. 상태 코드를 그대로 돌려주고, 어떻게 처리할지는 {@link PushChannel}이 정해요. */
public interface PushSender {

  /**
   * @throws IOException 연결 실패·시간 초과 (다시 보내요)
   */
  PushResponse send(PushMessage message) throws IOException;
}
