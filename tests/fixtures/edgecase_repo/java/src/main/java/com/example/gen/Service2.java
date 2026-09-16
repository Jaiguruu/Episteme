package com.example.gen;

import com.example.gen.Base2;

public class Service2 extends Base2 implements Handler2 {
    private final String name;

    public Service2(String name) {
        this.name = name;
    }

    public boolean handle(String payload) {
        this.validate(payload);
        return true;
    }

    private void validate(String payload) {
    }
}

interface Handler2 {
    boolean handle(String payload);
}

class Base2 {
    protected String name;
}
