export type LegalSection = {
  id: string;
  title: string;
  paragraphs?: readonly string[];
  items?: readonly string[];
  table?: { headers: readonly string[]; rows: readonly (readonly string[])[] };
  links?: readonly { label: string; href: string }[];
};

export type LegalDocument = {
  title: string;
  path: "/privacy" | "/terms";
  version: string;
  effectiveDate: string;
  description: string;
  summary: readonly string[];
  sections: readonly LegalSection[];
};

export const LEGAL_CONTACT = "towo2ssss@gmail.com";
export const LEGAL_ORIGIN = "https://mujuthaek.store";
