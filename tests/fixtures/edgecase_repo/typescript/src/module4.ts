import { Service3 } from "./module3";

export interface Handler4 {
  handle(payload: string): boolean;
}

export class Base4 {
  protected name: string;
  constructor(name: string) {
    this.name = name;
  }
}

export class Service4 extends Base4 implements Handler4 {
  handle(payload: string): boolean {
    this.validate(payload);
    return new Service3("x").handle(payload);
  }

  private validate(payload: string): void {}
}

export function helper4(value: string): string {
  return value;
}
