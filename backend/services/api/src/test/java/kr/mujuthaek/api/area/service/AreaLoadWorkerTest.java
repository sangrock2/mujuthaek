package kr.mujuthaek.api.area.service;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.time.Duration;
import java.time.LocalDate;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import kr.mujuthaek.api.area.domain.AreaLoadReport;
import kr.mujuthaek.api.area.domain.AreaLoadRequest;
import kr.mujuthaek.api.area.domain.AreaSource;
import kr.mujuthaek.api.area.repository.AreaLoadQueue;
import kr.mujuthaek.api.common.alert.OpsAlert;
import org.junit.jupiter.api.Test;

class AreaLoadWorkerTest {

  private final AreaLoadQueue queue = mock(AreaLoadQueue.class);
  private final AreaSourceLoadService loads = mock(AreaSourceLoadService.class);
  private final OpsAlert alert = mock(OpsAlert.class);
  private final AreaLoadWorker worker = new AreaLoadWorker(queue, loads, alert, true);

  private static final AreaLoadRequest REQUEST =
      new AreaLoadRequest(
          AreaSource.ADDRESS_ENTRANCE, "27", "area/x.txt", "a".repeat(64), LocalDate.now(), false);

  @Test
  void drain_loadsEveryWaitingFile_withTheClaimedRun() {
    UUID run = UUID.randomUUID();
    when(queue.claimNext())
        .thenReturn(Optional.of(new AreaLoadQueue.Claimed(run, REQUEST, 1)), Optional.empty());
    when(loads.loadQueued(eq(run), any())).thenReturn(AreaLoadReport.skipped(run));

    worker.drain();

    verify(loads).loadQueued(eq(run), any());
    verify(alert, never()).send(anyString(), anyString(), any());
  }

  @Test
  void fileProblem_isAlerted_andNotRetried() {
    UUID run = UUID.randomUUID();
    when(loads.loadQueued(eq(run), any())).thenReturn(AreaLoadReport.failed(run, "칸이 없어요"));

    worker.loadOne(new AreaLoadQueue.Claimed(run, REQUEST, 1));

    verify(alert).send(eq("area.load.failed:ADDRESS_ENTRANCE"), anyString(), eq("칸이 없어요"));
    verify(queue, never()).release(any(), anyInt(), anyString(), any());
  }

  @Test
  void connectionError_isRetriedLater_andAlertedOnlyWhenGivingUp() {
    UUID run = UUID.randomUUID();
    when(loads.loadQueued(eq(run), any())).thenThrow(new IllegalStateException("S3 연결 끊김"));
    when(queue.release(eq(run), eq(1), anyString(), any())).thenReturn(true);
    when(queue.release(eq(run), eq(3), anyString(), any())).thenReturn(false);

    worker.loadOne(new AreaLoadQueue.Claimed(run, REQUEST, 1));
    verify(queue).release(eq(run), eq(1), anyString(), eq(Duration.ofMinutes(1)));
    verify(alert, never()).send(anyString(), anyString(), any());

    worker.loadOne(new AreaLoadQueue.Claimed(run, REQUEST, 3));
    verify(alert).send(eq("area.load.error:ADDRESS_ENTRANCE"), anyString(), anyString());
  }

  @Test
  void recover_alertsWhenStaleRunsWereClosed() {
    when(queue.recoverStale(AreaLoadWorker.STALE_ERROR))
        .thenReturn(List.of(new AreaLoadQueue.Recovered(REQUEST, 1, true)));

    worker.recover();

    verify(alert).send(eq("area.load.stale"), anyString(), anyString());
  }
}
