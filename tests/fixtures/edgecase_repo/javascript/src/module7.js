const { Service6 } = require("./module6");

class Base7 {
  constructor(name) {
    this.name = name;
  }
}

class Service7 extends Base7 {
  handle(payload) {
    this.validate(payload);
    return new Service6("x").handle(payload);
  }

  validate(payload) {
    return payload !== null;
  }
}

function helper7(value) {
  return value;
}

module.exports = { Service7 };
