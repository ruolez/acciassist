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

  it("applies configured min/max to the number input", () => {
    const q = {
      ...choiceQuestion(),
      type: "number" as const,
      options: [],
      config: { min: 1, max: 10 },
    };
    render(<QuestionRenderer question={q} value={null} onChange={vi.fn()} />);
    const input = screen.getByRole("spinbutton");
    expect(input).toHaveAttribute("min", "1");
    expect(input).toHaveAttribute("max", "10");
  });

  it("caps the date input at today when disallow_future is set", () => {
    const q = {
      ...choiceQuestion(),
      type: "date" as const,
      options: [],
      config: { disallow_future: true },
    };
    const { container } = render(
      <QuestionRenderer question={q} value={null} onChange={vi.fn()} />,
    );
    const input = container.querySelector('input[type="date"]')!;
    expect(input.getAttribute("max")).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("applies configured max_length to text inputs", () => {
    const q = {
      ...choiceQuestion(),
      type: "short_text" as const,
      options: [],
      config: { max_length: 20 },
    };
    render(<QuestionRenderer question={q} value="" onChange={vi.fn()} />);
    expect(screen.getByRole("textbox")).toHaveAttribute("maxlength", "20");
  });

  it("does not steal focus when autoFocus is disabled", () => {
    const q = { ...choiceQuestion(), type: "short_text" as const, options: [] };
    render(
      <QuestionRenderer question={q} value="" onChange={vi.fn()} autoFocus={false} />,
    );
    expect(screen.getByRole("textbox")).not.toHaveFocus();
  });
});
