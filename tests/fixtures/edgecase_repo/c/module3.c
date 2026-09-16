#include <stdio.h>
#include "module2.h"

struct Base3 {
    int name;
};

typedef struct Base3 Base3;

int handle_3(const char *payload) {
    validate_3(payload);
    printf("%s", payload);
    return 0;
}

int validate_3(const char *payload) {
    return payload != 0;
}
