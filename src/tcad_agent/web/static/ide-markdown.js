"use strict";

(() => {
  function tableCells(line) {
    const trimmed = String(line || "").trim().replace(/^\|/, "").replace(/\|$/, "");
    return trimmed.split("|").map((cell) => cell.trim());
  }

  function isTableSeparator(line) {
    const cells = tableCells(line);
    return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
  }

  function tableAlignment(separator) {
    const value = String(separator || "").trim();
    if (value.startsWith(":") && value.endsWith(":")) return "center";
    if (value.endsWith(":")) return "right";
    if (value.startsWith(":")) return "left";
    return null;
  }

  function blocks(source) {
    const output = [];
    const lines = String(source || "").split(/\r?\n/);
    let index = 0;
    while (index < lines.length) {
      const line = lines[index];
      if (!line.trim()) {
        index += 1;
        continue;
      }
      const heading = line.match(/^(#{1,6})\s+(.+)$/);
      if (heading) {
        output.push({type: "heading", level: heading[1].length, text: heading[2]});
        index += 1;
        continue;
      }
      if (line.startsWith("```")) {
        const language = line.slice(3).trim();
        const content = [];
        index += 1;
        while (index < lines.length && !lines[index].startsWith("```")) {
          content.push(lines[index]);
          index += 1;
        }
        if (index < lines.length) index += 1;
        output.push({type: "code", language, text: content.join("\n")});
        continue;
      }
      if (
        line.includes("|")
        && index + 1 < lines.length
        && isTableSeparator(lines[index + 1])
      ) {
        const headers = tableCells(line);
        const separators = tableCells(lines[index + 1]);
        const rows = [];
        index += 2;
        while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
          rows.push(tableCells(lines[index]));
          index += 1;
        }
        output.push({
          type: "table",
          headers,
          rows,
          alignments: separators.map(tableAlignment),
        });
        continue;
      }
      if (/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
        output.push({type: "rule"});
        index += 1;
        continue;
      }
      if (/^\s*[-*+]\s+/.test(line)) {
        const items = [];
        while (index < lines.length && /^\s*[-*+]\s+/.test(lines[index])) {
          items.push(lines[index].replace(/^\s*[-*+]\s+/, ""));
          index += 1;
        }
        output.push({type: "list", items});
        continue;
      }
      if (/^>\s?/.test(line)) {
        const parts = [];
        while (index < lines.length && /^>\s?/.test(lines[index])) {
          parts.push(lines[index].replace(/^>\s?/, ""));
          index += 1;
        }
        output.push({type: "quote", text: parts.join("\n")});
        continue;
      }
      const paragraph = [line];
      index += 1;
      while (
        index < lines.length
        && lines[index].trim()
        && !/^(#{1,6})\s+/.test(lines[index])
        && !/^\s*[-*+]\s+/.test(lines[index])
        && !/^>\s?/.test(lines[index])
        && !lines[index].startsWith("```")
        && !/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/.test(lines[index])
        && !(
          lines[index].includes("|")
          && index + 1 < lines.length
          && isTableSeparator(lines[index + 1])
        )
      ) {
        paragraph.push(lines[index]);
        index += 1;
      }
      output.push({type: "paragraph", text: paragraph.join(" ")});
    }
    return output;
  }

  function safeLink(value) {
    const href = String(value || "").trim();
    if (!href || href.startsWith("//")) return null;
    const scheme = href.match(/^([a-z][a-z0-9+.-]*):/i);
    if (!scheme) return href;
    return ["http:", "https:"].includes(`${scheme[1].toLowerCase()}:`) ? href : null;
  }

  function appendInline(parent, text, documentRef) {
    const pattern = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^)]+\))/g;
    let cursor = 0;
    for (const match of String(text || "").matchAll(pattern)) {
      if (match.index > cursor) {
        parent.append(documentRef.createTextNode(text.slice(cursor, match.index)));
      }
      const token = match[0];
      if (token.startsWith("`")) {
        const code = documentRef.createElement("code");
        code.textContent = token.slice(1, -1);
        parent.append(code);
      } else if (token.startsWith("**")) {
        const strong = documentRef.createElement("strong");
        strong.textContent = token.slice(2, -2);
        parent.append(strong);
      } else if (token.startsWith("*")) {
        const emphasis = documentRef.createElement("em");
        emphasis.textContent = token.slice(1, -1);
        parent.append(emphasis);
      } else {
        const link = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
        const href = safeLink(link ? link[2] : "");
        if (!link || !href) {
          parent.append(documentRef.createTextNode(link ? link[1] : token));
        } else {
          const anchor = documentRef.createElement("a");
          anchor.textContent = link[1];
          anchor.setAttribute("href", href);
          if (/^https?:/i.test(href)) {
            anchor.setAttribute("target", "_blank");
            anchor.setAttribute("rel", "noopener noreferrer");
          }
          parent.append(anchor);
        }
      }
      cursor = match.index + token.length;
    }
    if (cursor < text.length) parent.append(documentRef.createTextNode(text.slice(cursor)));
  }

  function render(container, source) {
    const documentRef = container.ownerDocument || document;
    const children = [];
    blocks(source).forEach((block) => {
      let element;
      if (block.type === "heading") {
        element = documentRef.createElement(`h${block.level}`);
        appendInline(element, block.text, documentRef);
      } else if (block.type === "code") {
        element = documentRef.createElement("pre");
        const code = documentRef.createElement("code");
        code.textContent = block.text;
        if (block.language) code.setAttribute("data-language", block.language);
        element.append(code);
      } else if (block.type === "list") {
        element = documentRef.createElement("ul");
        block.items.forEach((item) => {
          const row = documentRef.createElement("li");
          appendInline(row, item, documentRef);
          element.append(row);
        });
      } else if (block.type === "quote") {
        element = documentRef.createElement("blockquote");
        appendInline(element, block.text, documentRef);
      } else if (block.type === "table") {
        element = documentRef.createElement("table");
        const head = documentRef.createElement("thead");
        const headRow = documentRef.createElement("tr");
        block.headers.forEach((header, column) => {
          const cell = documentRef.createElement("th");
          if (block.alignments[column]) cell.setAttribute("data-align", block.alignments[column]);
          appendInline(cell, header, documentRef);
          headRow.append(cell);
        });
        head.append(headRow);
        const body = documentRef.createElement("tbody");
        block.rows.forEach((values) => {
          const row = documentRef.createElement("tr");
          block.headers.forEach((_header, column) => {
            const cell = documentRef.createElement("td");
            if (block.alignments[column]) cell.setAttribute("data-align", block.alignments[column]);
            appendInline(cell, values[column] || "", documentRef);
            row.append(cell);
          });
          body.append(row);
        });
        element.append(head, body);
      } else if (block.type === "rule") {
        element = documentRef.createElement("hr");
      } else {
        element = documentRef.createElement("p");
        appendInline(element, block.text, documentRef);
      }
      children.push(element);
    });
    container.replaceChildren(...children);
    return container;
  }

  globalThis.AgentKronigMarkdown = {blocks, render, safeLink};
  if (globalThis.AgentKronigFileViewer) globalThis.AgentKronigFileViewer.markdownBlocks = blocks;
})();
