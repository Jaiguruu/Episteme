import { Service1 } from "./module1";

export interface Handler2 {
  handle(payload: string): boolean;
}

export class Base2 {
  protected name: string;
  constructor(name: string) {
    this.name = name;
  }
}

export class Service2 extends Base2 implements Handler2 {
  handle(payload: string): boolean {
    this.validate(payload);
    return new Service1("x").handle(payload);
  }

  private validate(payload: string): void {}
}

export function helper2(value: string): string {
  return value;
}
