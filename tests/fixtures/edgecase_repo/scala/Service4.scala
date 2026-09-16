package com.example.gen

import com.example.gen.Base4

trait Handler4 {
  def handle(payload: String): Boolean
}

class Base4(val name: String)

class Service4(name: String) extends Base4(name) with Handler4 {
  def handle(payload: String): Boolean = {
    this.validate(payload)
    true
  }

  private def validate(payload: String): Unit = {}
}

object Helpers4 {
  def helper(value: String): String = value
}
