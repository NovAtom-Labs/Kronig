"use strict";

function assertEqual(actual, expected, message) {
  if (actual !== expected) throw new Error(`${message}: ${actual}`);
}

class FakeNode {
  constructor(tagName = "#text", text = "") {
    this.tagName = tagName;
    this.textContent = text;
    this.children = [];
    this.attributes = {};
    this.ownerDocument = fakeDocument;
  }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = [...children]; }
  setAttribute(name, value) { this.attributes[name] = value; }
}

const fakeDocument = {
  createElement(tagName) { return new FakeNode(tagName); },
  createTextNode(text) { return new FakeNode("#text", text); },
};

function walk(node) {
  return [node, ...node.children.flatMap(walk)];
}

const markdown = globalThis.AgentKronigMarkdown;
const blocks = markdown.blocks(
  "# Result\n\n- **Fermi** statistics\n- `SRH` recombination\n\n```python\nprint('safe')\n```",
);
assertEqual(blocks[0].type, "heading", "heading is recognized");
assertEqual(blocks[1].type, "list", "list is recognized");
assertEqual(blocks[2].type, "code", "fenced code is recognized");

const container = new FakeNode("div");
markdown.render(
  container,
  "<script>alert(1)</script>\n\n[Safe](https://example.test) [Bad](javascript:alert(1)) **bold** `code`",
);
const nodes = walk(container);
assertEqual(nodes.some((node) => node.tagName === "script"), false, "raw HTML never creates elements");
assertEqual(nodes.some((node) => node.textContent.includes("<script>")), true, "raw HTML remains visible text");
const links = nodes.filter((node) => node.tagName === "a");
assertEqual(links.length, 1, "unsafe links are not anchors");
assertEqual(links[0].attributes.href, "https://example.test", "safe HTTPS link is retained");
assertEqual(links[0].attributes.rel, "noopener noreferrer", "external link is isolated");
assertEqual(nodes.some((node) => node.tagName === "strong"), true, "emphasis uses a constructed element");
assertEqual(nodes.some((node) => node.tagName === "code"), true, "inline code uses a constructed element");

const relative = new FakeNode("div");
markdown.render(relative, "[Open file](src/model.py)");
const relativeLink = walk(relative).find((node) => node.tagName === "a");
assertEqual(relativeLink.attributes.href, "src/model.py", "workspace-relative links remain local");
assertEqual(relativeLink.attributes.target, undefined, "local links do not open a new tab");

const scientific = new FakeNode("div");
const scientificBlocks = markdown.blocks(
  "## Sweep\n\n| Bias (V) | Current density (A/m²) |\n| ---: | ---: |\n| -1.0 | 2.4e-9 |\n| 0.6 | 1.1e4 |\n\n---\n",
);
assertEqual(scientificBlocks[1].type, "table", "GFM-style result tables are recognized");
assertEqual(scientificBlocks[2].type, "rule", "horizontal rules are recognized");
markdown.render(
  scientific,
  "| Quantity | Value |\n| --- | --- |\n| Peak field | 4.2e6 V/m |\n\n---",
);
const scientificNodes = walk(scientific);
assertEqual(scientificNodes.some((node) => node.tagName === "table"), true, "tables render structurally");
assertEqual(scientificNodes.filter((node) => node.tagName === "th").length, 2, "table headers render");
assertEqual(scientificNodes.filter((node) => node.tagName === "td").length, 2, "table cells render");
assertEqual(scientificNodes.some((node) => node.tagName === "hr"), true, "rules render structurally");
