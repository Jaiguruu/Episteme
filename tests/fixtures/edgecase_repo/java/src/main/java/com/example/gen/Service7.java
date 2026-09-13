package com.example.gen;

import com.example.gen.Base7;

public class Service7 extends Base7 implements Handler7 {
    private final String name;

    public Service7(String name) {
        this.name = name;
    }

    public boolean handle(String payload) {
        this.validate(payload);
        return true;
    }

    private void validate(String payload) {
    }
}

interface Handler7 {
    boolean handle(String payload);
}

class Base7 {
    protected String name;
}
