"use client";

import { dmCopy } from "@/components/deermate/i18n/copy";
import {
  Button,
  Disclosure,
  DisclosureTrigger,
  Field,
  Input,
  Textarea,
} from "@/components/deermate/ui";

import { type SecretaryController } from "./controller";
export function NewWorkForm({
  zh,
  mutate,
  goal,
  project,
  grant,
  setGoal,
  setProject,
  setGrant,
  busy,
  readUnavailable,
}: Pick<
  SecretaryController,
  | "zh"
  | "mutate"
  | "goal"
  | "project"
  | "grant"
  | "setGoal"
  | "setProject"
  | "setGrant"
  | "busy"
  | "readUnavailable"
>) {
  return (
    <Disclosure
      data-testid="attention-management"
      className="dm-attention-management"
    >
      <DisclosureTrigger>
        {dmCopy(zh, "continuous-secretary.create.work.directly.d2ef86")}
      </DisclosureTrigger>
      <form
        data-testid="continuous-form"
        className="dm-continuous-form"
        onSubmit={(e) => {
          e.preventDefault();
          void mutate(
            "work-orders",
            "POST",
            { goal, project, grant_id: grant },
            () => setGoal(""),
          );
        }}
      >
        <Field>
          {dmCopy(zh, "continuous-secretary.goal.167257")}
          <Textarea
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            maxLength={8000}
            required
          />
        </Field>
        <div data-testid="continuous-fields" className="dm-continuous-fields">
          <Field>
            {dmCopy(zh, "continuous-secretary.registered.project.id.48c78e")}
            <Input
              value={project}
              onChange={(e) => setProject(e.target.value)}
              maxLength={100}
              required
            />
          </Field>
          <Field>
            {dmCopy(zh, "continuous-secretary.device.grant.id.905a96")}
            <Input
              value={grant}
              onChange={(e) => setGrant(e.target.value)}
              maxLength={128}
              required
            />
          </Field>
        </div>
        <Button
          variant="primary"
          type="submit"
          disabled={busy || readUnavailable}
        >
          {dmCopy(zh, "continuous-secretary.create.work.c6c351")}
        </Button>
      </form>
    </Disclosure>
  );
}
