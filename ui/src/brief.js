/** Presentation labels for the synthetic cases. Routing still comes from the packet. */

export const SYNTHETIC_BRIEF = [
  ["SYN-01", "Aligned sources", "A clean record is ready for a person to complete."],
  ["SYN-02", "Near screening match", "A near name match escalates. It is not treated as clear."],
  ["SYN-03", "Exact screening match", "An exact list match escalates."],
  ["SYN-04", "Exact and near together", "Both match types are recorded, and the case escalates."],
  ["SYN-05", "PEP flag is true", "Only a boolean true PEP flag raises enhanced due diligence."],
  ["SYN-06", "PEP flag is the text true", "The word true is not a PEP flag. The case completes."],
  ["SYN-07", "Total equal to the threshold", "Equal to the line does not raise enhanced due diligence."],
  ["SYN-08", "Total one unit over the line", "Strictly above the line raises enhanced due diligence."],
  ["SYN-09", "Addresses differ", "A real address difference asks for an explanation."],
  ["SYN-10", "Punctuation-only address", "A comma is not a material address difference."],
  ["SYN-11", "Jurisdictions disagree", "The product policy is not chosen while jurisdiction is disputed."],
  ["SYN-12", "Entity references disagree", "The entity id is left unset. The case escalates."],
  ["SYN-13", "Holder is not an owner", "The identity name must match a registry owner exactly."],
  ["SYN-14", "Declared owner is not an owner", "The filing owner must match a registry owner exactly."],
  ["SYN-15", "Registry tool failed", "No registry means owner names stay unset, not an empty list."],
  ["SYN-16", "Registry is dissolved", "An inactive registry is not used for owners or the address."],
  ["SYN-17", "No owners listed", "An empty owner list escalates and leaves names unset."],
  ["SYN-18", "Ownership is two layers deep", "Depth above one escalates. The known names are kept."],
  ["SYN-19", "Ownership depth missing", "An unknown depth escalates. The case does not guess."],
  ["SYN-20", "Identity document missing", "A missing identity document asks for that document."],
  ["SYN-21", "Identity marked not supplied", "An explicit not-supplied flag asks for the document."],
  ["SYN-22", "Holder name is blank", "A blank holder name is a missing identity document."],
  ["SYN-23", "PEP plus an address mismatch", "The address question outranks enhanced due diligence."],
  ["SYN-24", "Missing identity plus a high total", "The missing document outranks enhanced due diligence."],
  ["SYN-25", "Screening hit plus an address gap", "Escalation still keeps the address question on the draft."],
  ["SYN-26", "Currency is not XCR", "A non-XCR total cannot be compared with the policy line."],
  ["SYN-27", "Jurisdiction outside the book", "An unsupported jurisdiction is classified unsupported."],
  ["SYN-28", "Sole proprietor at its line", "That threshold is equal, so the case completes."],
  ["SYN-29", "Sole proprietor over its line", "One unit over that line raises enhanced due diligence."],
  ["SYN-30", "Last day of the earlier policy", "The review date picks the policy. The later one is not used."],
];

export const BRIEF_BY_ID = Object.fromEntries(
  SYNTHETIC_BRIEF.map(([id, discrepancy, proves]) => [id, { discrepancy, proves }]),
);
