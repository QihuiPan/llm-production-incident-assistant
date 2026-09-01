import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("App", () => {
  it("communicates the read-only investigation boundary", () => {
    render(<App />);
    expect(screen.getByText("Incident Assistant")).toBeInTheDocument();
    expect(screen.getByText(/No deploys, restarts, rollbacks, or data mutations/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Start investigation/i })).toBeEnabled();
  });
});
