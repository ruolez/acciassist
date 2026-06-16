import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Question } from "../../api/types";
import { QuestionRenderer } from "./QuestionRenderer";

function choiceQuestion(): Question {
  return {
    id: 1,
    slug: "role",
    type: "single_choice",
    prompt: "Driver?",
    help_text: null,
    is_required: true,
    display_order: 0,
    page_group: null,
    config: {},
    options: [
      { id: 1, label: "Driver", value: "driver", display_order: 0 },
      { id: 2, label: "Passenger", value: "passenger", display_order: 1 },
    ],
  };
}

describe("QuestionRenderer", () => {
  it("emits the option value when a single choice is clicked", async () => {
    const onChange = vi.fn();
    render(<QuestionRenderer question={choiceQuestion()} value={null} onChange={onChange} />);
    await userEvent.click(screen.getByText("Passenger"));
    expect(onChange).toHaveBeenCalledWith("passenger");
  });

  it("toggles values for multi choice, adding then removing", async () => {
    const onChange = vi.fn();
    const q = { ...choiceQuestion(), type: "multi_choice" as const };
    const { rerender } = render(
      <QuestionRenderer question={q} value={[]} onChange={onChange} />,
    );
    await userEvent.click(screen.getByText("Driver"));
    expect(onChange).toHaveBeenLastCalledWith(["driver"]);

    rerender(<QuestionRenderer question={q} value={["driver"]} onChange={onChange} />);
    await userEvent.click(screen.getByText("Driver"));
    expect(onChange).toHaveBeenLastCalledWith([]);
  });

  it("renders a textarea for long_text and emits typed text", async () => {
    const onChange = vi.fn();
    const q = { ...choiceQuestion(), type: "long_text" as const, options: [] };
    render(<QuestionRenderer question={q} value="" onChange={onChange} />);
    await userEvent.type(screen.getByRole("textbox"), "Hi");
    expect(onChange).toHaveBeenCalled();
  });
});
