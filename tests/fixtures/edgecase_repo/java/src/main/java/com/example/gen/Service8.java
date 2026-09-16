package com.example.gen;

import com.example.gen.Base8;

public class Service8 extends Base8 implements Handler8 {
    private final String name;

    public Service8(String name) {
        this.name = name;
    }

    public boolean handle(String payload) {
        this.validate(payload);
        return true;
    }

    private void validate(String payload) {
    }
}

interface Handler8 {
    boolean handle(String payload);
}

class Base8 {
    protected String name;
}
