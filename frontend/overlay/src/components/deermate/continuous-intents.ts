type Body = Record<string, unknown>;

export type ContinuousIntent = {
  key: string;
  body: Body & { operation_id: string };
};

/** Keep the first request after an ambiguous reply, even if its view advanced. */
export class ContinuousIntents {
  private pending = new Map<string, ContinuousIntent>();

  begin(
    path: string,
    method: string,
    body: object,
    createId: () => string = () => crypto.randomUUID(),
  ): ContinuousIntent {
    const meaning: Body = { ...body };
    delete meaning.expected_revision;
    if (
      /^work-orders\/[^/]+\/actions$/.test(path) &&
      ["execute", "followup"].includes(String(meaning.action))
    ) {
      meaning.action = "run";
    }
    const key = JSON.stringify([path, method, meaning]);
    const previous = this.pending.get(key);
    if (previous) return previous;
    const intent = {
      key,
      body: { ...body, operation_id: createId() },
    };
    this.pending.set(key, intent);
    return intent;
  }

  confirmed(intent: ContinuousIntent) {
    if (this.pending.get(intent.key) === intent)
      this.pending.delete(intent.key);
  }

  rejected(intent: ContinuousIntent, status?: number) {
    // A missing reply/5xx cannot establish that the first request was refused.
    if (status !== undefined && status >= 400 && status < 500) {
      this.confirmed(intent);
    }
  }
}
