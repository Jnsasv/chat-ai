import { afterEach, describe, expect, it, vi } from "vitest";

import { ChatApiError, postChatMessage } from "./chat";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("chat API client", () => {
  it("sends the backend request shape and removes untrusted source URLs", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          conversation_id: "conversation-1",
          message_id: "message-1",
          answer: "The approved answer.",
          status: "answered",
          sources: [
            {
              query_id: "venues",
              label: "Official venue information",
              urls: [
                "https://www.fifa.com/tournament/venue",
                "https://fifa.com.evil.example/spoof",
                "javascript:alert(1)",
              ],
            },
          ],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await postChatMessage("List venues", "conversation-1");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/chat/messages",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: "List venues",
          conversation_id: "conversation-1",
        }),
      }),
    );
    expect(result.sources[0].urls).toEqual([
      "https://www.fifa.com/tournament/venue",
    ]);
  });

  it("maps server failures to safe generic messages", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: "upstream_error",
            message: "Internal database credential details",
          }),
          { status: 503 },
        ),
      ),
    );

    await expect(postChatMessage("List venues", null)).rejects.toMatchObject({
      name: "ChatApiError",
      status: 503,
      message: "Chat is not available yet. Please try again later.",
    });
  });

  it("rejects malformed success responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ answer: "not a valid response" }), {
          status: 200,
        }),
      ),
    );

    await expect(postChatMessage("List venues", null)).rejects.toBeInstanceOf(
      ChatApiError,
    );
  });
});
