package dev.darya.highload;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.net.URI;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import static org.springframework.http.HttpStatus.NOT_FOUND;

@RestController
@RequestMapping("/items")
public class ItemController {
    public record ItemRequest(@NotBlank @Size(max = 200) String name) {}
    private final ItemStore store;

    public ItemController(ItemStore store) { this.store = store; }

    @PostMapping
    public ResponseEntity<ItemStore.Item> create(@Valid @RequestBody ItemRequest request) {
        var item = store.create(request.name());
        return ResponseEntity.created(URI.create("/items/" + item.id())).body(item);
    }

    @GetMapping("/{id}")
    public ItemStore.Item get(@PathVariable long id) {
        return store.get(id).orElseThrow(() -> new ResponseStatusException(NOT_FOUND, "Item not found"));
    }

    @PutMapping("/{id}")
    public ItemStore.Item update(@PathVariable long id, @Valid @RequestBody ItemRequest request) {
        return store.update(id, request.name())
                .orElseThrow(() -> new ResponseStatusException(NOT_FOUND, "Item not found"));
    }
}
