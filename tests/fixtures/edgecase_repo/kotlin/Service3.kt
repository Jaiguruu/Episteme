package com.example.gen

import com.example.gen.Base3

interface Handler3 {
    fun handle(payload: String): Boolean
}

open class Base3(val name: String)

class Service3(name: String) : Base3(name), Handler3 {
    override fun handle(payload: String): Boolean {
        validate(payload)
        return true
    }

    private fun validate(payload: String) {}
}

fun helper3(value: String): String {
    return value
}
