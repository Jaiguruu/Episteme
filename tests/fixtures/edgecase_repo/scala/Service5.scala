package com.example.gen

import com.example.gen.Base5

trait Handler5 {
  def handle(payload: String): Boolean
}

class Base5(val name: String)

class Service5(name: String) extends Base5(name) with Handler5 {
  def handle(payload: String): Boolean = {
    this.validate(payload)
    true
  }

  private def validate(payload: String): Unit = {}
}

object Helpers5 {
  def helper(value: String): String = value
}
