package com.example.gen;

import com.example.gen.Base4;

public class Service4 extends Base4 implements Handler4 {
    private final String name;

    public Service4(String name) {
        this.name = name;
    }

    public boolean handle(String payload) {
        this.validate(payload);
        return true;
    }

    private void validate(String payload) {
    }
}

interface Handler4 {
    boolean handle(String payload);
}

class Base4 {
    protected String name;
}
