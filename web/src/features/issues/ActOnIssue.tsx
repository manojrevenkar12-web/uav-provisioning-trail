import { type FormEvent, useState } from "react";

import type { Issue } from "../../shared/api/types";
import { canActOnIssues, useSession } from "../../shared/lib/useSession";
import { Button, Notice } from "../../shared/ui";
import { Dialog } from "../../shared/ui/Dialog";
import { Field } from "../../shared/ui/Field";
import { Segmented } from "../../shared/ui/Segmented";
import { OWNER } from "../../shared/theme/tokens";
import { type ActionInput, useIssueAction } from "./api";
import styles from "./Issues.module.css";

const ACTIONS: { value: ActionInput["action"]; label: string; done: string }[] = [
  { value: "acknowledge", label: "Acknowledge", done: "Acknowledged" },
  { value: "fixed", label: "Mark fixed", done: "Marked fixed" },
  { value: "not_a_problem", label: "Not a problem", done: "Closed as not a problem" },
  { value: "note", label: "Add a note", done: "Note added" },
];
const MIN_NOTE = 3;

/** Turns an issue into work: who owns it, what was done, and from when a fix should show in the numbers. */
export function ActOnIssue({ issue }: { issue: Issue }) {
  const { role, actor } = useSession();
  const [open, setOpen] = useState(false);
  const [action, setAction] = useState<ActionInput["action"]>("acknowledge");
  const [note, setNote] = useState("");
  const [owner, setOwner] = useState(issue.owner);
  const [when, setWhen] = useState("");
  const [tried, setTried] = useState(false);
  const mutation = useIssueAction(issue.key);
  const tooShort = note.trim().length < MIN_NOTE;

  const close = () => {
    setOpen(false);
    setTried(false);
    setNote("");
    mutation.reset();
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTried(true);
    if (tooShort) return;
    mutation.mutate({
      action,
      note: note.trim(),
      owner,
      effective_at: action === "fixed" && when ? new Date(when).toISOString() : undefined,
    });
  };
  const done = ACTIONS.find((a) => a.value === mutation.variables?.action)?.done;

  return (
    <>
      <Button onClick={() => setOpen(true)}>Act on this</Button>
      <Dialog open={open} title={issue.label} onClose={close}>
        {mutation.isSuccess ? (
          <>
            <Notice>
              {done} by {mutation.data.actor || actor}.
            </Notice>
            <Button variant="primary" onClick={close}>
              Close
            </Button>
          </>
        ) : !canActOnIssues(role) ? (
          <>
            <Notice>
              Operators see the issues; the line lead, engineering or quality act on them. Switch the role at
              the top.
            </Notice>
            <Button onClick={close}>Close</Button>
          </>
        ) : (
          <form className={styles.form} onSubmit={submit} noValidate>
            <Segmented label="What happened" options={ACTIONS} value={action} onChange={setAction} />
            <Field label="Owner">
              {(p) => (
                <select {...p} value={owner} onChange={(e) => setOwner(e.target.value)}>
                  {Object.entries(OWNER).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              )}
            </Field>
            {action === "fixed" && (
              <Field
                label="Fixed from"
                hint="When the fix took effect on the line. Empty: now. Its effect is measured from then."
              >
                {(p) => (
                  <input
                    {...p}
                    type="datetime-local"
                    value={when}
                    onChange={(e) => setWhen(e.target.value)}
                  />
                )}
              </Field>
            )}
            <Field
              label="Note"
              hint="What was found or done, for whoever looks next."
              error={tried && tooShort ? `Write at least ${MIN_NOTE} characters.` : mutation.error?.message}
            >
              {(p) => (
                <textarea {...p} value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} />
              )}
            </Field>
            <div className={styles.buttons}>
              <Button type="submit" variant="primary" busy={mutation.isPending}>
                {ACTIONS.find((a) => a.value === action)?.label}
              </Button>
              <Button variant="quiet" onClick={close}>
                Cancel
              </Button>
            </div>
          </form>
        )}
      </Dialog>
    </>
  );
}
