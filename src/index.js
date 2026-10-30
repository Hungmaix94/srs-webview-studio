/**
 * srs-webview-studio
 * Reusable JavaScript SDK to mount or configure SRS Markdown-to-WebView Studio
 * in any web application (React, Next.js, Vue, Vanilla JS, Electron).
 */

export function parseSummaryMarkdown(summaryText = "", title = "SRS Documentation") {
  const lines = String(summaryText || "").split(/\r?\n/);
  const sections = [];
  let currentSection = {
    id: "overview",
    title: "Tổng quan",
    items: []
  };
  sections.push(currentSection);
  let lastTopItem = null;

  for (const rawLine of lines) {
    const line = rawLine.replace(/\s+$/, "");
    if (!line) continue;

    if (line.startsWith("## ")) {
      const secTitle = line.slice(3).trim();
      currentSection = {
        id: `sec-${sections.length}`,
        title: secTitle,
        items: []
      };
      sections.push(currentSection);
      lastTopItem = null;
      continue;
    }

    const mTop = line.match(/^\*\s+\[([^\]]+)\]\(([^)]+)\)/);
    if (mTop) {
      const item = {
        title: mTop[1].trim(),
        path: mTop[2].trim(),
        children: []
      };
      currentSection.items.push(item);
      lastTopItem = item;
      continue;
    }

    const mChild = line.match(/^\s+\*\s+\[([^\]]+)\]\(([^)]+)\)/);
    if (mChild && lastTopItem) {
      lastTopItem.children.push({
        title: mChild[1].trim(),
        path: mChild[2].trim()
      });
    }
  }

  const nonEmpty = sections.filter((s) => s.items.length > 0);
  return {
    title,
    generated_at: new Date().toISOString(),
    groups: nonEmpty,
    sections: nonEmpty
  };
}

/**
 * Mounts an isolated SRS WebView Studio inside any DOM container using an iframe
 * or configures the global window.SrsWebviewStudio instance.
 */
export function mountSrsWebviewStudio(container, options = {}) {
  const target = typeof container === "string" ? document.querySelector(container) : container;
  if (!target) {
    throw new Error("Container element not found for mountSrsWebviewStudio.");
  }

  const studioConfig = {
    title: options.title || "SRS Docs Studio",
    breadcrumbRoot: options.breadcrumbRoot || options.title || "Tài liệu SRS",
    allowedDomain: options.allowedDomain ?? "*",
    authRequired: options.authRequired ?? false,
    localUserLabel: options.localUserLabel || "Studio Editor",
    apiBaseUrl: options.apiBaseUrl || "",
    defaultDocPath: options.defaultDocPath || "_index.md",
    defaultSectionIndex: options.defaultSectionIndex ?? 0,
    embeddedManifest: options.manifest || null,
    embeddedDocs: options.docs || null,
    onSaveDoc: options.onSaveDoc || null
  };

  if (window.SrsWebviewStudio && options.inline !== false) {
    return window.SrsWebviewStudio.configure(studioConfig);
  }

  const iframe = document.createElement("iframe");
  iframe.style.width = options.width || "100%";
  iframe.style.height = options.height || "100vh";
  iframe.style.border = "0";
  iframe.setAttribute("title", studioConfig.title);

  if (options.studioUrl) {
    iframe.src = options.studioUrl;
  } else if (options.templateHtml) {
    const injected = options.templateHtml.replace(
      "/*__SRS_STUDIO_CONFIG_INJECT__*/ {}",
      JSON.stringify(studioConfig)
    );
    iframe.srcdoc = injected;
  }

  target.innerHTML = "";
  target.appendChild(iframe);
  return {
    iframe,
    postConfig(newOverrides) {
      if (iframe.contentWindow && iframe.contentWindow.SrsWebviewStudio) {
        iframe.contentWindow.SrsWebviewStudio.configure(newOverrides);
      }
    }
  };
}

export default {
  parseSummaryMarkdown,
  mountSrsWebviewStudio
};
