export function inspectDiagramGeometry() {
  const svg = document.querySelector('svg');
  const rootMatrix = svg.getScreenCTM().inverse();
  const project = (element, point) => new DOMPoint(point.x, point.y).matrixTransform(element.getScreenCTM()).matrixTransform(rootMatrix);
  const projectBox = (element, box) => {
    const points = [project(element, {x: box.x, y: box.y}), project(element, {x: box.x + box.width, y: box.y}),
      project(element, {x: box.x, y: box.y + box.height}), project(element, {x: box.x + box.width, y: box.y + box.height})];
    const x = Math.min(...points.map(point => point.x));
    const y = Math.min(...points.map(point => point.y));
    return {x, y, width: Math.max(...points.map(point => point.x)) - x, height: Math.max(...points.map(point => point.y)) - y};
  };
  const bounds = element => {
    return projectBox(element, element.getBBox());
  };
  const inside = (point, box, margin = 0) => point.x >= box.x - margin && point.x <= box.x + box.width + margin
    && point.y >= box.y - margin && point.y <= box.y + box.height + margin;
  const textElements = [...svg.querySelectorAll('text, foreignObject .nodeLabel, foreignObject .edgeLabel')]
    .filter(text => text.textContent.trim());
  const texts = textElements.map(text => {
    const boxes = [];
    if (text instanceof SVGTextContentElement) {
      for (let index = 0; index < text.getNumberOfChars(); index += 1) {
        if (!(text.textContent[index] || '').trim()) continue;
        const box = text.getExtentOfChar(index);
        boxes.push(projectBox(text, box));
      }
    } else {
      const walker = document.createTreeWalker(text, NodeFilter.SHOW_TEXT);
      let content = walker.nextNode();
      while (content) {
        for (let index = 0; index < content.length; index += 1) {
          if (!content.textContent[index].trim()) continue;
          const range = document.createRange();
          range.setStart(content, index);
          range.setEnd(content, index + 1);
          const box = range.getBoundingClientRect();
          const first = new DOMPoint(box.left, box.top).matrixTransform(rootMatrix);
          const last = new DOMPoint(box.right, box.bottom).matrixTransform(rootMatrix);
          boxes.push({x: first.x, y: first.y, width: last.x - first.x, height: last.y - first.y});
        }
        content = walker.nextNode();
      }
    }
    const label = text.closest('.edgeLabel');
    const background = label?.querySelector('rect.labelBkg, rect.background, rect[data-label-background]');
    const style = background && getComputedStyle(background);
    const opaque = Boolean(background && Number(style.opacity) === 1 && Number(style.fillOpacity) === 1
      && style.fill !== 'none' && !style.fill.startsWith('rgba('));
    return {element: text, content: text.textContent.trim(), boxes, edgeLabel: Boolean(label),
      background: opaque ? bounds(background) : null};
  });
  const paths = [...svg.querySelectorAll('path, line, polyline, polygon, rect, ellipse')]
    .filter(element => {
      const style = getComputedStyle(element);
      return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity) > 0
        && style.stroke !== 'none' && Number(style.strokeOpacity) > 0 && parseFloat(style.strokeWidth) > 0;
    });
  const backgrounds = [...svg.querySelectorAll('rect, ellipse, polygon, path')].filter(element => {
    const style = getComputedStyle(element);
    return !element.closest('defs') && Number(style.opacity) === 1 && Number(style.fillOpacity) === 1
      && style.fill !== 'none' && !style.fill.startsWith('rgba(');
  }).map(element => ({element, matrix: element.getScreenCTM().inverse(), box: bounds(element)}));
  const collisions = [];
  for (const [index, element] of paths.entries()) {
    const length = element.getTotalLength();
    if (length === 0) continue;
    const touched = new Set();
    for (let distance = 0; distance <= length; distance += 1) {
      const point = project(element, element.getPointAtLength(distance));
      for (const text of texts) {
        if (touched.has(text)) continue;
        if (text.boxes.some(box => inside(point, box, 1))) {
          const covered = backgrounds.some(background => {
            if (!(element.compareDocumentPosition(background.element) & Node.DOCUMENT_POSITION_FOLLOWING)
                || !inside(point, background.box)) return false;
            const local = point.matrixTransform(svg.getScreenCTM()).matrixTransform(background.matrix);
            return background.element.isPointInFill(local);
          });
          if (covered) continue;
          touched.add(text);
          collisions.push({line: element.id || `path-${index}`, label: text.content, edge_label: text.edgeLabel,
            location: {x: Math.round(point.x), y: Math.round(point.y)}});
        }
      }
    }
  }
  const cardOverflows = [];
  for (const node of svg.querySelectorAll('.node.neutral, .node.accent, .node.success, .node.failure')) {
    const rectangle = node.querySelector('rect.label-container');
    const text = node.querySelector('.label text');
    if (!rectangle || !text) throw Error('Diagram card must have a rectangle and text');
    const card = bounds(rectangle), label = bounds(text);
    if (label.x < card.x - 0.5 || label.y < card.y - 0.5 || label.x + label.width > card.x + card.width + 0.5
        || label.y + label.height > card.y + card.height + 0.5) cardOverflows.push({text: text.textContent.trim(), card, label});
  }
  return {text_count: texts.length, line_count: paths.length, collisions, card_overflows: cardOverflows,
    stage_connector_lengths: [...svg.querySelectorAll('[data-stage-connector]')].map(item => item.getTotalLength()),
    nodes: [...svg.querySelectorAll('.node')].map(node => ({text: node.textContent.trim(), ...bounds(node)})),
    edge_labels: texts.filter(text => text.edgeLabel).map(text => ({text: text.content, opaque_background: Boolean(text.background)}))};
}
