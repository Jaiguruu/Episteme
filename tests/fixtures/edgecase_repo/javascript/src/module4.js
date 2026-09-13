const { Service3 } = require("./module3");

class Base4 {
  constructor(name) {
    this.name = name;
  }
}

class Service4 extends Base4 {
  handle(payload) {
    this.validate(payload);
    return new Service3("x").handle(payload);
  }

  validate(payload) {
    return payload !== null;
  }
}

function helper4(value) {
  return value;
}

module.exports = { Service4 };
