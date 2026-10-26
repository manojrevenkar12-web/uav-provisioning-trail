# 2. The trail records the intent before the action

Status: accepted

A station can die in the middle of a step. If only results were recorded, a module that was half-flashed or a
burn that may have happened would leave no trace. Each step appends an `intent` event and commits it locally
before acting. A missing result is then evidence of an interruption, and the next run restarts that step instead
of assuming it. The fuse guard requires the intent to be stored before it allows the burn.
