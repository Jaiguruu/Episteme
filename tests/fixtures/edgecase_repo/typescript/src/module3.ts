import { Service2 } from "./module2";

export interface Handler3 {
  handle(payload: string): boolean;
}

export class Base3 {
  protected name: string;
  constructor(name: string) {
    this.name = name;
  }
}

export class Service3 extends Base3 implements Handler3 {
  handle(payload: string): boolean {
    this.validate(payload);
    return new Service2("x").handle(payload);
  }

  private validate(payload: string): void {}
}

export function helper3(value: string): string {
  return value;
}
