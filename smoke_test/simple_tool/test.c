// test.c
#include <stdlib.h>

/*
 * 1. BAD: malloc result is never checked before dereference.
 *    NPDChecker should report a warning at "*p = 42".
 */
int test_bad_malloc_no_check(void) {
    int *p = malloc(sizeof(int));  // may return NULL
    *p = 42;                       // unchecked dereference of possibly-NULL
    free(p);
    return *p;
}

/*
 * 2. GOOD: classic "if (!p) return;" pattern.
 *    On the path that reaches "*p = 10", the analyzer knows p != NULL.
 *    NPDChecker should NOT report a warning here.
 */
int test_good_malloc_with_check1(void) {
    int *p = malloc(sizeof(int));
    if (!p) {
        return -1;                 // NULL path exits here
    }
    *p = 10;                       // p is definitely non-NULL on this path
    int v = *p;
    free(p);
    return v;
}

/*
 * 3. BAD: pointer is compared to NULL, but execution continues on both paths.
 *    On the path where p == NULL, we still reach "*p = 5".
 *    NPDChecker should report a warning at "*p = 5".
 */
int test_bad_malloc_incomplete_check(void) {
    int *p = malloc(sizeof(int));
    if (p == NULL) {
        /* log error but do NOT return or fix p */
    }
    *p = 5;                        // possibly-NULL dereference
    free(p);
    return *p;
}

/*
 * 4. GOOD: explicit equality check with early return on NULL.
 *    NPDChecker should NOT report a warning at "*p = 20".
 */
int test_good_malloc_with_check2(void) {
    int *p = malloc(sizeof(int));
    if (p == NULL) {
        return -1;                 // guard against NULL
    }
    *p = 20;                       // safe
    int v = *p;
    free(p);
    return v;
}

/*
 * 5. Metadata-style pattern: field named "driver_data".
 *    Your checker special-cases MemberExpr with field name "driver_data"
 *    and treats variables initialized from it as "maybe NULL".
 */

struct device_id {
    void *driver_data;
};

/*
 * 5a. BAD: initialize from id->driver_data and dereference without check.
 *     NPDChecker should report a warning at "return *p".
 */
int test_bad_metadata(struct device_id *id) {
    int *p = id->driver_data;      // tracked as "maybe NULL" by NPDChecker
    return *p;                     // unchecked dereference
}

/*
 * 5b. GOOD: same as above but with a proper NULL check first.
 *     NPDChecker should NOT report a warning at "return *p".
 */
int test_good_metadata(struct device_id *id) {
    int *p = id->driver_data;      // maybe NULL
    if (!p) {
        return -1;                 // guard
    }
    return *p;                     // safe
}

/*
 * 6. GOOD: completely unrelated pointer that is never tracked by the checker.
 *    No malloc/driver_data/etc.; NPDChecker should stay silent.
 */
int test_untracked_pointer(void) {
    int local = 123;
    int *p = &local;               // not from malloc or driver_data
    return *p;                     // safe & untracked by NPDChecker
}
