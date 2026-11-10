package kr.mujuthaek.api;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.sql.Connection;
import java.util.concurrent.atomic.AtomicInteger;
import javax.sql.DataSource;

/** 보낸 SQL 문 수를 세는 DataSource (테스트용). 공고 수만큼 쿼리가 늘지 않는지 볼 때 써요. */
public final class CountingDataSource {

  private final AtomicInteger statements = new AtomicInteger();
  private final DataSource dataSource;

  public CountingDataSource(DataSource target) {
    this.dataSource =
        (DataSource)
            Proxy.newProxyInstance(
                DataSource.class.getClassLoader(),
                new Class<?>[] {DataSource.class},
                (proxy, method, args) -> {
                  Object result = invoke(target, method, args);
                  return result instanceof Connection c ? counting(c) : result;
                });
  }

  public DataSource dataSource() {
    return dataSource;
  }

  public int statements() {
    return statements.get();
  }

  public void reset() {
    statements.set(0);
  }

  private Connection counting(Connection target) {
    return (Connection)
        Proxy.newProxyInstance(
            Connection.class.getClassLoader(),
            new Class<?>[] {Connection.class},
            (proxy, method, args) -> {
              String name = method.getName();
              if (name.equals("prepareStatement")
                  || name.equals("prepareCall")
                  || name.equals("createStatement")) {
                statements.incrementAndGet();
              }
              return invoke(target, method, args);
            });
  }

  private static Object invoke(Object target, java.lang.reflect.Method method, Object[] args)
      throws Throwable {
    try {
      return method.invoke(target, args);
    } catch (InvocationTargetException e) {
      throw e.getCause();
    }
  }
}
