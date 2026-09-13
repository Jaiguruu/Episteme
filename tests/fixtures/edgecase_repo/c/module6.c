#include <stdio.h>
#include "module5.h"

struct Base6 {
    int name;
};

typedef struct Base6 Base6;

int handle_6(const char *payload) {
    validate_6(payload);
    printf("%s", payload);
    return 0;
}

int validate_6(const char *payload) {
    return payload != 0;
}
