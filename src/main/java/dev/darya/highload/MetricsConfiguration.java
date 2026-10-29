package dev.darya.highload;

import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.Set;

@Configuration
public class MetricsConfiguration {

    private static final Set<String> SERVICE_PATHS =
            Set.of("/health", "/metrics", "/handlers");

    @Bean
    public MeterFilter excludeServiceRequests() {
        return MeterFilter.deny(id ->
                id.getName().startsWith("http.server.requests")
                        && SERVICE_PATHS.contains(id.getTag("uri"))
        );
    }
}