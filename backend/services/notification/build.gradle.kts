plugins {
    java
    id("org.springframework.boot") version "4.1.1"
    id("io.spring.dependency-management") version "1.1.7"
    id("com.diffplug.spotless") version "8.9.0"
}

group = "kr.mujuthaek"
version = "0.0.1-SNAPSHOT"
description = "notification"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webmvc")
    implementation("org.springframework.boot:spring-boot-starter-validation")
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
    implementation("org.springframework.boot:spring-boot-starter-flyway")
    implementation("org.springframework.boot:spring-boot-starter-amqp")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus") // 성능 테스트 지표 (/actuator/prometheus, 서버 안에서만)
    implementation("org.flywaydb:flyway-database-postgresql")
    implementation(platform("software.amazon.awssdk:bom:2.55.9")) // api와 같은 버전
    implementation("software.amazon.awssdk:sesv2") // 이메일 발송
    runtimeOnly("org.postgresql:postgresql")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.boot:spring-boot-testcontainers")
    testImplementation("org.testcontainers:testcontainers-junit-jupiter")
    testImplementation("org.testcontainers:testcontainers-postgresql")
    testImplementation("org.testcontainers:testcontainers-rabbitmq")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

spotless {
    java {
        googleJavaFormat()
        removeUnusedImports()
        trimTrailingWhitespace()
        endWithNewline()
    }
}

tasks.withType<Test> {
    useJUnitPlatform()
}

val e2e = sourceSets.create("e2e") {
    compileClasspath += sourceSets.main.get().output
    runtimeClasspath += sourceSets.main.get().output
}
configurations[e2e.implementationConfigurationName].extendsFrom(configurations.implementation.get())
configurations[e2e.runtimeOnlyConfigurationName].extendsFrom(configurations.runtimeOnly.get())
tasks.register<JavaExec>("e2eRun") {
    dependsOn(e2e.classesTaskName)
    classpath = e2e.runtimeClasspath
    mainClass = "kr.mujuthaek.e2e.E2eNotificationApplication"
}
val verifyE2eIsolation by tasks.registering {
    dependsOn(tasks.bootJar)
    doLast {
        val entries = zipTree(tasks.bootJar.get().archiveFile.get().asFile)
        check(entries.matching { include("**/kr/mujuthaek/e2e/**", "**/application-e2e.yml") }.isEmpty) {
            "운영 jar에 E2E 제어 코드가 포함됐어요"
        }
    }
}
tasks.check { dependsOn(verifyE2eIsolation) }
