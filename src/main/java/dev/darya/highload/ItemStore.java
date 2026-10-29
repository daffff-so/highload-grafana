package dev.darya.highload;

import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Service;

@Service
public class ItemStore {
    public record Item(long id, String name) {}
    private final ConcurrentHashMap<Long, Item> items = new ConcurrentHashMap<>();
    private final AtomicLong sequence = new AtomicLong();

    public Item create(String name) {
        var item = new Item(sequence.incrementAndGet(), name);
        items.put(item.id(), item);
        return item;
    }

    public Optional<Item> get(long id) {
        return Optional.ofNullable(items.get(id));
    }

    public Optional<Item> update(long id, String name) {
        return Optional.ofNullable(items.computeIfPresent(id, (key, old) -> new Item(key, name)));
    }
}
