const draftKey = 'traveler_editor_draft';
const titleInput = document.querySelector('#draft-title');
const markdownInput = document.querySelector('#markdown');
const preview = document.querySelector('#preview');
const status = document.querySelector('#save-status');

let draft;
try { draft = JSON.parse(sessionStorage.getItem(draftKey)); } catch (_) { draft = null; }
if (!draft || typeof draft !== 'object') draft = {};
titleInput.value = typeof draft.title === 'string' ? draft.title : 'Trip plan';
markdownInput.value = typeof draft.markdown === 'string' ? draft.markdown : '';

function inline(parent, value) {
  const parts = value.split('**');
  parts.forEach((part, index) => {
    if (index % 2) {
      const strong = document.createElement('strong');
      strong.textContent = part;
      parent.append(strong);
    } else {
      parent.append(document.createTextNode(part));
    }
  });
}

function cells(line) {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(s => s.trim());
}

function renderPreview() {
  preview.replaceChildren();
  const heading = document.createElement('h1');
  heading.textContent = titleInput.value.trim() || 'Trip plan';
  preview.append(heading);
  const lines = markdownInput.value.split(/\r?\n/);
  let paragraph = [];
  let list = null;
  function flush() {
    if (!paragraph.length) return;
    const p = document.createElement('p');
    inline(p, paragraph.join('\n'));
    preview.append(p);
    paragraph = [];
  }
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();
    if (!trimmed) { flush(); list = null; continue; }
    const headingMatch = /^(#{1,6})\s+(.+)$/.exec(trimmed);
    if (headingMatch) {
      flush(); list = null;
      const h = document.createElement(`h${Math.min(headingMatch[1].length + 1, 6)}`);
      inline(h, headingMatch[2]); preview.append(h);
      continue;
    }
    if (trimmed.startsWith('|') && i + 1 < lines.length && /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[i + 1]) && lines[i + 1].includes('-')) {
      flush(); list = null;
      const table = document.createElement('table');
      const header = document.createElement('tr');
      cells(line).forEach(value => { const th = document.createElement('th'); inline(th, value); header.append(th); });
      table.append(header); i++;
      while (i + 1 < lines.length && lines[i + 1].trim().startsWith('|')) {
        const row = document.createElement('tr');
        cells(lines[++i]).forEach(value => { const td = document.createElement('td'); inline(td, value); row.append(td); });
        table.append(row);
      }
      preview.append(table);
      continue;
    }
    const item = /^(?:[-*]|\d+\.)\s+(.+)$/.exec(trimmed);
    if (item) {
      flush();
      if (!list) { list = document.createElement('ul'); preview.append(list); }
      const li = document.createElement('li'); inline(li, item[1]); list.append(li);
      continue;
    }
    if (trimmed.startsWith('> ')) {
      flush(); list = null;
      const quote = document.createElement('blockquote'); inline(quote, trimmed.slice(2)); preview.append(quote);
      continue;
    }
    list = null;
    paragraph.push(line);
  }
  flush();
}

function saveDraft() {
  draft.title = titleInput.value;
  draft.markdown = markdownInput.value;
  try {
    sessionStorage.setItem(draftKey, JSON.stringify(draft));
    status.textContent = 'Saved in this browser tab';
  } catch (_) {
    status.textContent = 'Could not save in this browser tab';
  }
  renderPreview();
}

titleInput.addEventListener('input', saveDraft);
markdownInput.addEventListener('input', saveDraft);
document.addEventListener('keydown', event => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
    event.preventDefault(); saveDraft();
  }
});
document.querySelector('#download').addEventListener('click', () => {
  saveDraft();
  const title = titleInput.value.trim() || 'Trip plan';
  const content = `# ${title}\n\n${markdownInput.value.trim()}\n`;
  const filename = title.normalize('NFKD').replace(/[^\p{L}\p{N}]+/gu, '-').replace(/^-|-$/g, '').toLowerCase() || 'trip-plan';
  const url = URL.createObjectURL(new Blob([content], { type: 'text/markdown;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = `${filename}.md`;
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});

renderPreview();
