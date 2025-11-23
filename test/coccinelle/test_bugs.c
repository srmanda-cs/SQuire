// File: test_bugs.c
#include <stdlib.h>

// A function with a bug
void function_with_bug()
{
    int *ptr;
    ptr = malloc(sizeof(int));
    *ptr = 100; // UNSAFE: We're using ptr without checking if it is NULL.
}

// A function without a bug
void function_without_bug()
{
    int *ptr;
    ptr = malloc(sizeof(int));
    if (ptr != NULL)
    {
        *ptr = 200; // SAFE: We're using ptr after checking it is not NULL.
    }
}

// If the script is working as intended, then we should:
// A. Either see a less than 100 percent pass
// Or B. output the exact lines where this rule may have been violated.