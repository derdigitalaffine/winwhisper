(function (root) {
  "use strict";
  const paths = {
    waveform: '<path d="M3 10v4m4-7v10m5-14v18m5-14v10m4-7v4"/>',
    document:
      '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6M8 13h8m-8 4h6"/>',
    folder:
      '<path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    minus: '<path d="M5 12h14"/>',
    x: '<path d="m6 6 12 12M6 18 18 6"/>',
    maximize: '<rect x="5" y="5" width="14" height="14" rx="1"/>',
    grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    sliders:
      '<path d="M4 7h9m4 0h3M4 17h3m4 0h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
    settings:
      '<path d="m9.5 3-.5 2-2 .9-1.8-.7-2 3.4L4.7 10v2l-1.5 1.4 2 3.4 1.8-.6 2 .9.5 2h4l.5-2 2-.9 1.8.6 2-3.4-1.5-1.4v-2l1.5-1.4-2-3.4-1.8.7-2-.9-.5-2z"/><circle cx="11.5" cy="11" r="3"/>',
    shield:
      '<path d="m12 3 8 3v6c0 4-5 8-8 9-3-1-8-5-8-9V6z"/><path d="m8.5 12 2.3 2.3 4.7-4.7"/>',
    help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 4 2c-1 .6-1.5 1.2-1.5 2M12 17h.01"/>',
    edit: '<path d="m15 4 5 5M4 20l5-1L20 8a2.8 2.8 0 0 0-4-4L5 15z"/>',
    upload:
      '<path d="M12 16V3m-5 5 5-5 5 5M4 15v5a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5"/>',
    download:
      '<path d="M12 3v13m-5-5 5 5 5-5M4 16v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/>',
    more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
    text: '<path d="M4 5h16M4 10h16M4 15h11M4 20h8"/>',
    sparkles:
      '<path d="m12 3 2.2 6.8L21 12l-6.8 2.2L12 21l-2.2-6.8L3 12l6.8-2.2zM20 2v4m-2-2h4"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "audio-file":
      '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6M8 14v3m4-5v7m4-5v3"/>',
    play: '<path d="m9 5 11 7-11 7z"/>',
    pause: '<path d="M8 5h2v14H8zM15 5h2v14h-2z"/>',
    rewind: '<path d="M3 9h4V5m-3 4a8 8 0 1 1 0 6M10 10h1v5m2-5h2v5h-2z"/>',
    scissors:
      '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="m8 8 13 13M8 16l5-5m3-3 5-5"/>',
    crop: '<path d="M6 3v13a2 2 0 0 0 2 2h13M3 6h13a2 2 0 0 1 2 2v13"/>',
    undo: '<path d="m9 5-5 5 5 5M4 10h10a6 6 0 0 1 0 12"/>',
    "zoom-in":
      '<circle cx="10" cy="10" r="7"/><path d="m15 15 6 6M7 10h6m-3-3v6"/>',
    "zoom-out": '<circle cx="10" cy="10" r="7"/><path d="m15 15 6 6M7 10h6"/>',
    search: '<circle cx="10" cy="10" r="7"/><path d="m15 15 6 6"/>',
    users:
      '<path d="M3 21v-2a5 5 0 0 1 5-5h4a5 5 0 0 1 5 5v2m1-9a4 4 0 0 0 0-8m3 17v-2a5 5 0 0 0-3-4"/><circle cx="10" cy="6" r="4"/>',
    messages:
      '<path d="M4 4h13a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H9l-5 4V6a2 2 0 0 1 2-2z"/><path d="M8 8h7m-7 4h5"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
    "check-circle": '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
    "check-square":
      '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="m7 12 3 3 7-7"/>',
    "check-list":
      '<path d="m3 6 2 2 3-4m3 3h10M3 13l2 2 3-4m3 3h10M3 20h5m3 0h10"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
    timeline:
      '<path d="M6 3v18M12 5h9m-9 7h6m-6 7h9"/><circle cx="6" cy="5" r="2"/><circle cx="6" cy="12" r="2"/><circle cx="6" cy="19" r="2"/>',
    vote: '<path d="m8 3 10 3-3 10-10-3zM4 13l-2 7h20l-2-7M10 8l1 2 4-2"/>',
    server:
      '<rect x="3" y="3" width="18" height="7" rx="2"/><rect x="3" y="14" width="18" height="7" rx="2"/><path d="M7 6.5h.01M7 17.5h.01M12 6.5h5m-5 11h5"/>',
    save: '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h12l4 4v12a2 2 0 0 1-2 2zM7 3v6h9V3M7 21v-8h10v8"/>',
    activity: '<path d="M2 12h5l3-9 4 18 3-9h5"/>',
    refresh:
      '<path d="M20 7v5h-5M4 17v-5h5m10-3a8 8 0 0 0-14-3M5 15a8 8 0 0 0 14 3"/>',
    external:
      '<path d="M14 3h7v7m-9 2 9-9M10 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5"/>',
    "arrow-right": '<path d="M4 12h16m-6-6 6 6-6 6"/>',
    columns:
      '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M12 3v18"/>',
  };
  function icon(name) {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.document}</svg>`;
  }
  function escape(text) {
    return String(text ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  }
  function stamp(seconds, precise = false) {
    seconds = Math.max(0, Number(seconds) || 0);
    let h = Math.floor(seconds / 3600),
      m = Math.floor(seconds / 60) % 60,
      s = seconds % 60;
    return `${h || precise ? String(h).padStart(2, "0") + ":" : ""}${String(m).padStart(2, "0")}:${precise ? s.toFixed(3).padStart(6, "0") : String(Math.floor(s)).padStart(2, "0")}`;
  }
  function parseTime(text) {
    let parts = String(text).trim().replace(",", ".").split(":").map(Number);
    if (parts.length > 3 || parts.some((x) => !Number.isFinite(x) || x < 0))
      throw new Error("Bitte eine gültige Zeit als hh:mm:ss.mmm eingeben.");
    return parts.reverse().reduce((a, x, i) => a + x * 60 ** i, 0);
  }
  function editedToSource(time, spans) {
    let offset = 0;
    for (let i = 0; i < spans.length; i++) {
      let [a, b] = spans[i],
        len = b - a;
      if (time < offset + len || i === spans.length - 1)
        return {
          time: a + Math.max(0, Math.min(len, time - offset)),
          index: i,
        };
      offset += len;
    }
    return { time: 0, index: 0 };
  }
  function sourceToEdited(time, spans) {
    let offset = 0;
    for (let [a, b] of spans) {
      if (time < a) return offset;
      if (time <= b) return offset + Math.max(0, time - a);
      offset += b - a;
    }
    return offset;
  }
  function inline(text) {
    return escape(text)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(
        /\[([^\]]+)\]\(#(s\d+)\)/g,
        '<a href="#$2" class="source-link" data-source="$2">$1</a>',
      );
  }
  function markdown(source) {
    let out = [],
      list = false;
    function close() {
      if (list) {
        out.push("</ul>");
        list = false;
      }
    }
    for (let raw of String(source).split("\n")) {
      if (raw === "## Fundstellen" || raw === "## Sources") break;
      if (/^(Promptversion:|Prompt version:|Modell:|Model:)/.test(raw))
        continue;
      let line = raw.trim();
      if (!line) {
        close();
        continue;
      }
      let h = line.match(/^(#{1,3})\s+(.+)$/);
      if (h) {
        close();
        out.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`);
        continue;
      }
      if (line.startsWith("> ")) {
        close();
        out.push(`<blockquote>${inline(line.slice(2))}</blockquote>`);
        continue;
      }
      let bullet = line.match(/^(?:-|\d+\.)\s+(.+)$/);
      if (bullet) {
        if (!list) {
          out.push("<ul>");
          list = true;
        }
        out.push(
          "<li>" +
            inline(bullet[1]).replace(
              /^\[ \] /,
              '<span class="task-check" aria-label="Aufgabe"></span>',
            ) +
            "</li>",
        );
        continue;
      }
      close();
      out.push("<p>" + inline(line) + "</p>");
    }
    close();
    return out.join("\n");
  }
  function highlight(text, query) {
    if (!query) return escape(text);
    let out = "",
      position = 0,
      lower = String(text).toLocaleLowerCase(),
      needle = query.toLocaleLowerCase(),
      index;
    while ((index = lower.indexOf(needle, position)) !== -1) {
      out +=
        escape(text.slice(position, index)) +
        "<mark>" +
        escape(text.slice(index, index + query.length)) +
        "</mark>";
      position = index + query.length;
    }
    return out + escape(text.slice(position));
  }
  const api = {
    icon,
    escape,
    stamp,
    parseTime,
    editedToSource,
    sourceToEdited,
    markdown,
    highlight,
  };
  root.StudioCore = api;
  if (typeof module !== "undefined") module.exports = api;
})(globalThis);
