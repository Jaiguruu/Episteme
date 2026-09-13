package com.example.gen

import com.example.gen.Base5

interface Handler5 {
    fun handle(payload: String): Boolean
}

open class Base5(val name: String)

class Service5(name: String) : Base5(name), Handler5 {
    override fun handle(payload: String): Boolean {
        validate(payload)
        return true
    }

    private fun validate(payload: String) {}
}

fun helper5(value: String): String {
    return value
}
