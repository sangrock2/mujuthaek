package kr.mujuthaek.api.area.geocode;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties({JusoSearchProperties.class, JusoCoordProperties.class})
class JusoSearchConfig {}
