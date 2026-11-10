package kr.mujuthaek.api.benefit.controller;

import kr.mujuthaek.api.benefit.service.internal.BenefitDetailService;

/** 테스트에서 패키지 안 컨트롤러를 만들어요. */
public final class BenefitControllerAccess {

  private BenefitControllerAccess() {}

  public static Object controller(BenefitDetailService details) {
    return new BenefitController(details);
  }
}
