import 'dart:async';

import 'module4.dart';

abstract class Handler5 {
  bool handle(String payload);
}

class Base5 {
  final String name;
  Base5(this.name);
}

class Service5 extends Base5 implements Handler5 {
  Service5(String name) : super(name);

  @override
  bool handle(String payload) {
    this.validate(payload);
    return true;
  }

  void validate(String payload) {}
}

String helper5(String value) => value;
