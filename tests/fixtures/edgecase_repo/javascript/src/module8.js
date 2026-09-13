const { Service7 } = require("./module7");

class Base8 {
  constructor(name) {
    this.name = name;
  }
}

class Service8 extends Base8 {
  handle(payload) {
    this.validate(payload);
    return new Service7("x").handle(payload);
  }

  validate(payload) {
    return payload !== null;
  }
}

function helper8(value) {
  return value;
}

module.exports = { Service8 };
