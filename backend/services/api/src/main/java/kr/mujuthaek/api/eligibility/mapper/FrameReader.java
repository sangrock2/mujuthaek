package kr.mujuthaek.api.eligibility.mapper;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import kr.mujuthaek.api.common.exception.CustomException;
import kr.mujuthaek.api.common.exception.ErrorCode;
import kr.mujuthaek.api.eligibility.rule.frame.Answer;
import kr.mujuthaek.api.eligibility.rule.frame.Applicant;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.Factor;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.FactorKind;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.Meta;
import kr.mujuthaek.api.eligibility.rule.frame.Criterion.RegistrationRequirement;
import kr.mujuthaek.api.eligibility.rule.frame.Frame;
import tools.jackson.databind.JsonNode;

/**
 * 판정 틀 JSON → 판정 모델. 판정에 쓰는 칸이 없거나 틀리면 어느 칸이 왜 틀렸는지 400으로 알려줘요.
 *
 * <p>틀은 공고 데이터라서 오류 메시지에 틀의 값(종류, 코드)을 넣어도 돼요. 판정에 쓰지 않는 모르는 칸은 무시해요.
 *
 * <p>quote·page·reviewReason은 없어도 되고, common·preferences·notes가 없으면 빈 목록으로 봐요. inReview가 없으면
 * false예요.
 */
public final class FrameReader {

  private final FrameSpec spec;
  private final Set<String> ids = new HashSet<>();

  private FrameReader(FrameSpec spec) {
    this.spec = spec;
  }

  public static Frame read(JsonNode root, FrameSpec spec) {
    return new FrameReader(spec).frame(root);
  }

  private Frame frame(JsonNode root) {
    String at = "frame";
    requireObject(root, at);
    String schema = string(root, "schema", at);
    if (!spec.schema().equals(schema)) {
      throw new CustomException(
          ErrorCode.ELIGIBILITY_FIELD_MISMATCH,
          "이 판정은 " + spec.schema() + " 틀만 받아요 (받은 틀: " + schema + ")");
    }
    String sourceId = string(root, spec.sourceIdField(), at);
    int version = requiredInt(root, "rawVersion", at, 1);
    LocalDate referenceDate =
        spec.referenceDateOptional()
            ? optionalDate(root, "referenceDate", at)
            : requiredDate(root, "referenceDate", at);
    List<Criterion> common = criteria(optionalArray(root, "common", at), at + ".common", false);

    List<JsonNode> groupNodes = requiredArray(root, "groups", at);
    if (groupNodes.isEmpty()) {
      throw invalid(at + ".groups", "대상군이 하나 이상 있어야 해요");
    }
    List<Frame.Group> groups = new ArrayList<>();
    Set<String> groupIds = new HashSet<>();
    for (int i = 0; i < groupNodes.size(); i++) {
      String g = at + ".groups[" + i + "]";
      JsonNode node = groupNodes.get(i);
      requireObject(node, g);
      String id = newId(string(node, "id", g), g);
      groupIds.add(id);
      Integer rank = optionalInt(node, "rank", g, 1);
      if (rank != null && !spec.ranks()) {
        throw invalid(g + ".rank", spec.schema() + " 틀에는 신청 순위(rank)가 없어요");
      }
      groups.add(
          new Frame.Group(
              id,
              string(node, "name", g),
              rank,
              criteria(requiredArray(node, "criteria", g), g + ".criteria", false)));
    }

    List<JsonNode> preferenceNodes = optionalArray(root, "preferences", at);
    if (!spec.preferences() && !preferenceNodes.isEmpty()) {
      throw invalid(at + ".preferences", spec.schema() + " 틀에는 우대(preferences)가 없어요");
    }
    List<Frame.Preference> preferences = new ArrayList<>();
    for (int i = 0; i < preferenceNodes.size(); i++) {
      preferences.add(preference(preferenceNodes.get(i), at + ".preferences[" + i + "]", groupIds));
    }

    List<Frame.Note> notes = new ArrayList<>();
    List<JsonNode> noteNodes = optionalArray(root, "notes", at);
    for (int i = 0; i < noteNodes.size(); i++) {
      notes.add(note(noteNodes.get(i), at + ".notes[" + i + "]", groupIds));
    }
    return new Frame(
        spec.field(), sourceId, version, referenceDate, common, groups, preferences, notes);
  }

  private Frame.Preference preference(JsonNode node, String at, Set<String> groupIds) {
    requireObject(node, at);
    String id = newId(string(node, "id", at), at);
    String groupId = optionalGroupId(node, at, groupIds);
    Frame.Preference.Effect effect =
        requiredEnum(node, "effect", at, Frame.Preference.Effect.class);
    BigDecimal points = optionalPositiveDecimal(node, "points", at);
    if (points != null && effect != Frame.Preference.Effect.BONUS_POINTS) {
      throw invalid(at + ".points", "점수는 가점(BONUS_POINTS)일 때만 넣어요");
    }
    return new Frame.Preference(
        id,
        string(node, "label", at),
        groupId,
        effect,
        points,
        criteria(requiredArray(node, "criteria", at), at + ".criteria", true),
        optionalString(node, "quote", at),
        optionalInt(node, "page", at, 1));
  }

  private Frame.Note note(JsonNode node, String at, Set<String> groupIds) {
    requireObject(node, at);
    return new Frame.Note(
        requiredEnum(node, "kind", at, Frame.Note.Kind.class),
        optionalGroupId(node, at, groupIds),
        string(node, "text", at),
        optionalString(node, "quote", at),
        optionalInt(node, "page", at, 1));
  }

  private String optionalGroupId(JsonNode node, String at, Set<String> groupIds) {
    String groupId = optionalString(node, "groupId", at);
    if (groupId != null && !groupIds.contains(groupId)) {
      throw invalid(at + ".groupId", "없는 대상군이에요: " + groupId);
    }
    return groupId;
  }

  // ── 조건 ──────────────────────────────────────────────

  private List<Criterion> criteria(List<JsonNode> nodes, String at, boolean nonEmpty) {
    if (nonEmpty && nodes.isEmpty()) {
      throw invalid(at, "조건이 하나 이상 있어야 해요");
    }
    List<Criterion> criteria = new ArrayList<>();
    for (int i = 0; i < nodes.size(); i++) {
      criteria.add(criterion(nodes.get(i), at + "[" + i + "]"));
    }
    return criteria;
  }

  private Criterion criterion(JsonNode node, String at) {
    requireObject(node, at);
    String kind = string(node, "kind", at);
    if (!spec.kinds().contains(kind)) {
      throw invalid(
          at + ".kind",
          spec.schema() + " 틀에서 쓸 수 없는 종류예요: " + kind + " (쓸 수 있는 종류: " + spec.kinds() + ")");
    }
    Meta meta = meta(node, at);
    return switch (kind) {
      case "AGE" -> {
        Integer min = optionalInt(node, "minAge", at, 0);
        Integer max = optionalInt(node, "maxAge", at, 0);
        notBothNull(min, max, at, "minAge", "maxAge");
        ordered(min, max, at, "minAge", "maxAge");
        yield new Criterion.Age(meta, min, max);
      }
      case "NATIONALITY" ->
          new Criterion.Nationality(meta, strings(node, "countryCodes", at, "[A-Z]{2}", true));
      case "RESIDENCE" ->
          new Criterion.Residence(
              meta,
              strings(node, "regionCodes", at, "\\d{10}", true),
              optionalInt(node, "minMonths", at, 0));
      case "REGION" ->
          new Criterion.Region(
              meta,
              requiredEnum(node, "basis", at, Criterion.RegionBasis.class),
              strings(node, "regionCodes", at, "\\d{10}", true));
      case "MARRIAGE" ->
          new Criterion.Marriage(
              meta,
              requiredEnum(node, "require", at, Criterion.MarriageRequirement.class),
              optionalInt(node, "maxYears", at, 0),
              optionalBoolean(node, "allowEngaged", at));
      case "CHILDREN" -> {
        Integer minCount = optionalInt(node, "minCount", at, 0);
        Integer youngest = optionalInt(node, "youngestMaxAge", at, 0);
        notBothNull(minCount, youngest, at, "minCount", "youngestMaxAge");
        yield new Criterion.Children(
            meta, minCount, youngest, optionalBoolean(node, "includeUnborn", at));
      }
      case "STATUS" ->
          new Criterion.Status(meta, codes(node, "anyOf", at, spec.statusCodes(), "유형"));
      case "EXCLUDED_STATUS" ->
          new Criterion.ExcludedStatus(
              meta, codes(node, "anyOf", at, spec.restrictionCodes(), "신청 제한 사유"));
      case "HOMELESS" ->
          new Criterion.Homeless(
              meta,
              requiredEnum(node, "scope", at, Criterion.HomelessScope.class),
              optionalInt(node, "minYears", at, 0));
      case "INCOME" -> income(node, at, meta);
      case "ASSET" ->
          new Criterion.Asset(
              meta,
              requiredEnum(node, "basis", at, Criterion.AssetBasis.class),
              requiredLong(node, "maxWon", at, 0),
              raisedLimits(node, at));
      case "CAR" ->
          new Criterion.Car(meta, requiredLong(node, "maxWon", at, 0), raisedLimits(node, at));
      case "SAVINGS" -> {
        Long minBalance = optionalLong(node, "minBalanceWon", at, 0);
        BigDecimal depositArea = optionalPositiveDecimal(node, "depositAreaM2", at);
        if (minBalance != null && depositArea != null) {
          throw invalid(at + ".depositAreaM2", "minBalanceWon과 같이 쓸 수 없어요 (둘 중 하나만)");
        }
        yield new Criterion.Savings(
            meta,
            optionalInt(node, "minMonths", at, 0),
            optionalInt(node, "minPayments", at, 0),
            minBalance,
            depositArea);
      }
      case "APPLICANT_TYPE" ->
          new Criterion.ApplicantKind(
              meta, requiredEnum(node, "only", at, Applicant.ApplicantType.class));
      case "BUSINESS_REGISTRATION" -> {
        RegistrationRequirement require =
            requiredEnum(node, "require", at, RegistrationRequirement.class);
        if (!spec.registrationRequires().contains(require)) {
          throw invalid(
              at + ".require",
              spec.schema() + " 틀에서 쓸 수 없는 값이에요: " + require + " " + spec.registrationRequires());
        }
        Integer within = optionalInt(node, "closedWithinYears", at, 1);
        if (within != null && require != RegistrationRequirement.CLOSED) {
          throw invalid(at + ".closedWithinYears", "폐업 기간은 CLOSED일 때만 넣어요");
        }
        yield new Criterion.BusinessRegistration(meta, require, within);
      }
      case "BUSINESS_CAREER" ->
          new Criterion.BusinessCareer(
              meta, requiredInt(node, "minMonths", at, 1), optionalInt(node, "withinYears", at, 1));
      case "BUSINESS_AGE" -> {
        LocalDate from = optionalDate(node, "openedFrom", at);
        LocalDate to = optionalDate(node, "openedTo", at);
        notBothNull(from, to, at, "openedFrom", "openedTo");
        datesOrdered(from, to, at, "openedFrom", "openedTo");
        yield new Criterion.BusinessAge(meta, from, to);
      }
      case "CLOSURE" -> {
        LocalDate from = optionalDate(node, "closedFrom", at);
        LocalDate to = optionalDate(node, "closedTo", at);
        datesOrdered(from, to, at, "closedFrom", "closedTo");
        yield new Criterion.Closure(
            meta, requiredEnum(node, "mode", at, Criterion.ClosureMode.class), from, to);
      }
      case "REVENUE" -> {
        Long min = optionalLong(node, "minWon", at, 0);
        Long max = optionalLong(node, "maxWon", at, 0);
        notBothNull(min, max, at, "minWon", "maxWon");
        ordered(min, max, at, "minWon", "maxWon");
        yield new Criterion.Revenue(meta, requiredInt(node, "year", at, 2000), min, max);
      }
      case "INDUSTRY" -> {
        int revision = requiredInt(node, "revision", at, 10);
        if (revision != 10 && revision != 11) {
          throw invalid(at + ".revision", "한국표준산업분류 차수는 10 또는 11이에요");
        }
        yield new Criterion.Industry(
            meta,
            requiredEnum(node, "mode", at, Criterion.IndustryMode.class),
            revision,
            strings(node, "codes", at, "\\d{2,5}", true),
            strings(node, "maybeCodes", at, "\\d{2,5}", false));
      }
      case "ANY_OF" -> {
        List<JsonNode> options = requiredArray(node, "options", at);
        if (options.size() < 2) {
          throw invalid(at + ".options", "길이 둘 이상 있어야 해요");
        }
        List<Criterion.Option> parsed = new ArrayList<>();
        for (int i = 0; i < options.size(); i++) {
          String o = at + ".options[" + i + "]";
          requireObject(options.get(i), o);
          parsed.add(
              new Criterion.Option(
                  string(options.get(i), "label", o),
                  criteria(requiredArray(options.get(i), "criteria", o), o + ".criteria", true)));
        }
        yield new Criterion.AnyOf(meta, parsed);
      }
      case "ASK" -> {
        String question = string(node, "question", at);
        Answer metWhen = requiredEnum(node, "metWhen", at, Answer.class);
        yield BusinessAgeQuestion.read(meta, question, metWhen)
            .<Criterion>map(c -> c)
            .orElseGet(() -> new Criterion.Ask(meta, question, metWhen));
      }
      default -> throw new IllegalStateException("종류 목록과 읽는 코드가 맞지 않아요: " + kind);
    };
  }

  private Meta meta(JsonNode node, String at) {
    String id = newId(string(node, "id", at), at);
    LocalDate asOf = optionalDate(node, "asOf", at);
    if (asOf != null && !spec.asOf()) {
      throw invalid(at + ".asOf", spec.schema() + " 틀에는 조건별 기준일(asOf)이 없어요");
    }
    return new Meta(
        id,
        optionalString(node, "quote", at),
        optionalInt(node, "page", at, 1),
        optionalBoolean(node, "inReview", at),
        optionalString(node, "reviewReason", at),
        asOf);
  }

  private Criterion.Income income(JsonNode node, String at, Meta meta) {
    Criterion.IncomeStandard standard =
        optionalEnum(node, "standard", at, Criterion.IncomeStandard.class);
    Integer year = optionalInt(node, "year", at, 2000);
    BigDecimal percent = optionalPositiveDecimal(node, "percent", at);
    List<Criterion.PrintedRow> printed = new ArrayList<>();
    List<JsonNode> rows = optionalArray(node, "printedTable", at);
    for (int i = 0; i < rows.size(); i++) {
      String r = at + ".printedTable[" + i + "]";
      requireObject(rows.get(i), r);
      printed.add(
          new Criterion.PrintedRow(
              requiredInt(rows.get(i), "householdSize", r, 1),
              requiredLong(rows.get(i), "maxWon", r, 0)));
    }
    if (standard == null) {
      if (year != null || percent != null) {
        throw invalid(at, "standard가 null이면 year와 percent도 null이에요");
      }
      if (printed.isEmpty()) {
        throw invalid(at + ".printedTable", "standard가 null이면 공고 금액표가 있어야 해요");
      }
    } else if (year == null || percent == null) {
      throw invalid(at, "standard가 있으면 year와 percent가 있어야 해요");
    }
    List<Criterion.Bonus> bonuses = new ArrayList<>();
    List<JsonNode> bonusNodes = optionalArray(node, "bonuses", at);
    for (int i = 0; i < bonusNodes.size(); i++) {
      String b = at + ".bonuses[" + i + "]";
      requireObject(bonusNodes.get(i), b);
      BigDecimal add = optionalPositiveDecimal(bonusNodes.get(i), "addPercent", b);
      if (add == null) {
        throw invalid(b + ".addPercent", "값이 있어야 해요");
      }
      bonuses.add(new Criterion.Bonus(factor(bonusNodes.get(i), b), add));
    }
    Criterion.BonusCombine combine =
        optionalEnum(node, "bonusCombine", at, Criterion.BonusCombine.class);
    return new Criterion.Income(
        meta,
        requiredEnum(node, "basis", at, Criterion.IncomeBasis.class),
        standard,
        year,
        percent,
        bonuses,
        combine == null ? Criterion.BonusCombine.SUM : combine,
        printed);
  }

  private List<Criterion.RaisedLimit> raisedLimits(JsonNode node, String at) {
    List<Criterion.RaisedLimit> limits = new ArrayList<>();
    List<JsonNode> nodes = optionalArray(node, "overrides", at);
    for (int i = 0; i < nodes.size(); i++) {
      String o = at + ".overrides[" + i + "]";
      requireObject(nodes.get(i), o);
      limits.add(
          new Criterion.RaisedLimit(
              factor(nodes.get(i), o), requiredLong(nodes.get(i), "maxWon", o, 0)));
    }
    return limits;
  }

  private Factor factor(JsonNode parent, String at) {
    String w = at + ".when";
    JsonNode node = parent.get("when");
    requireObject(node, w);
    FactorKind kind = requiredEnum(node, "factor", w, FactorKind.class);
    Integer min = optionalInt(node, "min", w, 0);
    Integer max = optionalInt(node, "max", w, 0);
    ordered(min, max, w, "min", "max");
    LocalDate since = optionalDate(node, "since", w);
    Criterion.CountRule rule = optionalEnum(node, "countRule", w, Criterion.CountRule.class);
    if (kind == FactorKind.NEWBORN_CHILDREN && (since == null || rule == null)) {
      throw invalid(w, "출생 자녀(NEWBORN_CHILDREN)는 since와 countRule이 있어야 해요");
    }
    if (kind != FactorKind.NEWBORN_CHILDREN && (since != null || rule != null)) {
      throw invalid(w, "since와 countRule은 출생 자녀(NEWBORN_CHILDREN)일 때만 넣어요");
    }
    if (kind == FactorKind.DUAL_INCOME && (min != null || max != null)) {
      throw invalid(w, "맞벌이(DUAL_INCOME)는 min·max를 넣지 않아요");
    }
    return new Factor(kind, min, max, since, rule);
  }

  // ── 값 읽기 ────────────────────────────────────────────

  private String newId(String id, String at) {
    if (!ids.add(id)) {
      throw invalid(at + ".id", "ID가 겹쳐요: " + id);
    }
    return id;
  }

  private List<String> codes(
      JsonNode node, String name, String at, Set<String> allowed, String what) {
    List<String> codes = strings(node, name, at, "[A-Z_]+", true);
    for (String code : codes) {
      if (!allowed.contains(code)) {
        throw invalid(
            at + "." + name,
            spec.schema() + " 틀에서 쓸 수 없는 " + what + " 코드예요: " + code + " " + allowed);
      }
    }
    return codes;
  }

  private static List<String> strings(
      JsonNode node, String name, String at, String pattern, boolean nonEmpty) {
    List<JsonNode> values =
        nonEmpty ? requiredArray(node, name, at) : optionalArray(node, name, at);
    if (nonEmpty && values.isEmpty()) {
      throw invalid(at + "." + name, "하나 이상 있어야 해요");
    }
    List<String> result = new ArrayList<>();
    for (int i = 0; i < values.size(); i++) {
      JsonNode value = values.get(i);
      if (!value.isString() || !value.stringValue().matches(pattern)) {
        throw invalid(at + "." + name + "[" + i + "]", "형식이 맞지 않아요 (" + pattern + ")");
      }
      if (result.contains(value.stringValue())) {
        throw invalid(at + "." + name + "[" + i + "]", "같은 값이 두 번 있어요");
      }
      result.add(value.stringValue());
    }
    return result;
  }

  private static void requireObject(JsonNode node, String at) {
    if (node == null || !node.isObject()) {
      throw invalid(at, "객체({...})여야 해요");
    }
  }

  private static boolean absent(JsonNode node) {
    return node == null || node.isNull() || node.isMissingNode();
  }

  private static String string(JsonNode node, String name, String at) {
    String value = optionalString(node, name, at);
    if (value == null || value.isBlank()) {
      throw invalid(at + "." + name, "값이 있어야 해요");
    }
    return value;
  }

  private static String optionalString(JsonNode node, String name, String at) {
    JsonNode value = node.get(name);
    if (absent(value)) {
      return null;
    }
    if (!value.isString()) {
      throw invalid(at + "." + name, "문자열이어야 해요");
    }
    return value.stringValue();
  }

  private static int requiredInt(JsonNode node, String name, String at, int min) {
    Integer value = optionalInt(node, name, at, min);
    if (value == null) {
      throw invalid(at + "." + name, "값이 있어야 해요");
    }
    return value;
  }

  private static Integer optionalInt(JsonNode node, String name, String at, int min) {
    JsonNode value = node.get(name);
    if (absent(value)) {
      return null;
    }
    if (!value.isIntegralNumber() || !value.canConvertToInt()) {
      throw invalid(at + "." + name, "정수여야 해요");
    }
    if (value.intValue() < min) {
      throw invalid(at + "." + name, min + " 이상이어야 해요");
    }
    return value.intValue();
  }

  private static long requiredLong(JsonNode node, String name, String at, long min) {
    Long value = optionalLong(node, name, at, min);
    if (value == null) {
      throw invalid(at + "." + name, "값이 있어야 해요");
    }
    return value;
  }

  private static Long optionalLong(JsonNode node, String name, String at, long min) {
    JsonNode value = node.get(name);
    if (absent(value)) {
      return null;
    }
    if (!value.isIntegralNumber() || !value.canConvertToLong()) {
      throw invalid(at + "." + name, "정수(원 단위)여야 해요");
    }
    if (value.longValue() < min) {
      throw invalid(at + "." + name, min + " 이상이어야 해요");
    }
    return value.longValue();
  }

  private static BigDecimal optionalPositiveDecimal(JsonNode node, String name, String at) {
    JsonNode value = node.get(name);
    if (absent(value)) {
      return null;
    }
    if (!value.isNumber() || value.decimalValue().signum() <= 0) {
      throw invalid(at + "." + name, "0보다 큰 숫자여야 해요");
    }
    return value.decimalValue();
  }

  private static boolean optionalBoolean(JsonNode node, String name, String at) {
    JsonNode value = node.get(name);
    if (absent(value)) {
      return false;
    }
    if (!value.isBoolean()) {
      throw invalid(at + "." + name, "true 또는 false여야 해요");
    }
    return value.booleanValue();
  }

  private static LocalDate requiredDate(JsonNode node, String name, String at) {
    LocalDate value = optionalDate(node, name, at);
    if (value == null) {
      throw invalid(at + "." + name, "값이 있어야 해요");
    }
    return value;
  }

  private static LocalDate optionalDate(JsonNode node, String name, String at) {
    String text = optionalString(node, name, at);
    if (text == null) {
      return null;
    }
    try {
      return LocalDate.parse(text);
    } catch (DateTimeParseException e) {
      throw invalid(at + "." + name, "날짜는 YYYY-MM-DD 형식이에요");
    }
  }

  private static <E extends Enum<E>> E requiredEnum(
      JsonNode node, String name, String at, Class<E> type) {
    E value = optionalEnum(node, name, at, type);
    if (value == null) {
      throw invalid(at + "." + name, "값이 있어야 해요 " + Arrays.toString(type.getEnumConstants()));
    }
    return value;
  }

  private static <E extends Enum<E>> E optionalEnum(
      JsonNode node, String name, String at, Class<E> type) {
    String text = optionalString(node, name, at);
    if (text == null) {
      return null;
    }
    try {
      return Enum.valueOf(type, text);
    } catch (IllegalArgumentException e) {
      throw invalid(at + "." + name, "다음 중 하나여야 해요: " + Arrays.toString(type.getEnumConstants()));
    }
  }

  private static List<JsonNode> requiredArray(JsonNode node, String name, String at) {
    JsonNode value = node.get(name);
    if (absent(value)) {
      throw invalid(at + "." + name, "목록이 있어야 해요");
    }
    return arrayValues(value, at + "." + name);
  }

  private static List<JsonNode> optionalArray(JsonNode node, String name, String at) {
    JsonNode value = node.get(name);
    return absent(value) ? List.of() : arrayValues(value, at + "." + name);
  }

  private static List<JsonNode> arrayValues(JsonNode value, String at) {
    if (!value.isArray()) {
      throw invalid(at, "목록([...])이어야 해요");
    }
    return List.copyOf(value.values());
  }

  private static void notBothNull(Object a, Object b, String at, String aName, String bName) {
    if (a == null && b == null) {
      throw invalid(at, aName + "와 " + bName + "가 둘 다 비어 있어요");
    }
  }

  private static <T extends Comparable<T>> void ordered(
      T low, T high, String at, String lowName, String highName) {
    if (low != null && high != null && low.compareTo(high) > 0) {
      throw invalid(at, lowName + "가 " + highName + "보다 커요");
    }
  }

  private static void datesOrdered(
      LocalDate from, LocalDate to, String at, String fromName, String toName) {
    if (from != null && to != null && from.isAfter(to)) {
      throw invalid(at, fromName + "가 " + toName + "보다 뒤예요");
    }
  }

  private static CustomException invalid(String at, String problem) {
    return new CustomException(ErrorCode.ELIGIBILITY_INVALID_FRAME, at + ": " + problem);
  }
}
