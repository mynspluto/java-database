package kvdb;

import kvdb.store.Storage;

public class Main {
  public static void main(String[] args) {
    System.out.println("Hello, World!");

    Storage storage = new Storage();
    storage.set("123", "value");
    System.out.println(storage.get("123"));
    storage.del("123");
    System.out.println(storage.get("123"));
  }
}