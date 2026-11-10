plugins {
    java
    id("org.springframework.boot") version "4.1.1"
    id("io.spring.dependency-management") version "1.1.7"
    id("com.diffplug.spotless") version "8.9.0"
    jacoco
}

group = "kr.mujuthaek"
version = "0.0.1-SNAPSHOT"
description = "api"

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
    implementation("org.springdoc:springdoc-openapi-starter-webmvc-ui:3.1.1") // API 문서(스웨거) /swagger-ui.html. 로컬·개발 서버만 켜요
    implementation("org.springframework.boot:spring-boot-starter-security-oauth2-client") // 소셜 로그인 (카카오·네이버·구글)
    implementation("org.springframework.boot:spring-boot-starter-security-oauth2-resource-server") // JWT 발급·검증 (Nimbus)
    implementation("org.flywaydb:flyway-database-postgresql")
    implementation("org.springframework.modulith:spring-modulith-starter-core:2.0.0")
    implementation(platform("software.amazon.awssdk:bom:2.55.9"))
    implementation("software.amazon.awssdk:s3") // area 원천 파일 읽기 (로컬은 MinIO)
    implementation("org.postgresql:postgresql") // area 적재기가 COPY(CopyManager)를 직접 써요
    implementation("com.github.ben-manes.caffeine:caffeine") // 무거운 관리자 조회를 잠깐 다시 쓰는 캐시 (common/cache/RecentCache)
    implementation("com.networknt:json-schema-validator:3.0.8") // notice가 받은 이벤트를 계약 스키마로 검사해요

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.boot:spring-boot-starter-security-test")
    testImplementation("org.springframework.boot:spring-boot-starter-webmvc-test")
    testImplementation("org.springframework.boot:spring-boot-testcontainers")
    testImplementation("org.testcontainers:testcontainers-junit-jupiter")
    testImplementation("org.testcontainers:testcontainers-postgresql")
    testImplementation("org.testcontainers:testcontainers-rabbitmq") // 아웃박스 발송 테스트
    testImplementation("org.springframework.modulith:spring-modulith-starter-test:2.0.0")
    testImplementation("org.springframework.modulith:spring-modulith-docs:2.0.0")
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

// 저장소의 계약을 그대로 패키징해요. 실행 중 네트워크나 Python 프로세스로 검증하지 않아요.
// 법정동코드표는 AI(extraction)와 같은 저장소 원본 하나를 써요. 빌드 때 api 리소스(common/regions/)로 복사해요.
// 저장소 전체가 보여야 해서(CI는 전체 checkout), services/api만 보이는 곳에서 빌드하면 여기서 멈춰요.
val legalDongCodes = layout.projectDirectory.dir("../extraction/data/legal-dong-codes")
tasks.processResources {
    from("../../contracts") {
        include(
            "schemas/*.json",
            "events/extraction.completed.v1.json",
            "events/policy.extracted.v1.json",
            "mappings/*.json",
        )
        into("contracts")
    }
    inputs.dir(legalDongCodes).withPropertyName("legalDongCodes")
    from(legalDongCodes) {
        include("legal_dong_*.csv")
        into("common/regions")
    }
    doFirst {
        val files = legalDongCodes.asFile.listFiles { f -> f.name.matches(Regex("legal_dong_\\d{8}\\.csv")) }
        check(!files.isNullOrEmpty()) {
            "법정동코드표가 없어요: ${legalDongCodes.asFile} (저장소 전체가 있는 곳에서 빌드하세요)"
        }
    }
}

tasks.processTestResources {
    from("../../contracts") {
        include(
            "examples/*.json",
            "tests/fixtures/*.json",
            "tests/fixtures/judgment/*.json",
            "openapi/*.json",
        )
        into("contracts")
    }
}

// 커버리지는 각 모듈의 service 패키지와 eligibility/rule만 재요 (controller·repository·dto 등은 제외)
jacoco {
    toolVersion = "0.8.14" // 자바 25 클래스 파일 지원
}

val coverageIncludes = listOf("kr/mujuthaek/api/*/service/**", "kr/mujuthaek/api/eligibility/rule/**")

tasks.test {
    finalizedBy(tasks.jacocoTestReport)
}

tasks.jacocoTestReport {
    dependsOn(tasks.test)
    reports {
        xml.required = true
        html.required = true
    }
    classDirectories.setFrom(files(classDirectories.files.map { fileTree(it) { include(coverageIncludes) } }))
}

tasks.jacocoTestCoverageVerification {
    dependsOn(tasks.test)
    classDirectories.setFrom(files(classDirectories.files.map { fileTree(it) { include(coverageIncludes) } }))
    violationRules {
        rule {
            limit {
                counter = "LINE"
                minimum = "0.80".toBigDecimal()
            }
        }
    }
}

tasks.check {
    dependsOn(tasks.jacocoTestCoverageVerification)
}
