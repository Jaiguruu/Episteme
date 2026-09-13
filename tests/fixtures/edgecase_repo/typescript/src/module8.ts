import { Service7 } from "./module7";

export interface Handler8 {
  handle(payload: string): boolean;
}

export class Base8 {
  protected name: string;
  constructor(name: string) {
    this.name = name;
  }
}

export class Service8 extends Base8 implements Handler8 {
  handle(payload: string): boolean {
    this.validate(payload);
    return new Service7("x").handle(payload);
  }

  private validate(payload: string): void {}
}

export function helper8(value: string): string {
  return value;
}
