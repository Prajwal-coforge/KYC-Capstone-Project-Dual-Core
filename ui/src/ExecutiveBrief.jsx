import { BRIEF_BY_ID, SYNTHETIC_BRIEF } from "./brief.js";

const ORDER = [
  "complete_review",
  "request_information",
  "enhanced_due_diligence",
  "escalate",
];

const ROUTE_LABEL = {
  complete_review: "Complete review",
  request_information: "Request information",
  enhanced_due_diligence: "Enhanced due diligence",
  escalate: "Escalate",
};

function routeLabel(routing) {
  return ROUTE_LABEL[routing] || routing || "Unknown";
}

export default function ExecutiveBrief({ packets, onOpenCase }) {
  const synthetic = packets.filter((packet) => BRIEF_BY_ID[packet.case_id]);
  const byRoute = Object.fromEntries(ORDER.map((routing) => [routing, []]));
  for (const packet of synthetic) {
    (byRoute[packet.routing] || (byRoute[packet.routing] = [])).push(packet);
  }

  return (
    <section className="brief">
      <p className="lede">
        Thirty made-up discrepancies, decided by the same rules as the twelve dev cases.
        Each result is a draft. This screen does not approve or reject a customer.
      </p>

      <div className="stats">
        {ORDER.map((routing) => (
          <p key={routing} className="stat">
            <strong>{(byRoute[routing] || []).length}</strong>
            <span>{routeLabel(routing)}</span>
          </p>
        ))}
      </div>

      <h2>How a route is chosen</h2>
      <ol className="precedence">
        <li>A conflict, a screening hit, a failed tool, or an unsupported customer escalates.</li>
        <li>A missing identity document or a real address difference asks for information.</li>
        <li>A boolean PEP flag, or a total strictly above the policy line, is enhanced due diligence.</li>
        <li>Anything else is ready to complete.</li>
      </ol>
      <p className="hint">
        A question outranks enhanced due diligence. An escalation still keeps the missing fact
        on the draft. Owner names stay unset when the registry is missing, inactive, or empty.
      </p>

      {synthetic.length === 0 && (
        <p className="status">The thirty synthetic drafts are not in submissions/results.json.</p>
      )}

      {ORDER.map((routing) => {
        const group = byRoute[routing] || [];
        if (group.length === 0) return null;
        return (
          <div key={routing}>
            <h2>{routeLabel(routing)}</h2>
            <table className="brief-table">
              <thead>
                <tr>
                  <th>Case</th>
                  <th>Discrepancy</th>
                  <th>What it shows</th>
                </tr>
              </thead>
              <tbody>
                {group.map((packet) => {
                  const row = BRIEF_BY_ID[packet.case_id];
                  return (
                    <tr key={packet.case_id}>
                      <td>
                        <button type="button" className="linkish" onClick={() => onOpenCase(packet.case_id)}>
                          {packet.case_id}
                        </button>
                      </td>
                      <td>{row.discrepancy}</td>
                      <td>{row.proves}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        );
      })}

      {synthetic.length > 0 && synthetic.length !== SYNTHETIC_BRIEF.length && (
        <p className="status">
          {synthetic.length} of {SYNTHETIC_BRIEF.length} synthetic drafts are in the packet file.
        </p>
      )}
    </section>
  );
}
