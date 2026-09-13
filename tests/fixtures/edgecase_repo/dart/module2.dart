import 'dart:async';

import 'module1.dart';

abstract class Handler2 {
  bool handle(String payload);
}

class Base2 {
  final String name;
  Base2(this.name);
}

class Service2 extends Base2 implements Handler2 {
  Service2(String name) : super(name);

  @override
  bool handle(String payload) {
    this.validate(payload);
    return true;
  }

  void validate(String payload) {}
}

String helper2(String value) => value;
