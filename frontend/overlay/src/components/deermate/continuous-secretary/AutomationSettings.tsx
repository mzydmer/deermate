"use client";
import Link from "next/link";

import { dmCopy } from "@/components/deermate/i18n/copy";
import { ErrorBanner, Skeleton } from "@/components/deermate/ui";
import {
  Button,
  Disclosure,
  DisclosureTrigger,
  Field,
  Heading,
  Select,
  StatusBadge,
  Text,
  Textarea,
} from "@/components/deermate/ui";

import { type SecretaryController } from "./controller";
import { str } from "./model";
export function AutomationSettings({
  zh,
  config,
  busy,
  readUnavailable,
  mutate,
  sources,
  rules,
  instruction,
  project,
  grant,
  setInstruction,
  decisions,
}: Pick<
  SecretaryController,
  | "zh"
  | "config"
  | "busy"
  | "readUnavailable"
  | "mutate"
  | "sources"
  | "rules"
  | "instruction"
  | "project"
  | "grant"
  | "setInstruction"
  | "decisions"
>) {
  return (
    <Disclosure
      data-testid="attention-management"
      className="dm-attention-management"
    >
      <DisclosureTrigger>
        {dmCopy(zh, "continuous-secretary.github.source.rules.70c5d5")}
      </DisclosureTrigger>
      {config.data && (
        <Field data-testid="continuous-budget" className="dm-continuous-budget">
          {dmCopy(
            zh,
            "continuous-secretary.automatic.execution.limit.day.377816",
          )}
          <Select
            value={Number(config.data.config.data.native_budget ?? 0)}
            disabled={busy || readUnavailable}
            onChange={(e) =>
              void mutate("continuous-config", "PATCH", {
                enabled: config.data.config.data.enabled === true,
                native_budget: Number(e.target.value),
                expected_revision: config.data.config.revision,
              })
            }
          >
            {[0, 1, 2].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </Select>
        </Field>
      )}
      <Text as="p" size="caption" tone="muted" className="">
        {dmCopy(
          zh,
          "continuous-secretary.enable.source.observation.and.automatic.work.sep.c581d4",
        )}
      </Text>
      <Link href="/admin/agents">
        {dmCopy(
          zh,
          "continuous-secretary.manage.device.project.authorization.e9cb06",
        )}
      </Link>

      {sources.isError && (
        <ErrorBanner role="alert">
          {dmCopy(zh, "continuous-secretary.source.unavailable.751fb3")}
        </ErrorBanner>
      )}
      {sources.isPending && (
        <Skeleton
          label={dmCopy(zh, "continuous-secretary.loading.source..b52882")}
        />
      )}
      {rules.isError && (
        <ErrorBanner role="alert">
          {dmCopy(
            zh,
            "continuous-secretary.rules.unavailable.displayed.rules.may.be.stale..4a34e3",
          )}
        </ErrorBanner>
      )}
      {rules.isPending && (
        <Skeleton
          label={dmCopy(zh, "continuous-secretary.loading.rules..14da32")}
        />
      )}
      {sources.data?.items.map((src) => (
        <div key={src.id}>
          <p>
            {str(src, "configured_repository") ||
              str(src, "repository") ||
              dmCopy(
                zh,
                "continuous-secretary.no.repository.configured.db03a8",
              )}{" "}
            · <StatusBadge domain="continuous" status={src.state} />
          </p>
          <Text as="p" size="caption" tone="muted" className="">
            {dmCopy(
              zh,
              "continuous-secretary.read.only.one.repository.initial.poll.establishe.19ec76",
            )}
          </Text>
          {str(src, "error") && (
            <ErrorBanner role="alert">{str(src, "error")}</ErrorBanner>
          )}
          <Button
            variant="ghost"
            size="sm"
            type="button"
            disabled={
              busy ||
              readUnavailable ||
              sources.isError ||
              !config.data?.github_configured
            }
            onClick={() =>
              void mutate(`event-sources/${src.id}`, "PATCH", {
                enabled:
                  src.state !== "enabled" ||
                  config.data?.config.data.enabled !== true,
                expected_revision: src.revision,
              })
            }
          >
            {src.state === "enabled" &&
            config.data?.config.data.enabled === true
              ? dmCopy(zh, "continuous-secretary.disable.source.50f23c")
              : dmCopy(zh, "continuous-secretary.enable.source.3e8277")}
          </Button>
        </div>
      ))}
      <form
        data-testid="continuous-form"
        className="dm-continuous-form"
        onSubmit={(e) => {
          e.preventDefault();
          void mutate(
            "automation-rules",
            "POST",
            {
              source_id: "github",
              mode: "observe",
              instruction,
              project,
              grant_id: grant,
            },
            () => setInstruction(""),
          );
        }}
      >
        <Field>
          {dmCopy(zh, "continuous-secretary.observation.rule.a8b668")}
          <Textarea
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            maxLength={4000}
            placeholder={dmCopy(
              zh,
              "continuous-secretary.for.example.follow.login.and.session.recovery.is.ae6966",
            )}
            required
          />
        </Field>
        <Button
          variant="primary"
          type="submit"
          disabled={busy || readUnavailable || sources.isError || rules.isError}
        >
          {dmCopy(zh, "continuous-secretary.add.observe.rule.3d5dcd")}
        </Button>
      </form>
      <ul data-testid="focus-list" className="dm-focus-list">
        {rules.data?.items.map((rule) => (
          <li key={rule.id}>
            <p>{str(rule, "instruction")}</p>
            <Field>
              {dmCopy(zh, "continuous-secretary.mode.58eb81")}
              <Select
                value={rule.state}
                disabled={busy || readUnavailable || rules.isError}
                onChange={(e) =>
                  void mutate(`automation-rules/${rule.id}`, "PATCH", {
                    source_id: "github",
                    instruction: str(rule, "instruction"),
                    mode: e.target.value,
                    project: str(rule, "project"),
                    grant_id: str(rule, "grant_id"),
                    native_budget: e.target.value === "auto" ? 1 : 0,
                    expected_revision: rule.revision,
                  })
                }
              >
                <option value="off">off</option>
                <option value="observe">observe</option>
                <option
                  value="auto"
                  disabled={
                    !str(rule, "project") ||
                    !str(rule, "grant_id") ||
                    Number(config.data?.config.data.native_budget ?? 0) === 0
                  }
                >
                  auto · 1 / UTC day
                </option>
              </Select>
            </Field>
          </li>
        ))}
      </ul>
      <Heading level={3}>
        {dmCopy(zh, "continuous-secretary.suggestions.d36854")}
      </Heading>
      {decisions.isError && (
        <ErrorBanner role="alert">
          {dmCopy(zh, "continuous-secretary.suggestions.unavailable.add6ae")}
        </ErrorBanner>
      )}
      {decisions.isPending && (
        <Skeleton
          label={dmCopy(zh, "continuous-secretary.loading.suggestions..8c3e42")}
        />
      )}
      {decisions.isSuccess &&
        !decisions.data.items.some((v) => v.state === "suggested") && (
          <Text as="p" tone="muted" className="">
            {dmCopy(
              zh,
              "continuous-secretary.no.pending.suggestions.configure.a.source.and.ob.dac42f",
            )}
          </Text>
        )}
      <ul data-testid="focus-list" className="dm-focus-list">
        {decisions.data?.items
          .filter((v) => v.state === "suggested")
          .map((d) => (
            <li key={d.id}>
              <p>{str(d, "title")}</p>
              <Text as="p" size="caption" className="">
                {str(d, "goal")}
              </Text>
              <Text as="p" size="caption" tone="muted" className="">
                {str(d, "rationale")}
              </Text>
              <div data-testid="focus-actions" className="dm-focus-actions">
                {["accept", "ignore"].map((action) => (
                  <Button
                    variant="ghost"
                    size="sm"
                    type="button"
                    key={action}
                    disabled={
                      busy ||
                      readUnavailable ||
                      decisions.isError ||
                      (action === "accept" &&
                        ((!project && !str(d, "project")) ||
                          (!grant && !str(d, "grant_id"))))
                    }
                    onClick={() =>
                      void mutate(`agent-decisions/${d.id}/actions`, "POST", {
                        action,
                        expected_revision: d.revision,
                        project,
                        grant_id: grant,
                      })
                    }
                  >
                    {action === "accept"
                      ? dmCopy(zh, "continuous-secretary.accept.execute.fa4888")
                      : dmCopy(zh, "continuous-secretary.ignore.bc67d4")}
                  </Button>
                ))}
              </div>
            </li>
          ))}
      </ul>
    </Disclosure>
  );
}
