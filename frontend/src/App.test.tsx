import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import App from "./App";
import * as chatApi from "./api/chat";

describe("chat interface", () => {
  it("warns that local demo records are synthetic", () => {
    render(<App />);

    expect(screen.getByText(/synthetic records/i)).toBeTruthy();
    expect(screen.getByText(/not official FIFA data/i)).toBeTruthy();
  });

  it("sends a question and renders the grounded response and source", async () => {
    const user = userEvent.setup();
    const sendMessage = vi.spyOn(chatApi, "postChatMessage").mockResolvedValue({
      conversation_id: "conversation-1",
      message_id: "message-1",
      answer: "The approved result lists two teams.",
      status: "answered",
      sources: [
        {
          query_id: "tournament_teams",
          label: "Official participating teams and groups",
          urls: ["https://www.fifa.com/example"],
        },
      ],
    });
    render(<App />);

    await user.type(
      screen.getByLabelText("Ask about World Cup 2026"),
      "List the teams",
    );
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(
      await screen.findByText("The approved result lists two teams."),
    ).toBeTruthy();
    expect(screen.getByText("Answered")).toBeTruthy();
    expect(
      screen
        .getByRole("link", { name: "Official source" })
        .getAttribute("href"),
    ).toBe("https://www.fifa.com/example");
    expect(sendMessage).toHaveBeenCalledWith("List the teams", null);
  });

  it("shows safe connection errors and allows another attempt", async () => {
    const user = userEvent.setup();
    vi.spyOn(chatApi, "postChatMessage").mockRejectedValue(
      new chatApi.ChatApiError("Chat is not available yet. Please try again later.", 503),
    );
    render(<App />);

    await user.type(
      screen.getByLabelText("Ask about World Cup 2026"),
      "Show venues",
    );
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Chat is not available yet. Please try again later.",
    );
    expect(screen.getByText("Show venues")).toBeTruthy();
    await waitFor(() => {
      expect(
        (screen.getByLabelText(
          "Ask about World Cup 2026",
        ) as HTMLTextAreaElement).disabled,
      ).toBe(false);
    });
  });

  it("submits with Enter and keeps newlines with Shift+Enter", async () => {
    const user = userEvent.setup();
    const sendMessage = vi.spyOn(chatApi, "postChatMessage").mockResolvedValue({
      conversation_id: "conversation-1",
      message_id: "message-1",
      answer: "Not supported.",
      status: "unsupported",
      sources: [],
    });
    render(<App />);
    const textbox = screen.getByLabelText(
      "Ask about World Cup 2026",
    ) as HTMLTextAreaElement;

    await user.type(textbox, "A question");
    await user.keyboard("{Shift>}{Enter}{/Shift}");
    expect(textbox.value).toBe("A question\n");

    fireEvent.keyDown(textbox, { key: "Enter", shiftKey: false });
    await waitFor(() => expect(sendMessage).toHaveBeenCalledOnce());
    expect(sendMessage).toHaveBeenCalledWith("A question", null);
  });
});
