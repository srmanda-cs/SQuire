#include <stdlib.h>

struct foo {
    int x;
};

/* emulate kmalloc for testing */
void *kmalloc(size_t size, int flags) {
    return malloc(size);
}

void good(void)
{
    struct foo *p = kmalloc(sizeof(*p), 0);
    if (!p)
        return;
    p->x = 1; // should NOT warn
}

void bad(void)
{
    struct foo *p = kmalloc(sizeof(*p), 0);
    p->x = 2; // should warn
}

void bad2(void)
{
    struct foo *p = kmalloc(sizeof(*p), 0);
    *p = (struct foo){ .x = 3 }; // should warn
}
