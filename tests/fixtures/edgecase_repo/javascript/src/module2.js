const { Service1 } = require("./module1");

class Base2 {
  constructor(name) {
    this.name = name;
  }
}

class Service2 extends Base2 {
  handle(payload) {
    this.validate(payload);
    return new Service1("x").handle(payload);
  }

  validate(payload) {
    return payload !== null;
  }
}

function helper2(value) {
  return value;
}

module.exports = { Service2 };
