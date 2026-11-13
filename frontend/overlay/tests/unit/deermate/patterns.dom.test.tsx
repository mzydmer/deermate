import { afterEach, expect, rs, test } from "@rstest/core";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { Composer } from "../../../src/components/deermate/patterns/composer";
import {
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Field,
  Input,
  Popover,
  PopoverContent,
  PopoverTrigger,
  Switch,
} from "../../../src/components/deermate/ui";
import {
  SidebarMenuButton,
  SidebarProvider,
} from "../../../src/components/ui/sidebar";

rs.mock("@/core/i18n/hooks", () => ({ useI18n: () => ({ locale: "en-US" }) }));
afterEach(cleanup);
test("composer keeps sending disabled when empty and separates newline from send", () => {
  const send = rs.fn(),
    change = rs.fn();
  const view = render(
    <Composer
      label="Message"
      sendLabel="Send"
      value=""
      onChange={change}
      onSubmit={send}
    />,
  );
  expect(
    screen.getByRole("button", { name: "Send" }).hasAttribute("disabled"),
  ).toBe(true);
  view.rerender(
    <Composer
      label="Message"
      sendLabel="Send"
      value="hello"
      onChange={change}
      onSubmit={send}
    />,
  );
  fireEvent.keyDown(screen.getByRole("textbox"), {
    key: "Enter",
    shiftKey: true,
  });
  expect(send).toHaveBeenCalledTimes(0);
  fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter" });
  expect(send).toHaveBeenCalledTimes(1);
  view.rerender(
    <Composer
      label="Message"
      sendLabel="Send"
      value="hello"
      busy
      onChange={change}
      onSubmit={send}
    />,
  );
  expect(
    screen.getByRole("button", { name: "Send" }).getAttribute("aria-busy"),
  ).toBe("true");
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  expect(send).toHaveBeenCalledTimes(1);
});
test("field honors explicit control ids and describes hint together with error", () => {
  render(
    <Field label="Name" hint="Public" error="Required">
      <Input id="chosen" />
    </Field>,
  );
  const input = screen.getByLabelText("Name");
  expect(input.id).toBe("chosen");
  expect(input.getAttribute("aria-describedby")).toContain("chosen-hint");
  expect(input.getAttribute("aria-describedby")).toContain("chosen-error");
  expect(input.getAttribute("aria-invalid")).toBe("true");
});
test("switch supports keyboard activation with explicit checked state", () => {
  const on = rs.fn();
  render(<Switch aria-label="Capture" checked onCheckedChange={on} />);
  const input = screen.getByRole("switch", { name: "Capture" });
  expect(input.getAttribute("aria-checked")).toBe("true");
  fireEvent.click(input);
  expect(on).toHaveBeenCalledWith(false);
});
test("popover preserves trigger naming and closes with Escape", async () => {
  render(
    <Popover>
      <PopoverTrigger asChild>
        <Button>Inspect</Button>
      </PopoverTrigger>
      <PopoverContent>
        <Button>Done</Button>
      </PopoverContent>
    </Popover>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Inspect" }));
  expect(screen.getByRole("dialog")).toBeTruthy();
  fireEvent.keyDown(screen.getByRole("button", { name: "Done" }), {
    key: "Escape",
  });
  expect(screen.queryByRole("dialog")).toBeNull();
});
test("menu opens by keyboard and exposes actionable items", () => {
  render(
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button>Actions</Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuItem>Inspect</DropdownMenuItem>
        <DropdownMenuItem>Correct</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>,
  );
  fireEvent.keyDown(screen.getByRole("button", { name: "Actions" }), {
    key: "ArrowDown",
  });
  expect(screen.getByRole("menu")).toBeTruthy();
  expect(screen.getAllByRole("menuitem")).toHaveLength(2);
});

test("loading preserves the action label when a caller changes its busy text", () => {
  const view = render(<Button>Save</Button>);
  view.rerender(<Button loading>Saving…</Button>);
  expect(screen.getByRole("button").textContent).toBe("Save");
  view.rerender(<Button>Saved</Button>);
  expect(screen.getByRole("button").textContent).toBe("Saved");
});
test("disabled asChild also blocks a child's own handlers", () => {
  const click = rs.fn();
  render(
    <Button asChild disabled>
      <a href="https://example.test/docs" onClick={click}>
        Docs
      </a>
    </Button>,
  );
  fireEvent.click(screen.getByRole("link"));
  expect(click).not.toHaveBeenCalled();
  expect(screen.getByRole("link").getAttribute("tabindex")).toBe("-1");
});

test("expanded sidebar labels do not create invisible tooltip layers", () => {
  const view = render(
    <SidebarProvider open>
      <SidebarMenuButton tooltip="Assistant">Assistant</SidebarMenuButton>
    </SidebarProvider>,
  );
  expect(
    screen
      .getByRole("button", { name: "Assistant" })
      .hasAttribute("data-state"),
  ).toBe(false);
  view.rerender(
    <SidebarProvider open={false}>
      <SidebarMenuButton tooltip="Assistant">Assistant</SidebarMenuButton>
    </SidebarProvider>,
  );
  expect(
    screen
      .getByRole("button", { name: "Assistant" })
      .getAttribute("data-state"),
  ).toBe("closed");
});
