pluginManagement {
    repositories {
        // 플러그인 표식은 기존에 검증한 Plugin Portal에서, 공통 라이브러리는 Maven Central에서 받아요.
        mavenCentral {
            content {
                excludeModuleByRegex(".*", ".*\\.gradle\\.plugin")
            }
        }
        gradlePluginPortal()
    }
}

rootProject.name = "api"
