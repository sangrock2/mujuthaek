package kr.mujuthaek.api.common.validation;

import static java.lang.annotation.ElementType.FIELD;
import static java.lang.annotation.ElementType.PARAMETER;
import static java.lang.annotation.ElementType.RECORD_COMPONENT;
import static java.lang.annotation.ElementType.TYPE_USE;
import static java.lang.annotation.RetentionPolicy.RUNTIME;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.Documented;
import java.lang.annotation.Retention;
import java.lang.annotation.Target;

/**
 * 날짜·연월이 1900년 1월 1일부터 2200년 12월 31일 사이여야 해요. 비어 있으면(null) 통과해요.
 *
 * <p>판정 규칙은 받은 날짜에 몇 년을 더하고 빼며 계산해요. 범위 검사가 없으면 {@code +999999999-12-31} 같은 날짜가 계산 중 예외를 내서 400이 아닌
 * 500과 운영 경보가 났어요(2026-11-16 보안 감사 L-12). 실제 사람·사업의 날짜는 이 범위를 넘지 않아요.
 */
@Documented
@Constraint(validatedBy = {ReasonableDateValidator.class, ReasonableYearMonthValidator.class})
@Target({FIELD, PARAMETER, RECORD_COMPONENT, TYPE_USE})
@Retention(RUNTIME)
public @interface ReasonableDate {

  String message() default "1900-01-01부터 2200-12-31 사이 날짜여야 해요";

  Class<?>[] groups() default {};

  Class<? extends Payload>[] payload() default {};
}
