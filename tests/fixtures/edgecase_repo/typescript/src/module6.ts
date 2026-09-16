import { Service5 } from "./module5";

export interface Handler6 {
  handle(payload: string): boolean;
}

export class Base6 {
  protected name: string;
  constructor(name: string) {
    this.name = name;
  }
}

export class Service6 extends Base6 implements Handler6 {
  handle(payload: string): boolean {
    this.validate(payload);
    return new Service5("x").handle(payload);
  }

  private validate(payload: string): void {}
}

export function helper6(value: string): string {
  return value;
}
