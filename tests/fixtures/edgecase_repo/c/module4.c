#include <stdio.h>
#include "module3.h"

struct Base4 {
    int name;
};

typedef struct Base4 Base4;

int handle_4(const char *payload) {
    validate_4(payload);
    printf("%s", payload);
    return 0;
}

int validate_4(const char *payload) {
    return payload != 0;
}
