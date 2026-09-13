package com.example.gen

import com.example.gen.Base3

trait Handler3 {
  def handle(payload: String): Boolean
}

class Base3(val name: String)

class Service3(name: String) extends Base3(name) with Handler3 {
  def handle(payload: String): Boolean = {
    this.validate(payload)
    true
  }

  private def validate(payload: String): Unit = {}
}

object Helpers3 {
  def helper(value: String): String = value
}
