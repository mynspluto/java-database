package kvdb;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;

import kvdb.store.Storage;

public class Main {
  public static void main(String[] args) throws IOException {
    Storage storage = new Storage();
    BufferedReader reader = new BufferedReader(new InputStreamReader(System.in));

    String line;
    while((line = reader.readLine()) != null) {
      line = line.trim();
      if(line.isEmpty()) {
        continue;
      }

      String[] parts = line.split("\\s+", 3);
      String command = parts[0].toLowerCase();

      switch(command) {
        case "set" -> {
          if(parts.length != 3) {
            System.out.println("ERR wrong number of arguments for 'set'");
          } else {
            storage.set(parts[1], parts[2]);
            System.out.println("OK");
          }
        }
        case "get" -> {
          if(parts.length != 2) {
            System.out.println("ERR wrong number of argumets for 'get");
          } else {
            String value = storage.get(parts[1]);
            System.out.println(value == null ? "(nil)" : value);
          }
        }
        case "del" -> {
          if(parts.length != 2) {
            System.out.println("ERR wrong number of arguments for 'del'");
          } else {
            System.out.println(storage.del(parts[1]) ? 1 : 0);
          }
        }
        case "exit", "quit" -> {
          return;
        }
        default -> System.out.println("ERR unknown command '" + command + "'");
      }
    }
  }
}