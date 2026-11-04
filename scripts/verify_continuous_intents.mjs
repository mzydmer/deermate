// Node 24+: offline regression for ambiguous UI replies; no browser or provider.
import assert from "node:assert/strict";
import { ContinuousIntents } from "../frontend/overlay/src/components/deermate/continuous-intents.ts";

const intents = new ContinuousIntents();
let count = 0;
const createId = () => `operation-${++count}`;
const path = "work-orders/work-a/actions";
const first = intents.begin(
  path,
  "POST",
  {
    action: "execute",
    text: "Fix the bounded task",
    expected_revision: 1,
  },
  createId,
);
intents.rejected(first, 503);
const afterProjection = intents.begin(
  path,
  "POST",
  {
    action: "followup",
    text: "Fix the bounded task",
    expected_revision: 9,
  },
  createId,
);
assert.strictEqual(afterProjection, first);
assert.deepEqual(afterProjection.body, {
  action: "execute",
  text: "Fix the bounded task",
  expected_revision: 1,
  operation_id: "operation-1",
});
intents.rejected(first);
assert.strictEqual(
  intents.begin(
    path,
    "POST",
    {
      action: "followup",
      text: "Fix the bounded task",
      expected_revision: 10,
    },
    createId,
  ),
  first,
);
assert.equal(count, 1);

const otherWork = intents.begin(
  "work-orders/work-b/actions",
  "POST",
  {
    action: "execute",
    text: "Fix the bounded task",
    expected_revision: 1,
  },
  createId,
);
assert.notEqual(otherWork.body.operation_id, first.body.operation_id);
const otherQuestion = intents.begin(
  path,
  "POST",
  {
    action: "followup",
    text: "Check the independent tests",
    expected_revision: 10,
  },
  createId,
);
assert.notEqual(otherQuestion.body.operation_id, first.body.operation_id);

intents.rejected(first, 409);
const afterKnownRejection = intents.begin(
  path,
  "POST",
  {
    action: "followup",
    text: "Fix the bounded task",
    expected_revision: 12,
  },
  createId,
);
assert.notEqual(afterKnownRejection.body.operation_id, first.body.operation_id);
assert.equal(afterKnownRejection.body.expected_revision, 12);
intents.confirmed(afterKnownRejection);
const afterConfirmation = intents.begin(
  path,
  "POST",
  {
    action: "followup",
    text: "Fix the bounded task",
    expected_revision: 15,
  },
  createId,
);
assert.notEqual(
  afterConfirmation.body.operation_id,
  afterKnownRejection.body.operation_id,
);

// A stale acknowledgement cannot clear a newer pending request.
intents.confirmed(afterKnownRejection);
assert.strictEqual(
  intents.begin(
    path,
    "POST",
    {
      action: "followup",
      text: "Fix the bounded task",
      expected_revision: 16,
    },
    createId,
  ),
  afterConfirmation,
);
const newOwnerInstance = new ContinuousIntents();
assert.notEqual(
  newOwnerInstance.begin(
    path,
    "POST",
    {
      action: "followup",
      text: "Fix the bounded task",
      expected_revision: 1,
    },
    createId,
  ).body.operation_id,
  afterConfirmation.body.operation_id,
);
console.log("Continuous UI intent recovery: 8 regression scenarios passed");
