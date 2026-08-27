# Code Intelligence

This project has the pyright LSP configured for both editors and the Claude Code harness. Prefer LSP operations over text search whenever you are navigating code by symbol rather than by string.

## Decision rule

If you know a **symbol name** (class, function, method, variable) → use LSP.
If you are searching for a **text pattern** (comment, docstring, string literal, config value, TODO marker) → use Grep/Glob.

Reading an entire file to learn its shape is almost always the wrong move — `documentSymbol` is faster, cheaper, and does not bloat context.

## Reflex → LSP substitution table

If you catch yourself about to run the query on the left, stop and use the operation on the right instead:

| Intent                                                           | Wrong reflex            | Correct LSP call                                                          |
| ---------------------------------------------------------------- | ----------------------- | ------------------------------------------------------------------------- |
| "Where is `X` defined?"                                          | `Grep "class X\|def X"` | `goToDefinition` (from a usage site) or `workspaceSymbol` (from anywhere) |
| "Where is `X` used / called?"                                    | `Grep "X("`             | `findReferences`, or `incomingCalls` for function call sites              |
| "What is the type / signature / docstring of `X`?"               | Read the whole file     | `hover` on any occurrence                                                 |
| "What classes, methods, or top-level symbols live in this file?" | Read the whole file     | `documentSymbol`                                                          |
| "Who implements this interface / abstract method?"               | `Grep`                  | `goToImplementation`                                                      |
| "What does this function call internally?"                       | Read + manual trace     | `outgoingCalls`                                                           |

## Rename / signature-change gate

Before any rename or signature change, run `findReferences` on the symbol and inspect every call site. Skipping this is how silent breakage ships.

## Diagnostics

There is no separate "diagnostics" LSP call. Diagnostics are delivered to you automatically as `<new-diagnostics>` system reminders tied to the files you just touched. Treat any reported pyright or ruff error as a blocker — fix it before the next edit, not at the end of the session.
