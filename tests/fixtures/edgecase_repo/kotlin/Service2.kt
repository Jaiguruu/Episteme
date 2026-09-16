package com.example.gen

import com.example.gen.Base2

interface Handler2 {
    fun handle(payload: String): Boolean
}

open class Base2(val name: String)

class Service2(name: String) : Base2(name), Handler2 {
    override fun handle(payload: String): Boolean {
        validate(payload)
        return true
    }

    private fun validate(payload: String) {}
}

fun helper2(value: String): String {
    return value
}
