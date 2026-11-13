"use client";
import { Inbox, Plus } from "lucide-react";

import {
  Avatar,
  Badge,
  Button,
  Card,
  Checkbox,
  Combobox,
  CopyButton,
  DataTable,
  Dialog,
  DialogContent,
  DialogTitle,
  DialogTrigger,
  Disclosure,
  DisclosureTrigger,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Empty,
  ErrorBanner,
  ErrorState,
  Field,
  Heading,
  IconButton,
  Input,
  InputGroup,
  Kbd,
  KeyValue,
  Panel,
  Popover,
  PopoverContent,
  PopoverTrigger,
  RelativeTime,
  SectionHeader,
  SegmentedControl,
  Select,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
  SheetTrigger,
  Skeleton,
  Spinner,
  StatusBadge,
  Switch,
  Text,
  Textarea,
  Toast,
} from "./index";
export function DesignGallery() {
  return (
    <main
      className="grid gap-6 bg-canvas-soft p-6"
      data-testid="design-gallery"
    >
      <Heading level={1}>Component gallery</Heading>
      <Card>
        <SectionHeader icon={Inbox} title="Actions" />
        <div className="flex flex-wrap gap-3">
          {(["primary", "secondary", "ghost", "link", "danger"] as const).map(
            (variant) => (
              <Button key={variant} variant={variant}>
                {variant}
              </Button>
            ),
          )}
          <Button loading>Saving</Button>
          <Button disabled>Disabled</Button>
          {(["sm", "md", "lg"] as const).map((size) => (
            <Button size={size} key={size}>
              {size}
            </Button>
          ))}
          {(["neutral", "muted", "link", "danger"] as const).map((tone) => (
            <Button tone={tone} key={tone}>
              {tone}
            </Button>
          ))}
          <IconButton label="Add" icon={<Plus className="size-4" />} />
        </div>
      </Card>
      <Card>
        <Field label="Name" hint="Required">
          <Input placeholder="Name" />
        </Field>
        <Field label="Invalid" error="Check the name">
          <Input />
        </Field>
        <Field label="Notes">
          <Textarea defaultValue="A long note" />
        </Field>
        <Field label="Choice">
          <Select defaultValue="one">
            <option value="one">One</option>
            <option value="two">Two</option>
          </Select>
        </Field>
        {(["sm", "md", "lg"] as const).map((size) => (
          <Field label={`Input ${size}`} key={size}>
            <Input size={size} />
          </Field>
        ))}
        <InputGroup
          prefix={<Inbox className="size-4" />}
          suffix={<Kbd>⌘ K</Kbd>}
        >
          <Input aria-label="Search group" />
        </InputGroup>
        <Combobox
          label="Search choices"
          defaultValue="one"
          items={[
            { value: "one", label: "One" },
            { value: "two", label: "Two" },
          ]}
        />
        <Checkbox aria-label="Select" />
        <Switch aria-label="Enabled" />
      </Card>
      <Panel>
        <SectionHeader icon={Inbox} title="States" />
        <div className="flex flex-wrap gap-3">
          {Object.keys({
            submitted: 0,
            working: 0,
            input_required: 0,
            completed: 0,
            failed: 0,
            cancelled: 0,
            uncertain: 0,
          }).map((status) => (
            <StatusBadge key={status} status={status} />
          ))}
          <StatusBadge domain="validation" status="passed" />
          <StatusBadge domain="validation" status="failed" />
          <StatusBadge domain="connection" status="expired" />
        </div>
        {(
          ["default", "info", "success", "warning", "danger", "violet"] as const
        ).map((variant) => (
          <Badge key={variant} variant={variant}>
            {variant}
          </Badge>
        ))}
        <StatusBadge domain="work" status="partial" />
        <StatusBadge domain="connection" status="not_checked" />
        <StatusBadge status="future_status" />
        <ErrorState
          title="Could not load"
          detail="Try again when the source is available."
          action={<Button>Retry</Button>}
        />
        <Button onClick={() => Toast("Saved preview")}>Preview toast</Button>
        <CopyButton value="synthetic-identifier" />
        <Popover>
          <PopoverTrigger asChild>
            <Button>Open popover</Button>
          </PopoverTrigger>
          <PopoverContent>Supplementary details</PopoverContent>
        </Popover>
        <Sheet>
          <SheetTrigger asChild>
            <Button>Open sheet</Button>
          </SheetTrigger>
          <SheetContent>
            <SheetTitle>Details</SheetTitle>
            <SheetDescription>Synthetic long-form details</SheetDescription>
            <KeyValue
              label="Path"
              mono
              value={"/workspace/" + "long-segment/".repeat(30)}
            />
          </SheetContent>
        </Sheet>
        <Skeleton />
        <Spinner />
        <Empty title="No records" description="Choose a source to begin." />
        <ErrorBanner onRetry={() => void 0}>Unable to refresh</ErrorBanner>
      </Panel>
      <Card>
        <SegmentedControl
          label="Filter"
          items={[
            { value: "all", label: "All", count: 3 },
            { value: "active", label: "Active", count: 1 },
          ]}
        />
        <KeyValue label="Path" value="src/components/deermate/ui" mono copy />
        <RelativeTime value="2026-11-12T12:00:00Z" />
        <Kbd>Esc</Kbd>
        <Avatar name="Fixture" />
        <Disclosure>
          <DisclosureTrigger>More</DisclosureTrigger>
          <Text>Details</Text>
        </Disclosure>
        <Dialog>
          <DialogTrigger asChild>
            <Button>Open dialog</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogTitle>Details</DialogTitle>
            <Text>Use Escape to close.</Text>
          </DialogContent>
        </Dialog>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button>Open menu</Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            <DropdownMenuItem>First</DropdownMenuItem>
            <DropdownMenuItem>Second</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </Card>
      <DataTable
        columns={[
          {
            key: "name",
            label: "Name",
            render: (row: { id: string }) => row.id,
          },
        ]}
        rows={[{ id: "sample" }]}
        rowKey={(row) => row.id}
      />
    </main>
  );
}
