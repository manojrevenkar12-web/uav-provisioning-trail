# 5. The analysis is measured on shifts written blind

Status: accepted

The dev shift and the analysis share an author. Held-out shifts are written by an agent that reads only
`heldout/WRITING_CAMPAIGNS.md`. `uavsim heldout <set>` records the first run once; CI fails if it changes. A set
studied to change the analysis is marked `regression` and replaced by a new blind set. v1: 18 of 20 causes named,
2 false alarms, on its first run.
