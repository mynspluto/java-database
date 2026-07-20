package kvdb.store;

import java.util.Map;
import java.util.HashMap;
import java.util.Objects;

public class Storage {
    private final Map<String, String> map;

    public Storage() {
        this.map = new HashMap<>();
    }

    public get(String key) {
        return _hashmap.get(key);
    }

    public void set(String Key, String value) {
        Objects.requireNonNull(key, "key must not be null");
        Objects.requireNonNull(value, "value must not be null");
        map.put(key, value);
    }

    public boolean del(String key) {
        return map.remove(key) != null;
    }
}