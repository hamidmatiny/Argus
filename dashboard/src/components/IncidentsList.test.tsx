import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { IncidentsList } from "@/components/IncidentsList";
import { IncidentActions } from "@/components/IncidentActions";
import type { Incident } from "@/lib/types";

const sample: Incident = {
  incident_id: "esc_1",
  vehicle_id: "VH-1",
  severity: "INCIDENT_SEVERITY_CRITICAL",
  status: "INCIDENT_STATUS_OPEN",
  reason: "breaker open",
};

describe("IncidentsList", () => {
  it("renders incident rows", () => {
    render(<IncidentsList initial={[sample]} role="viewer" />);
    expect(screen.getByTestId("incidents-table")).toBeInTheDocument();
    expect(screen.getByText("esc_1")).toBeInTheDocument();
    expect(screen.getByText("VH-1")).toBeInTheDocument();
  });
});

describe("IncidentActions auth gate", () => {
  it("hides action buttons for viewers", () => {
    render(<IncidentActions incident={sample} role="viewer" />);
    expect(screen.getByTestId("viewer-no-actions")).toBeInTheDocument();
    expect(screen.queryByTestId("ack-button")).not.toBeInTheDocument();
  });

  it("shows action buttons for operators", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        incident: { ...sample, status: "INCIDENT_STATUS_ACKNOWLEDGED" },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<IncidentActions incident={sample} role="operator" />);
    expect(screen.getByTestId("incident-actions")).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("ack-button"));
    expect(fetchMock).toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});
