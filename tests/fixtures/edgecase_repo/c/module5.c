#include <stdio.h>
#include "module4.h"

struct Base5 {
    int name;
};

typedef struct Base5 Base5;

int handle_5(const char *payload) {
    validate_5(payload);
    printf("%s", payload);
    return 0;
}

int validate_5(const char *payload) {
    return payload != 0;
}
