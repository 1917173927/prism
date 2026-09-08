// Deterministic display layers; server validation remains authoritative.
export function workflowDraftKey(nodes) {
  return JSON.stringify(nodes.map(n => ({node_id:n.node_id, x:n.x, y:n.y,
    dependencies:[...n.dependencies].sort()})).sort((a,b) => a.node_id.localeCompare(b.node_id)));
}

export function workflowStages(nodes) {
  const remaining = new Map(nodes.map(node => [node.node_id, node]));
  const completed = new Set(), stages = [];
  while (remaining.size) {
    const ready = [...remaining.values()].filter(node => node.dependencies.every(id => completed.has(id)));
    if (!ready.length) return {stages, unresolved:[...remaining.values()]};
    stages.push(ready);
    for (const node of ready) { remaining.delete(node.node_id); completed.add(node.node_id); }
  }
  return {stages, unresolved:[]};
}
