# Status v2

`status.v2.yaml` is the active, compact status projection. It stores only each Story's
implementation state, verification state, and the reason external checks were not run.
Git history and the final integration CI run provide history; evidence bodies and source
copies are not duplicated here.

`changes/st-0005/**`, historical worklogs, debt logs, and completion-evidence documents
remain available as archive material. They are not workflow authority and do not need to
be updated during normal development.
