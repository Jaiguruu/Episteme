const { Service4 } = require("./module4");

class Base5 {
  constructor(name) {
    this.name = name;
  }
}

class Service5 extends Base5 {
  handle(payload) {
    this.validate(payload);
    return new Service4("x").handle(payload);
  }

  validate(payload) {
    return payload !== null;
  }
}

function helper5(value) {
  return value;
}

module.exports = { Service5 };
