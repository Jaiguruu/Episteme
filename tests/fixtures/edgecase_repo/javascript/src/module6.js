const { Service5 } = require("./module5");

class Base6 {
  constructor(name) {
    this.name = name;
  }
}

class Service6 extends Base6 {
  handle(payload) {
    this.validate(payload);
    return new Service5("x").handle(payload);
  }

  validate(payload) {
    return payload !== null;
  }
}

function helper6(value) {
  return value;
}

module.exports = { Service6 };
