# 빌드 컨텍스트는 저장소 루트예요: docker build -f services/notification/Dockerfile -t mujuthaek-notification .
# 빌드는 빌드하는 컴퓨터 아키텍처에서(jar는 어디서나 같아요), 실행 이미지만 대상 아키텍처(linux/amd64)로 만들어요.
FROM --platform=$BUILDPLATFORM eclipse-temurin:25-jdk@sha256:b8705e936964c228dfce359e63dbf08f6c69cb380ed1d576b1f6b1064f15567d AS build
WORKDIR /src
COPY services/notification services/notification
WORKDIR /src/services/notification
RUN --mount=type=cache,target=/root/.gradle bash ./gradlew --no-daemon bootJar -x test \
 && find build/libs -name '*.jar' ! -name '*-plain.jar' -exec cp {} /src/app.jar \;

FROM eclipse-temurin:25-jre@sha256:a640968ae55027b322cedd5f8228b01a84baff0b9e9360e47601c6a111ba1699
ENV TZ=Asia/Seoul \
    JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=70 -XX:+ExitOnOutOfMemoryError"
RUN useradd --system --create-home --uid 10001 app
WORKDIR /app
COPY --from=build /src/app.jar app.jar
USER app
EXPOSE 8081
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
