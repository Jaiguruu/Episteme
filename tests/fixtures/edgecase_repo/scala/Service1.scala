package com.example.gen

import com.example.gen.Base1

trait Handler1 {
  def handle(payload: String): Boolean
}

class Base1(val name: String)

class Service1(name: String) extends Base1(name) with Handler1 {
  def handle(payload: String): Boolean = {
    this.validate(payload)
    true
  }

  private def validate(payload: String): Unit = {}
}

object Helpers1 {
  def helper(value: String): String = value
}
