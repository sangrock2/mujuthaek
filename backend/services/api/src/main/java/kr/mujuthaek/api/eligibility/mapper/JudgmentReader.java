package kr.mujuthaek.api.eligibility.mapper;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import kr.mujuthaek.api.eligibility.rule.Judgment;
import kr.mujuthaek.api.eligibility.rule.Judgment.Basics;
import kr.mujuthaek.api.eligibility.rule.Judgment.Criterion;
import kr.mujuthaek.api.eligibility.rule.Judgment.Factor;
import tools.jackson.databind.JsonNode;

/**
 * extraction.completed의 judgment(contracts/schemas/housing-judgment.v1.json)를 판정 엔진 모델로 바꿔요.
 *
 * <p>소득 구간 대상군은 대상 대상군의 「구간 중 하나」 조건으로 접어요({@link IncomeTiers}).
 *
 * <p>모르는 조건 종류가 오면(계약이 늘었는데 판정이 아직 모를 때) 그 조건은 "직접 확인" 질문(ASK)으로 바꿔서, 판정이 조용히 지원 가능으로 나오지 않게 해요.
 */
public final class JudgmentReader {

  private JudgmentReader() {}

  public static Judgment read(JsonNode j) {
    List<Judgment.Group> groups = new ArrayList<>();
    for (JsonNode g : j.path("groups")) {
      groups.add(new Judgment.Group(text(g, "id"), text(g, "name"), criteria(g.path("criteria"))));
    }
    return new Judgment(
        LocalDate.parse(text(j, "referenceDate")),
        criteria(j.path("common")),
        IncomeTiers.fold(groups));
  }

  static List<Criterion> criteria(JsonNode array) {
    List<Criterion> out = new ArrayList<>();
    for (JsonNode c : array) {
      out.add(criterion(c));
    }
    return out;
  }

  static Criterion criterion(JsonNode c) {
    Basics b =
        new Basics(
            text(c, "id"),
            text(c, "quote"),
            integer(c, "page"),
            c.path("inReview").asBoolean(false),
            text(c, "reviewReason"));
    String kind = text(c, "kind");
    return switch (kind == null ? "" : kind) {
      case "AGE" -> new Judgment.Age(b, integer(c, "minAge"), integer(c, "maxAge"));
      case "RESIDENCE" ->
          new Judgment.Residence(b, strings(c.path("regionCodes")), integer(c, "minMonths"));
      case "HOMELESS" -> new Judgment.Homeless(b, text(c, "scope"), integer(c, "minYears"));
      case "INCOME" ->
          new Judgment.Income(
              b,
              text(c, "basis"),
              text(c, "standard"),
              integer(c, "year"),
              decimal(c, "percent"),
              bonuses(c.path("bonuses")),
              text(c, "bonusCombine"),
              printed(c.path("printedTable")));
      case "ASSET" ->
          new Judgment.Asset(
              b, text(c, "basis"), c.path("maxWon").asLong(), overrides(c.path("overrides")));
      case "CAR" -> new Judgment.Car(b, c.path("maxWon").asLong(), overrides(c.path("overrides")));
      case "MARRIAGE" ->
          new Judgment.Marriage(
              b,
              text(c, "require"),
              integer(c, "maxYears"),
              c.path("allowEngaged").asBoolean(false));
      case "CHILDREN" ->
          new Judgment.Children(
              b,
              integer(c, "minCount"),
              integer(c, "youngestMaxAge"),
              c.path("includeUnborn").asBoolean(false));
      case "SAVINGS" ->
          new Judgment.Savings(
              b,
              integer(c, "minMonths"),
              integer(c, "minPayments"),
              c.path("minBalanceWon").isNumber() ? c.path("minBalanceWon").asLong() : null,
              decimal(c, "depositAreaM2"));
      case "STATUS" -> new Judgment.WelfareStatus(b, strings(c.path("anyOf")));
      case "ANY_OF" -> {
        List<Judgment.Option> options = new ArrayList<>();
        for (JsonNode o : c.path("options")) {
          options.add(new Judgment.Option(text(o, "label"), criteria(o.path("criteria"))));
        }
        yield new Judgment.AnyOf(b, options);
      }
      case "ASK" -> new Judgment.Ask(b, text(c, "question"), text(c, "metWhen"));
      default ->
          new Judgment.Ask(b, b.quote() == null ? "공고의 이 조건에 해당하는지 확인해 주세요" : b.quote(), "YES");
    };
  }

  private static List<Judgment.Bonus> bonuses(JsonNode array) {
    List<Judgment.Bonus> out = new ArrayList<>();
    for (JsonNode x : array) {
      out.add(new Judgment.Bonus(factor(x.path("when")), x.path("addPercent").asDouble()));
    }
    return out;
  }

  private static List<Judgment.Override> overrides(JsonNode array) {
    List<Judgment.Override> out = new ArrayList<>();
    for (JsonNode x : array) {
      out.add(new Judgment.Override(factor(x.path("when")), x.path("maxWon").asLong()));
    }
    return out;
  }

  private static List<Judgment.PrintedRow> printed(JsonNode array) {
    List<Judgment.PrintedRow> out = new ArrayList<>();
    for (JsonNode x : array) {
      out.add(new Judgment.PrintedRow(x.path("householdSize").asInt(), x.path("maxWon").asLong()));
    }
    return out;
  }

  private static Factor factor(JsonNode f) {
    return new Factor(text(f, "factor"), integer(f, "min"), integer(f, "max"));
  }

  private static String text(JsonNode n, String name) {
    JsonNode v = n.path(name);
    return v.isMissingNode() || v.isNull() ? null : v.asString();
  }

  private static Integer integer(JsonNode n, String name) {
    JsonNode v = n.path(name);
    return v.isNumber() ? v.asInt() : null;
  }

  private static Double decimal(JsonNode n, String name) {
    JsonNode v = n.path(name);
    return v.isNumber() ? v.asDouble() : null;
  }

  private static List<String> strings(JsonNode array) {
    List<String> out = new ArrayList<>();
    for (JsonNode v : array) {
      out.add(v.asString());
    }
    return out;
  }
}
