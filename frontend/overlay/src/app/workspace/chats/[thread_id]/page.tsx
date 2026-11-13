import { ChatMemoryBanner } from "@/components/deermate/workspace-memory";
import ChatPage from "@/components/workspace/chats/chat-page";
export default function WorkspaceChatPage() {
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <ChatMemoryBanner />
      <div className="min-h-0 flex-1">
        <ChatPage />
      </div>
    </div>
  );
}
