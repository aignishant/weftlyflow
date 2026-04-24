// Lucide icon resolution for a node type.
//
// The mapping is intentionally small: a handful of exact-match slugs for
// the core nodes users see every day, then a category-level fallback.
// Unknown slugs fall back to a neutral `Box` icon — always better than
// crashing on a missing mapping.

import {
  Bell,
  Box,
  Braces,
  Cable,
  Clock,
  Code2,
  Database,
  Filter,
  GitBranch,
  Globe,
  Hand,
  type LucideIcon,
  Mail,
  Merge,
  MessageSquare,
  Pencil,
  Shuffle,
  Sparkles,
  Split,
  Timer,
  Webhook,
  Workflow as WorkflowIcon,
  Zap,
} from "lucide-vue-next";

const EXACT: Record<string, LucideIcon> = {
  "weftlyflow.manual_trigger": Hand,
  "weftlyflow.webhook": Webhook,
  "weftlyflow.cron": Clock,
  "weftlyflow.http_request": Globe,
  "weftlyflow.set": Pencil,
  "weftlyflow.if": GitBranch,
  "weftlyflow.switch": Split,
  "weftlyflow.merge": Merge,
  "weftlyflow.filter": Filter,
  "weftlyflow.split_in_batches": Shuffle,
  "weftlyflow.wait": Timer,
  "weftlyflow.code": Code2,
  "weftlyflow.function": Braces,
  "weftlyflow.function_item": Braces,
  "weftlyflow.execute_workflow": WorkflowIcon,
  "weftlyflow.no_op": Box,
  "weftlyflow.email_send": Mail,
  "weftlyflow.slack": MessageSquare,
  "weftlyflow.discord": MessageSquare,
  "weftlyflow.notification": Bell,
  "weftlyflow.postgres": Database,
  "weftlyflow.mysql": Database,
  "weftlyflow.mongodb": Database,
  "weftlyflow.redis": Database,
};

const CATEGORY_FALLBACKS: Record<string, LucideIcon> = {
  trigger: Zap,
  core: Box,
  integration: Cable,
  ai: Sparkles,
};

/**
 * Return the Lucide icon component for a node slug, falling back to the
 * node's category icon and then to a generic `Box` if all else fails.
 */
export function iconForNode(
  slug: string,
  category?: string,
): LucideIcon {
  const exact = EXACT[slug];
  if (exact) {
    return exact;
  }
  // Heuristic: anything ending in `_trigger` is a trigger.
  if (slug.endsWith("_trigger")) {
    return Zap;
  }
  if (category && CATEGORY_FALLBACKS[category]) {
    return CATEGORY_FALLBACKS[category];
  }
  return Box;
}

/**
 * Re-exported so call sites that resolve an icon once and render it many
 * times can avoid pulling `lucide-vue-next` directly.
 */
export type { LucideIcon };
