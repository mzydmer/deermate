import { afterEach, expect, rs, test } from "@rstest/core";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

import {
  Button,
  Card,
  Checkbox,
  DataTable,
  Dialog,
  DialogContent,
  DialogTitle,
  DialogTrigger,
  Disclosure,
  DisclosureTrigger,
  Field,
  IconButton,
  Input,
  SegmentedControl,
  Select,
  StatusBadge,
  Textarea,
} from "@/components/deermate/ui";
rs.mock("@/core/i18n/hooks", () => ({ useI18n: () => ({ locale: "en-US" }) }));
afterEach(cleanup);
test("button tone replaces variant text, sizes are explicit, loading blocks activation", () => {
  const click = rs.fn();
  render(
    <Button variant="primary" tone="danger" size="sm" loading onClick={click}>
      Save
    </Button>,
  );
  const b = screen.getByRole("button");
  expect(b.className).toContain("text-error-deep");
  expect(b.className).not.toContain("text-on-primary");
  expect(b.getAttribute("data-size")).toBe("sm");
  expect(b.getAttribute("aria-busy")).toBe("true");
  expect((b as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(b);
  expect(click).not.toHaveBeenCalled();
  expect(b.textContent).toContain("Save");
});
test("asChild preserves link semantics and prevents disabled navigation", () => {
  const click = rs.fn();
  render(
    <Button asChild disabled onClick={click}>
      <a href="https://example.test/docs">Docs</a>
    </Button>,
  );
  const link = screen.getByRole("link");
  expect(link.getAttribute("aria-disabled")).toBe("true");
  fireEvent.click(link);
  expect(click).not.toHaveBeenCalled();
});
test("icon action has a required accessible name", () => {
  render(<IconButton label="Add item" icon={<span />} />);
  expect(screen.getByRole("button", { name: "Add item" })).toBeTruthy();
});
test("field preserves caller control and links errors", () => {
  render(
    <Field label="Project" hint="Short name" error="Required">
      <Input defaultValue="hello" />
    </Field>,
  );
  const input = screen.getByLabelText("Project");
  expect((input as HTMLInputElement).value).toBe("hello");
  expect(input.getAttribute("aria-invalid")).toBe("true");
  expect(input.getAttribute("aria-describedby")?.split(" ")).toContain(
    screen.getByRole("alert").id,
  );
  expect(input.getAttribute("aria-describedby")?.split(" ")).toHaveLength(2);
});
test("textarea keeps controlled changes and removes native resize affordance", () => {
  const change = rs.fn();
  render(<Textarea aria-label="Message" onChange={change} />);
  const input = screen.getByRole("textbox");
  fireEvent.change(input, { target: { value: "A line" } });
  expect(change).toHaveBeenCalled();
  expect((input as HTMLTextAreaElement).style.resize).toBe("none");
});
test("checkbox retains native keyboard and form semantics", () => {
  render(<Checkbox aria-label="Remember" defaultChecked />);
  expect((screen.getByRole("checkbox")).checked).toBe(true);
});
test("status map distinguishes unverified execution, failed validation and unknown", () => {
  render(
    <>
      <StatusBadge status="completed_unverified" />
      <StatusBadge domain="validation" status="failed" />
      <StatusBadge status="future_state" />
    </>,
  );
  expect(screen.getByText("Ended · unverified")).toBeTruthy();
  expect(screen.getByText("Validation failed")).toBeTruthy();
  expect(screen.getByText("future_state")).toBeTruthy();
});
test("table has an independent region and explicit error/empty/loading states", () => {
  const props = {
    columns: [{ key: "id", label: "ID", render: (r: { id: string }) => r.id }],
    rowKey: (r: { id: string }) => r.id,
  };
  const { rerender } = render(
    <DataTable {...props} rows={[]} empty="Nothing here" />,
  );
  expect(screen.getByText("Nothing here")).toBeTruthy();
  rerender(<DataTable {...props} rows={[]} loading />);
  expect(screen.getByRole("status")).toBeTruthy();
  rerender(<DataTable {...props} rows={[]} error="Offline" />);
  expect(screen.getByRole("alert").textContent).toContain("Offline");
  rerender(<DataTable {...props} rows={[{ id: "one" }]} />);
  expect(screen.getByRole("region")).toBeTruthy();
  expect(screen.getByRole("columnheader")).toBeTruthy();
});
test("disclosure exposes expanded state without a native triangle", async () => {
  render(
    <Disclosure>
      <DisclosureTrigger>More</DisclosureTrigger>
      <p>Inside</p>
    </Disclosure>,
  );
  const trigger = screen.getByRole("button", { name: "More" });
  expect(trigger.getAttribute("aria-expanded")).toBe("false");
  fireEvent.click(trigger);
  await waitFor(() =>
    expect(trigger.getAttribute("aria-expanded")).toBe("true"),
  );
  expect(document.querySelector("details")).toBeNull();
});
test("dialog restores trigger focus after Escape", async () => {
  render(
    <Dialog>
      <DialogTrigger asChild>
        <Button>Open</Button>
      </DialogTrigger>
      <DialogContent aria-describedby={undefined}>
        <DialogTitle>Details</DialogTitle>
      </DialogContent>
    </Dialog>,
  );
  const trigger = screen.getByRole("button", { name: "Open" });
  trigger.focus();
  fireEvent.click(trigger);
  await screen.findByRole("dialog");
  fireEvent.keyDown(document.activeElement!, { key: "Escape" });
  await waitFor(() => expect(document.activeElement).toBe(trigger));
});

test("select is controlled and exposes a named combobox", () => {
  const change = rs.fn();
  render(
    <Select aria-label="Source" value="one" onChange={change}>
      <option value="one">One</option>
      <option value="two">Two</option>
    </Select>,
  );
  const trigger = screen.getByRole("combobox", { name: "Source" });
  expect(trigger.textContent).toContain("One");
  expect(trigger.getAttribute("data-size")).toBe("md");
});

test("surface recipes expose compact card, readable heading and form controls", () => {
  render(
    <>
      <Card variant="compact">Content</Card>
      <Field label="Mode">
        <Input size="lg" />
      </Field>
      <SegmentedControl
        label="View"
        defaultValue="all"
        items={[
          { value: "all", label: "All" },
          { value: "active", label: "Active" },
        ]}
      />
    </>,
  );
  expect(screen.getByText("Content").getAttribute("data-variant")).toBe(
    "compact",
  );
  expect(screen.getByLabelText("Mode").getAttribute("data-size")).toBe("lg");
  expect(
    screen.getByRole("tab", { name: "All" }).getAttribute("aria-selected"),
  ).toBe("true");
  fireEvent.mouseDown(screen.getByRole("tab", { name: "Active" }), {
    button: 0,
    ctrlKey: false,
  });
  expect(
    screen.getByRole("tab", { name: "Active" }).getAttribute("aria-selected"),
  ).toBe("true");
});
