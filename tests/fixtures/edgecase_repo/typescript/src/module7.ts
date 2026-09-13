import { Service6 } from "./module6";

export interface Handler7 {
  handle(payload: string): boolean;
}

export class Base7 {
  protected name: string;
  constructor(name: string) {
    this.name = name;
  }
}

export class Service7 extends Base7 implements Handler7 {
  handle(payload: string): boolean {
    this.validate(payload);
    return new Service6("x").handle(payload);
  }

  private validate(payload: string): void {}
}

export function helper7(value: string): string {
  return value;
}
