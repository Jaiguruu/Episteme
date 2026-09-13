#include <stdio.h>
#include "module0.h"

struct Base1 {
    int name;
};

typedef struct Base1 Base1;

int handle_1(const char *payload) {
    validate_1(payload);
    printf("%s", payload);
    return 0;
}

int validate_1(const char *payload) {
    return payload != 0;
}
