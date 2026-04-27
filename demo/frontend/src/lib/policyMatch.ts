import { minimatch } from "minimatch";
import { parseDocument, isMap, isSeq } from "yaml";
import type { ActionRequest } from "./types";

type YamlMapLike = { toJSON?: () => unknown };
function toPlainObject(node: unknown): Record<string, unknown> | null {
  if (node === null || node === undefined) return null;
  const candidate = node as YamlMapLike;
  if (typeof candidate.toJSON === "function") {
    const plain = candidate.toJSON();
    if (plain && typeof plain === "object" && !Array.isArray(plain)) {
      return plain as Record<string, unknown>;
    }
    return null;
  }
  if (typeof node === "object" && !Array.isArray(node)) {
    return node as Record<string, unknown>;
  }
  return null;
}

export type RuleStatus =
  | "matched"
  | "action-only"
  | "resource-only"
  | "constraint-fail"
  | "no-match";

export type ParsedRule = {
  index: number;
  line: number; // 1-based
  action: string;
  resource: string;
  constraint: Record<string, unknown> | null;
};

export type RuleTrace = ParsedRule & { status: RuleStatus };

export type PolicyTrace = {
  rules: RuleTrace[];
  matchedIndex: number | null;
  parseError: string | null;
};

export const FALLBACK_POLICY = `capabilities:
  - action: db.read
    resource: prod/**

  - action: db.write
    resource: prod/test_*

  - action: mcp.call
    resource: scholar/*

  - action: net.http
    resource: https://api.example.com/**
    constraint:
      method: GET
`;

function actionMatches(rule: ParsedRule, request: ActionRequest): boolean {
  return rule.action === request.action;
}

function resourceMatches(rule: ParsedRule, request: ActionRequest): boolean {
  return minimatch(request.target, rule.resource, {
    nocomment: true,
    dot: true,
    noglobstar: false,
  });
}

function constraintMatches(rule: ParsedRule, request: ActionRequest): boolean {
  if (!rule.constraint) return true;
  const params = request.params ?? {};
  return Object.entries(rule.constraint).every(([k, v]) => params[k] === v);
}

function offsetToLine(text: string, offset: number): number {
  let line = 1;
  for (let i = 0; i < offset && i < text.length; i++) {
    if (text.charCodeAt(i) === 10) line++;
  }
  return line;
}

export function parsePolicyRules(yaml: string): {
  rules: ParsedRule[];
  parseError: string | null;
} {
  try {
    const doc = parseDocument(yaml, { keepSourceTokens: true });
    if (doc.errors.length > 0) {
      return { rules: [], parseError: doc.errors[0].message };
    }
    const root = doc.contents;
    if (!isMap(root)) return { rules: [], parseError: "Policy root must be a map" };
    const capsPair = root.items.find(
      (it) => (it.key as { value?: unknown } | null)?.value === "capabilities",
    );
    if (!capsPair) return { rules: [], parseError: "Missing 'capabilities' key" };
    const seq = capsPair.value;
    if (!isSeq(seq)) return { rules: [], parseError: "'capabilities' must be a list" };
    const rules: ParsedRule[] = [];
    seq.items.forEach((item, index) => {
      if (!isMap(item)) return;
      const action = (item.get("action") as string | undefined) ?? "";
      const resource = (item.get("resource") as string | undefined) ?? "";
      const constraintNode = item.get("constraint");
      const constraint = toPlainObject(constraintNode);
      const rangeStart = item.range?.[0] ?? 0;
      const line = offsetToLine(yaml, rangeStart);
      rules.push({ index, line, action, resource, constraint });
    });
    return { rules, parseError: null };
  } catch (err) {
    return {
      rules: [],
      parseError: err instanceof Error ? err.message : String(err),
    };
  }
}

export function traceRequest(yaml: string, request: ActionRequest): PolicyTrace {
  const { rules, parseError } = parsePolicyRules(yaml);
  let matchedIndex: number | null = null;
  const traced: RuleTrace[] = rules.map((rule) => {
    const a = actionMatches(rule, request);
    const r = resourceMatches(rule, request);
    const c = constraintMatches(rule, request);
    let status: RuleStatus;
    if (a && r && c) status = "matched";
    else if (a && r && !c) status = "constraint-fail";
    else if (a && !r) status = "action-only";
    else if (!a && r) status = "resource-only";
    else status = "no-match";
    if (status === "matched" && matchedIndex === null) matchedIndex = rule.index;
    return { ...rule, status };
  });
  return { rules: traced, matchedIndex, parseError };
}
