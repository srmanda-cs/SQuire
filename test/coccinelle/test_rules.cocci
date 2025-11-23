// ============================================================
// Coccinelle semantic patch: unsafe_malloc_use
// ------------------------------------------------------------
// Goal:
//   Detect pointer variables that receive memory from malloc()
//   and are dereferenced later without checking if they are NULL.
//
//   This does NOT modify code, it only reports findings.
// ============================================================


@unsafe_malloc_use@

// ------------------------------------------------------------
// Metavariables
// ------------------------------------------------------------
// - "identifier p;" means we’re searching for a C identifier,
//   such as a variable name (example: ptr).
//
// - "position pos;" means we’re capturing the exact location
//   in the source code where a certain match occurs,
//   so we can later print the line number.
identifier p;
position pos;

@@

// ------------------------------------------------------------
// Matching pattern
// ------------------------------------------------------------
//
// 1. Match a line where a variable (p) is assigned the result
//    of malloc(). This binds p to that specific variable.
//
p = malloc(...);

//
// 2. Allow any number of statements between the malloc()
//    and the later usage we care about. The "..." means
//    “any code” and "when any" means there are no restrictions.
//
... when any

//
// 3. Look for a dereference of that same variable p.
//    The pattern *p matches a dereference expression,
//    and @pos tells Coccinelle to record its source location.
//
(
    *p@pos
)

//
// 4. Avoid false positives: don’t consider dereferences
//    that occur inside an if-condition checking p != NULL.
//
//    That means, skip any dereference if Coccinelle finds
//    it is inside code guarded like:
//
//       if (p != NULL) { ... }
//
//    The condition "when != if (p != NULL) { ... }"
//    literally says: “This match only holds when it is NOT
//    inside such an if statement.”
//
... when != if (p != NULL) { ... }


// ------------------------------------------------------------
// Reporting section
// ------------------------------------------------------------
//
// Coccinelle can run Python code after matches are found.
// This section prints a message for each match.
// ------------------------------------------------------------
@script:python@

// Pass the metavariables from the matching rule above
// into the Python section so we can use them here.
//   - "p" is the pointer variable name.
//   - "pos" stores location info (line, column, etc).
p << unsafe_malloc_use.p;
pos << unsafe_malloc_use.pos;

@@

// Print a message for each unsafe usage found.
//   pos[0].line gives the line number in the original file.
//   Example console output:
//     Possible unsafe use of malloc'ed variable: ptr at line 7
print("Possible unsafe use of malloc'ed variable:", p, "at line", pos[0].line)