#include <stdio.h>
#include "module1.h"

struct Base2 {
    int name;
};

typedef struct Base2 Base2;

int handle_2(const char *payload) {
    validate_2(payload);
    printf("%s", payload);
    return 0;
}

int validate_2(const char *payload) {
    return payload != 0;
}
