import 'dart:async';

import 'module2.dart';

abstract class Handler3 {
  bool handle(String payload);
}

class Base3 {
  final String name;
  Base3(this.name);
}

class Service3 extends Base3 implements Handler3 {
  Service3(String name) : super(name);

  @override
  bool handle(String payload) {
    this.validate(payload);
    return true;
  }

  void validate(String payload) {}
}

String helper3(String value) => value;
