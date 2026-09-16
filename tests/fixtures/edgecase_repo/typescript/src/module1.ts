import { Service0 } from "./module0";

export interface Handler1 {
  handle(payload: string): boolean;
}

export class Base1 {
  protected name: string;
  constructor(name: string) {
    this.name = name;
  }
}

export class Service1 extends Base1 implements Handler1 {
  handle(payload: string): boolean {
    this.validate(payload);
    return new Service0("x").handle(payload);
  }

  private validate(payload: string): void {}
}

export function helper1(value: string): string {
  return value;
}
