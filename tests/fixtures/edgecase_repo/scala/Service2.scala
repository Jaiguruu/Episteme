package com.example.gen

import com.example.gen.Base2

trait Handler2 {
  def handle(payload: String): Boolean
}

class Base2(val name: String)

class Service2(name: String) extends Base2(name) with Handler2 {
  def handle(payload: String): Boolean = {
    this.validate(payload)
    true
  }

  private def validate(payload: String): Unit = {}
}

object Helpers2 {
  def helper(value: String): String = value
}
