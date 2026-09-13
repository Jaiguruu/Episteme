import 'dart:async';

import 'module0.dart';

abstract class Handler1 {
  bool handle(String payload);
}

class Base1 {
  final String name;
  Base1(this.name);
}

class Service1 extends Base1 implements Handler1 {
  Service1(String name) : super(name);

  @override
  bool handle(String payload) {
    this.validate(payload);
    return true;
  }

  void validate(String payload) {}
}

String helper1(String value) => value;
