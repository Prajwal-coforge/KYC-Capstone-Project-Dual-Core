import { useEffect, useState } from "react";

const ROUTE_LABEL = {
  complete_review: "Complete review",
  request_information: "Request information",
  enhanced_due_diligence: "Enhanced due diligence",
  escalate: "Escalate",
};

function routeLabel(routing) {
  return ROUTE_LABEL[routing] || routing || "Unknown";
}

function showFact(value) {
  if (value == null) return "Not established";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "None listed";
  return String(value).replaceAll("_", " ");
}

function factLabel(key) {
  return key.replaceAll("_", " ");
}

export default function App() {
  const [packets, setPackets] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [status, setStatus] = useState("loading");
  const [message, setMessage] = useState("");

  async function load() {
    setStatus("loading");
    try {
      const response = await fetch("/api/results");
      const body = await response.json();
      if (!response.ok) {
        throw new Error(body.error || "The packet file could not be read.");
      }
      if (!Array.isArray(body)) {
        throw new Error("The packet file is not a list of reviews.");
      }
      setPackets(body);
      setSelectedId((current) => current || body[0]?.case_id || null);
      setStatus("ready");
      setMessage("");
    } catch (error) {
      setPackets([]);
      setSelectedId(null);
      setStatus("error");
      setMessage(error.message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const selected = packets.find((packet) => packet.case_id === selectedId) || null;

  return (
    <div className="page">
      <header className="top">
        <div>
          <p className="eyebrow">Lumen Business Bank</p>
          <h1>KYC review drafts</h1>
          <p className="lede">
            Each note is a draft for a person to read. This screen does not approve or reject a
            customer.
          </p>
        </div>
        <button type="button" onClick={load}>
          Refresh
        </button>
      </header>

      {status === "loading" && <p className="status">Loading drafts…</p>}
      {status === "error" && <p className="status">{message}</p>}
      {status === "ready" && packets.length === 0 && (
        <p className="status">No drafts in submissions/results.json.</p>
      )}

      {status === "ready" && packets.length > 0 && (
        <main className="layout">
          <ul className="cases">
            {packets.map((packet) => (
              <li key={packet.case_id}>
                <button
                  type="button"
                  className={packet.case_id === selectedId ? "case is-selected" : "case"}
                  onClick={() => setSelectedId(packet.case_id)}
                >
                  <span className="case-id">{packet.case_id}</span>
                  <span className={`route route-${packet.routing}`}>{routeLabel(packet.routing)}</span>
                </button>
              </li>
            ))}
          </ul>
          {selected && <Draft packet={selected} />}
        </main>
      )}
    </div>
  );
}

function Draft({ packet }) {
  const facts = packet.facts || {};
  const missing = packet.missing_information || [];
  const questions = packet.follow_up_questions || [];
  const citations = packet.citations || [];
  const incomplete = packet.incomplete_reasons || [];

  return (
    <article className="draft">
      <p className={`route route-${packet.routing}`}>{routeLabel(packet.routing)}</p>
      <h2>{packet.case_id}</h2>
      <p className="meta">
        {(packet.classification || "kyc_review").replaceAll("_", " ")}
        {packet.policy_ids?.length ? ` · ${packet.policy_ids.join(", ")}` : ""}
      </p>

      <h3>Facts</h3>
      <dl className="facts">
        {Object.entries(facts).map(([key, value]) => (
          <div key={key}>
            <dt>{factLabel(key)}</dt>
            <dd>{showFact(value)}</dd>
          </div>
        ))}
      </dl>

      {incomplete.length > 0 && (
        <>
          <h3>Could not be checked</h3>
          <ul>
            {incomplete.map((reason) => (
              <li key={reason}>{reason.replaceAll("_", " ")}</li>
            ))}
          </ul>
        </>
      )}

      <h3>Missing information</h3>
      {missing.length === 0 ? (
        <p>None.</p>
      ) : (
        <ul>
          {missing.map((field) => (
            <li key={field}>{field.replaceAll("_", " ")}</li>
          ))}
        </ul>
      )}

      {questions.length > 0 && (
        <>
          <h3>Draft questions</h3>
          <p className="hint">Not sent. A person decides whether to ask.</p>
          {questions.map((item) => (
            <p key={item.field} className="question">
              <strong>{(item.field || "question").replaceAll("_", " ")}. </strong>
              {item.question}
            </p>
          ))}
        </>
      )}

      <h3>Analyst note</h3>
      <pre className="note">{packet.narrative || "No note."}</pre>

      <h3>Citations</h3>
      {citations.length === 0 ? (
        <p>None.</p>
      ) : (
        citations.map((citation, index) => (
          <blockquote key={`${citation.source_id}-${index}`}>
            <p>{citation.quote}</p>
            <footer>
              {citation.claim}
              {citation.source_id ? ` · ${citation.source_id}` : ""}
            </footer>
          </blockquote>
        ))
      )}
    </article>
  );
}
