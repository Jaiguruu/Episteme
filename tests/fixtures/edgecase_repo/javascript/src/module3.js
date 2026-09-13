const { Service2 } = require("./module2");

class Base3 {
  constructor(name) {
    this.name = name;
  }
}

class Service3 extends Base3 {
  handle(payload) {
    this.validate(payload);
    return new Service2("x").handle(payload);
  }

  validate(payload) {
    return payload !== null;
  }
}

function helper3(value) {
  return value;
}

module.exports = { Service3 };
