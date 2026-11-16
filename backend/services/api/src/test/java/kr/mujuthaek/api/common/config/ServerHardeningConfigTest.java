package kr.mujuthaek.api.common.config;

import static org.assertj.core.api.Assertions.assertThat;

import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.boot.tomcat.servlet.TomcatServletWebServerFactory;
import org.springframework.boot.web.server.WebServer;

/**
 * Tomcat이 {@code /..;/} 같은 의심스러운 주소를 400으로 막는지, 실제 Tomcat을 띄워 원본 주소 그대로 보내 봐요(2026-11-16 보안 감사 4장).
 * Spring Security 방화벽 없이 Tomcat 한 겹만으로 막히는지 보는 거예요.
 */
class ServerHardeningConfigTest {

  @Test
  void tomcatRejectsSuspiciousUris() throws Exception {
    var factory = new TomcatServletWebServerFactory(0);
    factory.addConnectorCustomizers(new ServerHardeningConfig().rejectSuspiciousUris());
    WebServer server = start(factory);
    try {
      assertThat(status(server.getPort(), "/ok")).isEqualTo(200);
      assertThat(status(server.getPort(), "/api/..;/internal/x")).isEqualTo(400);
      assertThat(status(server.getPort(), "/api/%2e%2e/internal/x")).isEqualTo(400);
    } finally {
      server.stop();
    }
  }

  @Test
  void withoutTheCustomizerTomcatNormalizesTheSameUri() throws Exception {
    // 대조군: 설정이 없으면 Tomcat은 「/api/..;/internal/x」를 「/internal/x」로 바꿔 그대로 처리해요
    WebServer server = start(new TomcatServletWebServerFactory(0));
    try {
      assertThat(status(server.getPort(), "/api/..;/internal/x")).isEqualTo(200);
    } finally {
      server.stop();
    }
  }

  private static WebServer start(TomcatServletWebServerFactory factory) {
    WebServer server =
        factory.getWebServer(
            context ->
                context
                    .addServlet(
                        "ok",
                        new HttpServlet() {
                          @Override
                          protected void doGet(HttpServletRequest req, HttpServletResponse res) {
                            res.setStatus(200);
                          }
                        })
                    .addMapping("/*"));
    server.start();
    return server;
  }

  /** 주소를 고치지 않고 그대로 보내려고 소켓으로 직접 써요. */
  private static int status(int port, String rawPath) throws IOException {
    try (var socket = new Socket("127.0.0.1", port)) {
      socket.setSoTimeout(5000);
      OutputStream out = socket.getOutputStream();
      out.write(
          ("GET " + rawPath + " HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
              .getBytes(StandardCharsets.US_ASCII));
      out.flush();
      var in =
          new BufferedReader(
              new InputStreamReader(socket.getInputStream(), StandardCharsets.US_ASCII));
      String statusLine = in.readLine();
      return Integer.parseInt(statusLine.split(" ")[1]);
    }
  }
}
