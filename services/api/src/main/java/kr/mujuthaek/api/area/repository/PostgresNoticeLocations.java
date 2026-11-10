package kr.mujuthaek.api.area.repository;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import javax.sql.DataSource;
import kr.mujuthaek.api.area.domain.Coordinate;
import kr.mujuthaek.api.area.domain.GeocodeResult;
import kr.mujuthaek.api.area.domain.GeocodeResult.FailReason;
import kr.mujuthaek.api.area.domain.GeocodeResult.Method;
import kr.mujuthaek.api.area.domain.GeocodeResult.Status;
import kr.mujuthaek.api.area.domain.NoticeLocation;
import kr.mujuthaek.api.area.domain.StoredLocation;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Component;

/**
 * 공고 위치의 좌표(area.notice_locations) 읽기·쓰기. 같은 공고·위치 ID는 한 줄이고, 다시 저장하면 area 위치 ID(location_id)는 그대로
 * 두고 내용만 바꿔요(세권 지표·점수가 그 ID를 가리켜요). JDBC만 써서 테스트에서는 {@code new}로 만들어요.
 */
@Component
public final class PostgresNoticeLocations {

  private static final String REUSABLE =
      """
      select method, st_y(geom::geometry) as lat, st_x(geom::geometry) as lng, bjd_code_found, region_mismatch
      from area.notice_locations
      where address_key = ? and bjd_code_given is not distinct from ? and status = 'OK'
      order by calculated_at desc
      limit 1
      """;

  private static final String SAVE =
      """
      insert into area.notice_locations as t (notice_id, notice_location_id, notice_version, kind, address_text,
                                              address_key, bjd_code_given, bjd_code_found, geom, status, method,
                                              fail_reason, region_mismatch, calculated_at)
      values (?, ?, ?, ?, ?, ?, ?, ?,
              case when ?::float8 is null then null else st_setsrid(st_makepoint(?, ?), 4326)::geography end,
              ?, ?, ?, ?, now())
      on conflict (notice_id, notice_location_id) do update
        set notice_version = excluded.notice_version, kind = excluded.kind, address_text = excluded.address_text,
            address_key = excluded.address_key, bjd_code_given = excluded.bjd_code_given,
            bjd_code_found = excluded.bjd_code_found, geom = excluded.geom, status = excluded.status,
            method = excluded.method, fail_reason = excluded.fail_reason,
            region_mismatch = excluded.region_mismatch, calculated_at = now()
      returning location_id
      """;

  private final DataSource dataSource;
  private final JdbcTemplate jdbc;

  public PostgresNoticeLocations(DataSource dataSource) {
    this.dataSource = dataSource;
    this.jdbc = new JdbcTemplate(dataSource);
  }

  /**
   * 같은 주소 키·같은 받은 법정동코드로 이미 찾은 정확한 좌표(OK). 대략 위치(APPROX)·실패는 나중에 더 잘 찾을 수 있어서 다시 써요(재사용 안 함).
   * 시군구·주소 ID는 저장하지 않아서 비어요.
   *
   * <p>법정동코드도 같아야 해요: 찾을 때 그 코드로 시군구를 좁히므로, 「중앙로 7」처럼 시군구 없는 주소는 코드가 다르면 다른 곳이에요. 주소 글자만 보면 다른 도시의
   * 좌표를 그대로 썼어요(2026-11-10 코드 검토).
   */
  public Optional<GeocodeResult> reusable(String addressKey, String bjdCodeGiven) {
    if (addressKey == null || addressKey.isBlank()) {
      return Optional.empty();
    }
    try (Connection conn = dataSource.getConnection();
        PreparedStatement ps = conn.prepareStatement(REUSABLE)) {
      ps.setString(1, addressKey);
      ps.setString(2, bjdCodeGiven);
      try (ResultSet rs = ps.executeQuery()) {
        if (!rs.next()) {
          return Optional.empty();
        }
        return Optional.of(
            new GeocodeResult(
                Status.OK,
                Method.valueOf(rs.getString("method")),
                new Coordinate(rs.getDouble("lat"), rs.getDouble("lng")),
                rs.getString("bjd_code_found"),
                null,
                null,
                null,
                rs.getBoolean("region_mismatch")));
      }
    } catch (SQLException e) {
      throw new DataAccessResourceFailureException("공고 위치를 읽지 못했어요: " + e.getMessage(), e);
    }
  }

  /** 저장한 줄의 area 위치 ID를 돌려줘요 (처음이면 새로, 있던 위치면 그대로). */
  public UUID save(NoticeLocation location, String addressKey, GeocodeResult result) {
    Coordinate c = result.coordinate();
    FailReason reason = result.failReason();
    try (Connection conn = dataSource.getConnection();
        PreparedStatement ps = conn.prepareStatement(SAVE)) {
      ps.setObject(1, location.noticeId());
      ps.setString(2, location.noticeLocationId());
      ps.setInt(3, location.noticeVersion());
      ps.setString(4, location.kind() == null ? "UNKNOWN" : location.kind());
      ps.setString(5, location.address() == null ? "" : location.address());
      ps.setString(6, addressKey);
      ps.setString(7, location.bjdCode());
      ps.setString(8, result.bjdCodeFound());
      ps.setObject(9, c == null ? null : c.lng(), Types.DOUBLE);
      ps.setObject(10, c == null ? null : c.lng(), Types.DOUBLE);
      ps.setObject(11, c == null ? null : c.lat(), Types.DOUBLE);
      ps.setString(12, result.status().name());
      ps.setString(13, result.method() == null ? null : result.method().name());
      ps.setString(14, reason == null ? null : reason.name());
      ps.setBoolean(15, result.regionMismatch());
      try (ResultSet rs = ps.executeQuery()) {
        rs.next();
        return rs.getObject(1, UUID.class);
      }
    } catch (SQLException e) {
      throw new DataAccessResourceFailureException("공고 위치를 저장하지 못했어요: " + e.getMessage(), e);
    }
  }

  private static final String STORED_COLUMNS =
      "location_id, notice_id, notice_location_id, notice_version, address_text, bjd_code_given, status,"
          + " fail_reason, st_y(geom::geometry) as lat, st_x(geom::geometry) as lng";

  private static final RowMapper<StoredLocation> STORED =
      (rs, n) ->
          new StoredLocation(
              rs.getObject("location_id", UUID.class),
              rs.getObject("notice_id", UUID.class),
              rs.getString("notice_location_id"),
              rs.getInt("notice_version"),
              rs.getString("address_text"),
              rs.getString("bjd_code_given"),
              Status.valueOf(rs.getString("status")),
              rs.getString("fail_reason") == null
                  ? null
                  : FailReason.valueOf(rs.getString("fail_reason")),
              rs.getObject("lat") == null
                  ? null
                  : new Coordinate(rs.getDouble("lat"), rs.getDouble("lng")));

  /** 공고의 지금 위치들 (notice 위치 ID 순). */
  public List<StoredLocation> ofNotice(UUID noticeId) {
    return jdbc.query(
        "select "
            + STORED_COLUMNS
            + " from area.notice_locations where notice_id = ? order by notice_location_id",
        STORED,
        noticeId);
  }

  /** 공고의 위치 중 keep에 없는 것을 지우고 지운 수를 돌려줘요. 세권 지표·점수는 area 안 외래 키(on delete cascade)로 같이 지워져요. */
  public int deleteMissing(UUID noticeId, Collection<String> keep) {
    return jdbc.update(
        "delete from area.notice_locations where notice_id = ? and not (notice_location_id = any(?::text[]))",
        noticeId,
        keep.toArray(String[]::new));
  }

  /** 좌표를 다시 찾지 않은 위치의 공고 버전만 올려요 (위치가 같은 새 공고 버전). */
  public void touchVersion(UUID locationId, int noticeVersion) {
    jdbc.update(
        "update area.notice_locations set notice_version = ? where location_id = ?",
        noticeVersion,
        locationId);
  }

  /** 좌표가 있는 모든 위치 (공고 순). 시설·상가를 다시 적재해 점수를 다시 보낼 때 써요. */
  public List<StoredLocation> withCoordinates() {
    return jdbc.query(
        "select "
            + STORED_COLUMNS
            + " from area.notice_locations where geom is not null order by notice_id, notice_location_id",
        STORED);
  }

  /** 좌표를 못 찾은 위치 (최근 계산 순). 관리자 화면 데이터예요. */
  public List<StoredLocation> failed(int limit) {
    return jdbc.query(
        "select "
            + STORED_COLUMNS
            + " from area.notice_locations where status = 'FAILED' order by calculated_at desc limit ?",
        STORED,
        limit);
  }

  /** 위치 ID로 위치들 (없는 ID는 빠져요). */
  public List<StoredLocation> byIds(Collection<UUID> locationIds) {
    if (locationIds.isEmpty()) {
      return List.of();
    }
    return jdbc.query(
        "select "
            + STORED_COLUMNS
            + " from area.notice_locations where location_id = any(?::uuid[])",
        STORED,
        (Object) locationIds.toArray(UUID[]::new));
  }

  /** 한 점(직장 등)에서 각 위치까지 거리(m, 반올림). 좌표가 없는 위치는 빠져요. 저장하지 않아요. */
  public java.util.Map<UUID, Long> distancesFrom(Collection<UUID> locationIds, Coordinate from) {
    java.util.Map<UUID, Long> out = new java.util.LinkedHashMap<>();
    if (locationIds.isEmpty()) {
      return out;
    }
    jdbc.query(
        "select location_id, round(st_distance(geom, st_setsrid(st_makepoint(?, ?), 4326)::geography))::bigint as m"
            + " from area.notice_locations where location_id = any(?::uuid[]) and geom is not null",
        rs -> {
          out.put(rs.getObject("location_id", UUID.class), rs.getLong("m"));
        },
        from.lng(),
        from.lat(),
        locationIds.toArray(UUID[]::new));
    return out;
  }

  /** 여러 공고의 위치들 (공고·notice 위치 ID 순). */
  public List<StoredLocation> ofNotices(Collection<UUID> noticeIds) {
    if (noticeIds.isEmpty()) {
      return List.of();
    }
    return jdbc.query(
        "select "
            + STORED_COLUMNS
            + " from area.notice_locations where notice_id = any(?::uuid[])"
            + " order by notice_id, notice_location_id",
        STORED,
        (Object) noticeIds.toArray(UUID[]::new));
  }

  /** 지도 범위 안 공고의 대표 좌표 (공고마다 notice 위치 ID가 가장 앞인 위치 하나). 공간 인덱스를 써요. */
  public List<StoredLocation> representativesWithin(
      double swLat, double swLng, double neLat, double neLng, int limit) {
    return jdbc.query(
        "select * from (select distinct on (notice_id) "
            + STORED_COLUMNS
            + " from area.notice_locations"
            + " where geom && st_makeenvelope(?, ?, ?, ?, 4326)::geography"
            + " order by notice_id, notice_location_id) x limit ?",
        STORED,
        swLng,
        swLat,
        neLng,
        neLat,
        limit);
  }
}
