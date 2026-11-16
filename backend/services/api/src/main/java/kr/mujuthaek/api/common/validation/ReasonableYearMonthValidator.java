package kr.mujuthaek.api.common.validation;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import java.time.YearMonth;

/** {@link ReasonableDate}: YearMonth */
public class ReasonableYearMonthValidator
    implements ConstraintValidator<ReasonableDate, YearMonth> {

  @Override
  public boolean isValid(YearMonth value, ConstraintValidatorContext context) {
    return value == null
        || (!value.isBefore(YearMonth.from(ReasonableDateValidator.MIN))
            && !value.isAfter(YearMonth.from(ReasonableDateValidator.MAX)));
  }
}
