# F0c Component Records

F0c is complete only when it includes one current record for Trace-Lite,
Trace, and trace-bench plus a coordinator synthesis. These starter files are
not final evidence; the assigned worker refreshes dates, commands, hashes,
dirty-path classifications, and source anchors without altering the source
trees.

Use REPOSITORY_STATE_TEMPLATE.json for the machine-readable record and retain
a readable companion note for each component.

Required common fields:

1. absolute root;
2. Git commit/branch or explicit unversioned status;
3. timestamp and commands used;
4. protected tracked/untracked/ignored path classifications;
5. source inventory include/exclude rules;
6. integration/import/configuration boundary;
7. safe clean mutation base or explicit absence;
8. stale packet matrix;
9. claim boundary.

Never clean, stage, reset, stash, reformat, relocate, or commit user-owned
state during F0c.
