package com.example.gen;

import com.example.gen.Base3;

public class Service3 extends Base3 implements Handler3 {
    private final String name;

    public Service3(String name) {
        this.name = name;
    }

    public boolean handle(String payload) {
        this.validate(payload);
        return true;
    }

    private void validate(String payload) {
    }
}

interface Handler3 {
    boolean handle(String payload);
}

class Base3 {
    protected String name;
}
