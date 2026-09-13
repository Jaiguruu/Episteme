import { Service4 } from "./module4";

export interface Handler5 {
  handle(payload: string): boolean;
}

export class Base5 {
  protected name: string;
  constructor(name: string) {
    this.name = name;
  }
}

export class Service5 extends Base5 implements Handler5 {
  handle(payload: string): boolean {
    this.validate(payload);
    return new Service4("x").handle(payload);
  }

  private validate(payload: string): void {}
}

export function helper5(value: string): string {
  return value;
}
