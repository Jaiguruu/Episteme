package com.example.gen;

import com.example.gen.Base1;

public class Service1 extends Base1 implements Handler1 {
    private final String name;

    public Service1(String name) {
        this.name = name;
    }

    public boolean handle(String payload) {
        this.validate(payload);
        return true;
    }

    private void validate(String payload) {
    }
}

interface Handler1 {
    boolean handle(String payload);
}

class Base1 {
    protected String name;
}
