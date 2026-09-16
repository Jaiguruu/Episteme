import 'dart:async';

import 'module3.dart';

abstract class Handler4 {
  bool handle(String payload);
}

class Base4 {
  final String name;
  Base4(this.name);
}

class Service4 extends Base4 implements Handler4 {
  Service4(String name) : super(name);

  @override
  bool handle(String payload) {
    this.validate(payload);
    return true;
  }

  void validate(String payload) {}
}

String helper4(String value) => value;
