package com.example.gen;

import com.example.gen.Base5;

public class Service5 extends Base5 implements Handler5 {
    private final String name;

    public Service5(String name) {
        this.name = name;
    }

    public boolean handle(String payload) {
        this.validate(payload);
        return true;
    }

    private void validate(String payload) {
    }
}

interface Handler5 {
    boolean handle(String payload);
}

class Base5 {
    protected String name;
}
