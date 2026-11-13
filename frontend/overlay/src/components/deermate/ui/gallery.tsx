"use client";
import { Inbox, Plus } from "lucide-react";
import {
  Avatar,
  Badge,
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Empty,
  ErrorBanner,
  Field,
  Heading,
  IconButton,
  Input,
  Kbd,
  KeyValue,
  Panel,
  RelativeTime,
  SectionHeader,
  SegmentedControl,
  Select,
  Skeleton,
  Spinner,
  StatusBadge,
  Switch,
  Text,
  Textarea,
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
        <Badge variant="violet">Preview</Badge>
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
