# Examples

## Normal

Input: directory containing recipe JSON, run log, measurement CSV, and note text.

Output: 4 imported files, raw artifacts, recipe/run/measurement records, one experience candidate.

## Missing

Input file has unknown extension.

Output: archive or report unsupported according to project policy; do not silently skip.

## Refusal

Input asks to overwrite original logs after parsing.

Output: refuse; originals must remain unchanged.
