const { Service0 } = require("./module0");

class Base1 {
  constructor(name) {
    this.name = name;
  }
}

class Service1 extends Base1 {
  handle(payload) {
    this.validate(payload);
    return new Service0("x").handle(payload);
  }

  validate(payload) {
    return payload !== null;
  }
}

function helper1(value) {
  return value;
}

module.exports = { Service1 };
