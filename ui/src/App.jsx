import { useEffect, useState } from "react";
import ExecutiveBrief from "./ExecutiveBrief.jsx";

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
  const [view, setView] = useState("brief");
  const [setName, setSetName] = useState("synthetic");

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

  const visible = packets.filter((packet) => {
    const synthetic = String(packet.case_id).startsWith("SYN-");
    if (setName === "synthetic") return synthetic;
    if (setName === "dev") return !synthetic;
    return true;
  });
  const shown =
    visible.find((packet) => packet.case_id === selectedId) || visible[0] || null;

  return (
    <div className="page">
      <header className="top">
        <div>
          <p className="eyebrow">Lumen Business Bank</p>
          <h1>{view === "brief" ? "Executive brief" : "KYC review drafts"}</h1>
          <p className="lede">
            {view === "brief"
              ? "How the thirty synthetic discrepancies were routed. Drafts only."
              : "Each note is a draft for a person to read. This screen does not approve or reject a customer."}
          </p>
        </div>
        <div className="nav">
          <button
            type="button"
            className={view === "brief" ? "is-selected" : ""}
            onClick={() => setView("brief")}
          >
            Executive brief
          </button>
          <button
            type="button"
            className={view === "drafts" ? "is-selected" : ""}
            onClick={() => setView("drafts")}
          >
            Drafts
          </button>
          <button type="button" onClick={load}>
            Refresh
          </button>
        </div>
      </header>

      {status === "loading" && <p className="status">Loading drafts…</p>}
      {status === "error" && <p className="status">{message}</p>}
      {status === "ready" && packets.length === 0 && (
        <p className="status">No drafts in submissions/results.json.</p>
      )}

      {status === "ready" && view === "brief" && (
        <ExecutiveBrief
          packets={packets}
          onOpenCase={(caseId) => {
            setSetName(String(caseId).startsWith("SYN-") ? "synthetic" : "dev");
            setSelectedId(caseId);
            setView("drafts");
          }}
        />
      )}

      {status === "ready" && view === "drafts" && packets.length > 0 && (
        <main className="layout">
          <div>
            <div className="nav set-filter">
              {[
                ["synthetic", "Synthetic"],
                ["dev", "Dev set"],
                ["all", "All"],
              ].map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  className={setName === id ? "is-selected" : ""}
                  onClick={() => setSetName(id)}
                >
                  {label}
                </button>
              ))}
            </div>
            <ul className="cases">
              {visible.map((packet) => (
                <li key={packet.case_id}>
                  <button
                    type="button"
                    className={packet.case_id === shown?.case_id ? "case is-selected" : "case"}
                    onClick={() => setSelectedId(packet.case_id)}
                  >
                    <span className="case-id">{packet.case_id}</span>
                    <span className={`route route-${packet.routing}`}>{routeLabel(packet.routing)}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
          {shown && <Draft packet={shown} />}
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
