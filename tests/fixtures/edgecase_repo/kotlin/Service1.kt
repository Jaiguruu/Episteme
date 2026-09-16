package com.example.gen

import com.example.gen.Base1

interface Handler1 {
    fun handle(payload: String): Boolean
}

open class Base1(val name: String)

class Service1(name: String) : Base1(name), Handler1 {
    override fun handle(payload: String): Boolean {
        validate(payload)
        return true
    }

    private fun validate(payload: String) {}
}

fun helper1(value: String): String {
    return value
}
