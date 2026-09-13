package com.example.gen

import com.example.gen.Base6

interface Handler6 {
    fun handle(payload: String): Boolean
}

open class Base6(val name: String)

class Service6(name: String) : Base6(name), Handler6 {
    override fun handle(payload: String): Boolean {
        validate(payload)
        return true
    }

    private fun validate(payload: String) {}
}

fun helper6(value: String): String {
    return value
}
