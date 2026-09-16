package com.example.gen;

import com.example.gen.Base6;

public class Service6 extends Base6 implements Handler6 {
    private final String name;

    public Service6(String name) {
        this.name = name;
    }

    public boolean handle(String payload) {
        this.validate(payload);
        return true;
    }

    private void validate(String payload) {
    }
}

interface Handler6 {
    boolean handle(String payload);
}

class Base6 {
    protected String name;
}
