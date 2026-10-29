package dev.darya.highload;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;

import java.util.Comparator;
import java.util.List;
import java.util.Set;

@RestController
public class HandlersController {

    private static final Set<String> SERVICE_PATHS =
            Set.of("/health", "/metrics", "/handlers", "/error");

    private final RequestMappingHandlerMapping mappings;

    public HandlersController(
            @Qualifier("requestMappingHandlerMapping")
            RequestMappingHandlerMapping mappings) {
        this.mappings = mappings;
    }

    public record Handler(String method, String path) {}

    @GetMapping("/handlers")
    public List<Handler> handlers() {
        return mappings.getHandlerMethods().entrySet().stream()
                .filter(entry -> entry.getValue().getBeanType()
                        .getPackageName().startsWith("dev.darya.highload"))
                .flatMap(entry -> entry.getKey().getPatternValues().stream()
                        .filter(path -> !SERVICE_PATHS.contains(path))
                        .flatMap(path -> entry.getKey()
                                .getMethodsCondition().getMethods().stream()
                                .map(method -> new Handler(method.name(), path))))
                .distinct()
                .sorted(Comparator.comparing(Handler::path)
                        .thenComparing(Handler::method))
                .toList();
    }
}
