"use client";
import { useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import { dmCopy } from "@/components/deermate/i18n/copy";
import { ErrorBanner } from "@/components/deermate/ui";
import { Button, Field, Input, Switch, Text } from "@/components/deermate/ui";

import { invalidateHome, personalAPI, type Profile } from "./model";
export function ProfileForm({
  profile,
  zh,
}: {
  profile: Profile;
  zh: boolean;
}) {
  const cache = useQueryClient();
  const [name, setName] = useState(profile.display_name);
  const [zone, setZone] = useState(profile.timezone);
  const [enabled, setEnabled] = useState(profile.memory_enabled);
  const [capture, setCapture] = useState(profile.auto_capture_enabled);
  const [suggest, setSuggest] = useState(profile.proactive_enabled);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState("");
  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFeedback("");
    try {
      await personalAPI<Profile>("personal-profile", profile.owner, {
        method: "PATCH",
        body: JSON.stringify({
          display_name: name.trim(),
          timezone: zone.trim(),
          memory_enabled: enabled,
          auto_capture_enabled: capture,
          proactive_enabled: suggest,
          expected_revision: profile.revision,
        }),
      });
      invalidateHome(cache, profile.owner);
      await cache.invalidateQueries({
        queryKey: ["deermate", "personal-profile", profile.owner],
      });
      await cache.invalidateQueries({
        queryKey: ["deermate", "personal-memory", profile.owner],
      });
    } catch {
      setFeedback(
        dmCopy(
          zh,
          "personal-memory.settings.were.not.saved.check.the.timezone.or.re.3a4648",
        ),
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <form
      data-testid="memory-form"
      className="dm-memory-form"
      onSubmit={(event) => void save(event)}
    >
      <Field>
        {dmCopy(zh, "personal-memory.what.should.i.call.you..457d67")}
        <Input
          value={name}
          maxLength={80}
          disabled={busy}
          onChange={(e) => setName(e.target.value)}
        />
      </Field>
      <Field>
        {dmCopy(zh, "personal-memory.timezone.571d45")}
        <Input
          value={zone}
          maxLength={80}
          disabled={busy}
          onChange={(e) => setZone(e.target.value)}
          placeholder="Asia/Shanghai"
        />
      </Field>
      <Button
        variant="secondary"
        type="button"
        onClick={() =>
          setZone(Intl.DateTimeFormat().resolvedOptions().timeZone)
        }
        disabled={busy}
      >
        {dmCopy(zh, "personal-memory.use.device.timezone.31d11f")}
      </Button>
      <Field data-testid="memory-check" className="dm-memory-check">
        <Switch
          checked={enabled}
          disabled={busy}
          onCheckedChange={setEnabled}
        />
        {dmCopy(zh, "personal-memory.use.saved.memory.in.answers.3833f0")}
      </Field>
      <Text as="p" tone="muted" className="">
        {dmCopy(
          zh,
          "personal-memory.turning.this.off.excludes.saved.facts.from.answe.7f811f",
        )}
      </Text>
      <Field data-testid="memory-check" className="dm-memory-check">
        <Switch
          checked={capture}
          disabled={busy}
          onCheckedChange={setCapture}
        />
        {dmCopy(
          zh,
          "personal-memory.automatically.capture.preferences.and.requiremen.339be2",
        )}
      </Field>
      <Text as="p" tone="muted" className="">
        {dmCopy(
          zh,
          "personal-memory.no.special.phrase.is.required.authentication.sec.85765d",
        )}
      </Text>
      <Field data-testid="memory-check" className="dm-memory-check">
        <Switch
          checked={suggest}
          disabled={busy || !enabled}
          onCheckedChange={setSuggest}
        />
        {dmCopy(zh, "personal-memory.suggest.topics.from.saved.goals.5359f1")}
      </Field>
      <Text as="p" tone="muted" className="">
        {dmCopy(
          zh,
          "personal-memory.suggests.questions.from.your.valid.saved.goals.a.4b454c",
        )}
      </Text>
      <Button loading={busy} variant="primary" type="submit" disabled={busy}>
        {busy
          ? dmCopy(zh, "personal-memory.saving..4c8592")
          : dmCopy(zh, "personal-memory.save.personal.settings.05031f")}
      </Button>
      {feedback && <ErrorBanner role="alert">{feedback}</ErrorBanner>}
    </form>
  );
}
