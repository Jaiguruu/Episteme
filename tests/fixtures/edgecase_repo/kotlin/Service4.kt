package com.example.gen

import com.example.gen.Base4

interface Handler4 {
    fun handle(payload: String): Boolean
}

open class Base4(val name: String)

class Service4(name: String) : Base4(name), Handler4 {
    override fun handle(payload: String): Boolean {
        validate(payload)
        return true
    }

    private fun validate(payload: String) {}
}

fun helper4(value: String): String {
    return value
}
