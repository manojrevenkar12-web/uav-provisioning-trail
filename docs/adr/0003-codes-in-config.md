# 3. Failure handling is a vocabulary in config, not code

Status: accepted

What a failure means, who owns it, how many attempts it gets and what the operator does first changes as the
line learns. Every code lives in `config/codes.yaml`: label, owner, retry budget, recovery, restart step. The
analysis groups by the same codes, the console names them from the same file, and a test fails if any step
raises a code the file does not know.
