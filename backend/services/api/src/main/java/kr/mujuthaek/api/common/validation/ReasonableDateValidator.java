package kr.mujuthaek.api.common.validation;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import java.time.LocalDate;

/** {@link ReasonableDate}: LocalDate */
public class ReasonableDateValidator implements ConstraintValidator<ReasonableDate, LocalDate> {

  static final LocalDate MIN = LocalDate.of(1900, 1, 1);
  static final LocalDate MAX = LocalDate.of(2200, 12, 31);

  @Override
  public boolean isValid(LocalDate value, ConstraintValidatorContext context) {
    return value == null || (!value.isBefore(MIN) && !value.isAfter(MAX));
  }
}
