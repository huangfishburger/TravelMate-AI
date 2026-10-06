const $ = (selector) => document.querySelector(selector);
const messagesEl = $('#messages');
const activityEl = $('#activity');
const form = $('#composer');
const promptEl = $('#prompt');
const sendEl = $('#send');
const imageInput = $('#images');
const attachmentsEl = $('#attachments');
let selectedImages = [];
let currentDestination = '';
let currentMessages = [];

function renderAttachments() {
  attachmentsEl.replaceChildren();
  selectedImages.forEach((file, index) => {
    const chip = el('div', 'attachment');
    const preview = el('img'); preview.src = URL.createObjectURL(file);
    preview.onload = () => URL.revokeObjectURL(preview.src);
    preview.alt = '';
    const remove = el('button', '', '×'); remove.type = 'button';
    remove.setAttribute('aria-label', `Remove ${file.name}`);
    remove.addEventListener('click', () => { selectedImages.splice(index, 1); renderAttachments(); });
    chip.append(preview, el('span', '', file.name), remove); attachmentsEl.append(chip);
  });
}

imageInput.addEventListener('change', () => {
  const incoming = Array.from(imageInput.files || []);
  if (selectedImages.length + incoming.length > 3 || incoming.some((file) => file.size > 8 * 1024 * 1024)) {
    alert('Attach at most 3 images, up to 8 MB each.'); imageInput.value = ''; return;
  }
  selectedImages.push(...incoming); imageInput.value = ''; renderAttachments();
});

function dataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error(`Could not read ${file.name}`));
    reader.readAsDataURL(file);
  });
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function tag(container, label, soft = false) {
  container.append(el('span', `tag${soft ? ' soft' : ''}`, label));
}

function renderState(memory) {
  const state = memory?.trip_state || {};
  $('#destination').textContent = state.destination || 'Where to next?';
  const dates = state.dates || {};
  const budget = state.hard_constraints?.budget;
  const budgetCurrency = state.hard_constraints?.budget_currency;
  const dateText = dates.start && dates.end ? `${dates.start} → ${dates.end}` : dates.start || dates.end || '';
  const budgetText = budget != null ? `${budgetCurrency || '¤'} ${Number(budget).toLocaleString()} budget` : '';
  const peopleText = state.travelers ? `${state.travelers} traveler${state.travelers === 1 ? '' : 's'}` : '';
  $('#dates-budget').textContent = [dateText, peopleText, budgetText].filter(Boolean).join(' · ') || 'Your plans will appear here.';
  const hard = $('#hard-tags');
  const soft = $('#soft-tags');
  hard.replaceChildren(); soft.replaceChildren();
  if (state.hard_constraints?.nonstop === true) tag(hard, '🔒 Nonstop');
  if (state.locked?.flight) tag(hard, '🔒 Flight locked');
  if (state.locked?.hotel) tag(hard, '🔒 Hotel locked');
  if (!hard.childNodes.length) hard.append(el('span', 'empty-tag', 'No constraints yet'));
  if (state.soft_preferences?.airline) tag(soft, `♥ ${state.soft_preferences.airline} preferred`, true);
  if (state.soft_preferences?.pace) tag(soft, `${state.soft_preferences.pace} pace`, true);
  for (const interest of state.soft_preferences?.interests || []) tag(soft, interest, true);
  if (!soft.childNodes.length) soft.append(el('span', 'empty-tag', 'Preferences will appear here'));
}

function sectioned(text) {
  const sections = { intro: [], summary: [], details: [], budget: [] };
  let current = 'intro';
  for (const line of text.split(/\r?\n/)) {
    const label = line.replace(/^[#*\s]+|[#*\s:]+$/g, '').toLowerCase();
    if (/^(daily summary|行程摘要|每日摘要)$/.test(label)) current = 'summary';
    else if (/^(daily details|行程細節|每日細節)$/.test(label)) current = 'details';
    else if (/^(budget|cost breakdown|estimated costs|cost estimate|budget breakdown|費用|費用明細|費用估算|預算)$/.test(label)) current = 'budget';
    else sections[current].push(line);
  }
  return sections;
}

function textBlock(parent, lines, className) {
  const text = lines.join('\n').trim();
  if (!text) return;
  parent.append(el('div', className, text));
}

function dayBlocks(parent, lines, className) {
  const groups = [];
  let current = [];
  for (const line of lines) {
    if (/^\s*(?:#{1,4}\s*|\*\*)?(?:day\s*\d+|第[一二三四五六七八九十\d]+天)/i.test(line) && current.length) {
      groups.push(current); current = [];
    }
    current.push(line);
  }
  if (current.length) groups.push(current);
  for (const group of groups) {
    const card = el('div', className);
    const first = group[0]?.trim() || '';
    if (/^(?:#{1,4}\s*|\*\*)?(?:day\s*\d+|第[一二三四五六七八九十\d]+天)/i.test(first)) {
      card.append(el('h4', '', first.replace(/^#+\s*/, '').replace(/\*\*/g, '')));
      textBlock(card, group.slice(1), 'answer-text');
    } else textBlock(card, group, 'answer-text');
    parent.append(card);
  }
}

const costLabels = {flight: 'Flights', hotel: 'Hotel', food: 'Food', transportation: 'Transportation', activities: 'Activities', other: 'Other'};

function costCategory(label) {
  const normalized = String(label).toLowerCase().replace(/[\s_/-]/g, '');
  if (/flight|airfare|airline|機票|航班/.test(normalized)) return 'flight';
  if (/hotel|lodging|accommodation|住宿|飯店|旅館/.test(normalized)) return 'hotel';
  if (/food|meal|dining|餐飲|餐費|飲食/.test(normalized)) return 'food';
  if (/transport|transit|localtravel|市內|區域交通|交通/.test(normalized)) return 'transportation';
  if (/activit|attraction|ticket|門票|活動|景點/.test(normalized)) return 'activities';
  if (/other|misc|contingen|雜支|其他|備用/.test(normalized)) return 'other';
  return null;
}

function resolvedCosts(answer, budgetLines) {
  const costs = {};
  for (const [label, raw] of Object.entries(answer.costs || {})) {
    const key = costCategory(label);
    const amount = Number(raw);
    if (key && raw != null && Number.isFinite(amount)) costs[key] = amount;
  }
  for (const line of budgetLines) {
    const cleaned = line.trim().replace(/^[-*]\s*/, '').replace(/\*\*/g, '');
    let label, amountText;
    if (cleaned.startsWith('|')) {
      const columns = cleaned.replace(/^\||\|$/g, '').split('|').map(part => part.trim());
      [label, amountText] = columns;
    } else {
      const split = cleaned.match(/^([^：:]+)[：:]\s*(.+)$/);
      if (split) [, label, amountText] = split;
    }
    const key = costCategory(label || '');
    const amount = amountText?.match(/(?:TWD|NTD|NT\$|USD|JPY|¥|\$)?\s*([\d,]+(?:\.\d+)?)/i);
    if (key && costs[key] == null && amount) costs[key] = Number(amount[1].replace(/,/g, ''));
  }
  return costs;
}

function renderCosts(parent, answer, budgetLines = [], zh = false) {
  if (!answer.costs) return;
  const table = el('table', 'cost-table');
  const costs = resolvedCosts(answer, budgetLines);
  const currency = answer.currency || 'USD';
  const money = (value) => `${currency} ${Number(value).toLocaleString(undefined, {maximumFractionDigits: 2})}`;
  const chineseLabels = {flight: '機票', hotel: '住宿', food: '餐飲', transportation: '當地交通', activities: '活動', other: '雜支'};
  for (const [key, label] of Object.entries(zh ? chineseLabels : costLabels)) {
    const amount = costs[key];
    if (amount == null) continue;
    const row = el('tr');
    row.append(el('td', '', label), el('td', '', money(amount)));
    table.append(row);
  }
  const itemized = Object.values(costs).reduce((sum, amount) => sum + amount, 0);
  const difference = answer.total_cost == null ? 0 : answer.total_cost - itemized;
  const reconciled = answer.total_cost != null && Math.abs(difference) < 0.01;
  if (answer.total_cost != null && difference > 0.01) {
    const row = el('tr'); row.append(el('td', '', zh ? '未分類費用' : 'Unitemized balance'), el('td', '', money(difference))); table.append(row);
  }
  if (answer.total_cost != null) {
    const row = el('tr', 'cost-total'); row.append(el('td', '', zh ? '預估總計' : 'Estimated total'), el('td', '', money(answer.total_cost))); table.append(row);
  }
  parent.append(el('h3', '', zh ? '預估費用' : 'Estimated costs'), table);
  if (answer.total_cost != null && !reconciled) parent.append(el('div', 'budget-note over',
    difference > 0 ? (zh ? '部分費用已計入總額，但沒有分類。' : 'Some costs are included in the total but have no category.') :
      (zh ? '明細加總高於檢查後的總額，請核對原始預算說明。' : 'The listed categories exceed the checked total. Review the original budget notes.')));
  if (answer.total_budget != null) {
    const remaining = answer.remaining != null ? answer.remaining : answer.total_budget - answer.total_cost;
    parent.append(el('div', `budget-note${answer.within_budget === false ? ' over' : ''}`,
      `${zh ? '預算' : 'Budget'} ${money(answer.total_budget)} · ${answer.within_budget === false ? (zh ? '超出' : 'Over by') : (zh ? '剩餘' : 'Remaining')} ${money(Math.abs(remaining))}`));
  }
  return reconciled;
}

function renderBudgetContent(parent, lines) {
  let prose = [];
  let table = null;
  let hasTable = false;
  const flushProse = () => {
    textBlock(parent, prose, 'answer-text');
    prose = [];
  };
  for (const line of lines) {
    if (/^\s*\|/.test(line)) {
      hasTable = true;
      if (!table) {
        flushProse();
        table = el('table', 'cost-table detailed-cost-table');
        parent.append(table);
      }
      const cells = line.trim().replace(/^\||\|$/g, '').split('|').map((cell) => cell.trim());
      if (cells.every((cell) => /^:?-{3,}:?$/.test(cell))) continue;
      const row = el('tr');
      cells.forEach((cell) => row.append(el('td', '', cell.replace(/\*\*/g, ''))));
      table.append(row);
    } else {
      table = null;
      prose.push(line);
    }
  }
  flushProse();
  return hasTable;
}

function renderLogistics(parent, logistics, zh = false) {
  if (!logistics) return;
  const entries = [];
  const warnings = [];
  const flight = logistics.flight;
  if (flight && typeof flight === 'object') {
    const airportCode = (airport) => typeof airport === 'object' ? airport?.id : airport;
    const airportTime = (airport) => typeof airport === 'object' ? airport?.time : null;
    const endpoints = (journey) => {
      if (!journey) return [null, null];
      const segments = Array.isArray(journey.segments) && journey.segments.length ? journey.segments : [journey];
      return [airportCode(segments[0].departure_airport), airportCode(segments[segments.length - 1].arrival_airport)];
    };
    const legs = [
      [zh ? '去程' : 'Outbound', flight.outbound],
      [zh ? '回程' : 'Return', flight.return],
    ];
    if (!legs.some(([, leg]) => leg) && (flight.flight_number || flight.departure_time)) {
      legs.push([zh ? '航班' : 'Flight', flight]);
    }
    for (const [label, leg] of legs) {
      if (!leg || typeof leg !== 'object') continue;
      const segments = Array.isArray(leg.segments) && leg.segments.length ? leg.segments : [leg];
      const first = segments[0];
      const last = segments[segments.length - 1];
      const departCode = airportCode(first.departure_airport);
      const arriveCode = airportCode(last.arrival_airport);
      const departTime = first.departure_time || airportTime(first.departure_airport);
      const arriveTime = last.arrival_time || airportTime(last.arrival_airport);
      const route = [departCode, arriveCode].filter(Boolean).join(' → ');
      const identity = segments.length > 1 ? (zh ? `${segments.length} 段航班` : `${segments.length} flight segments`) : [leg.airline, leg.flight_number].filter(Boolean).join(' ');
      const timing = [first.date || leg.date, departTime, arriveTime ? `${zh ? '抵達' : 'arrives'} ${arriveTime}` : ''].filter(Boolean).join(' · ');
      const detail = [identity, route, timing].filter(Boolean).join(' · ');
      if (detail) entries.push([label, detail]);
      if (segments.length > 1) segments.forEach((segment, index) => {
        const segmentRoute = [airportCode(segment.departure_airport), airportCode(segment.arrival_airport)].filter(Boolean).join(' → ');
        const segmentTime = [segment.departure_time || airportTime(segment.departure_airport),
          segment.arrival_time || airportTime(segment.arrival_airport)].filter(Boolean).join(' → ');
        entries.push([zh ? `第 ${index + 1} 段` : `Leg ${index + 1}`, [[segment.airline, segment.flight_number].filter(Boolean).join(' '), segmentRoute, segmentTime].filter(Boolean).join(' · ')]);
      });
    }
    if (flight.outbound && flight.return) {
      const [outStart, outEnd] = endpoints(flight.outbound);
      const [returnStart, returnEnd] = endpoints(flight.return);
      if ((outEnd && returnStart && outEnd !== returnStart) ||
          (outStart && returnEnd && outStart !== returnEnd)) {
        warnings.push(zh ? '顯示的航段無法連成完整來回行程，請核對是否漏了轉機航段或是刻意安排多城市路線。' : 'Displayed flight segments do not form a continuous round trip. Check the full itinerary for missing connections or an intentional multi-city route.');
      }
    }
  }
  const hotel = logistics.hotel;
  const stays = Array.isArray(hotel?.stays) ? hotel.stays : hotel?.name ? [hotel] : [];
  for (const stay of stays) {
    if (!stay || !stay.name) continue;
    const start = stay.check_in_date;
    const end = stay.check_out_date;
    const from = start ? new Date(`${start}T00:00:00Z`) : null;
    const until = end ? new Date(`${end}T00:00:00Z`) : null;
    if (from && until && !Number.isNaN(from.valueOf()) && !Number.isNaN(until.valueOf()) &&
        until > from && (until - from) / 86400000 <= 30) {
      for (let day = new Date(from); day < until; day.setUTCDate(day.getUTCDate() + 1)) {
        entries.push([zh ? `${day.toISOString().slice(0, 10)} 住宿` : `${day.toISOString().slice(0, 10)} night`, stay.name]);
      }
    } else {
      entries.push([start && end ? `${start} → ${end}` : (zh ? '飯店' : 'Hotel'), stay.name]);
    }
  }
  if (!entries.length) return;
  parent.append(el('h3', '', zh ? '航班與住宿' : 'Flights & stays'));
  const list = el('div', 'logistics-list');
  for (const [label, detail] of entries) {
    const row = el('div', 'logistics-row');
    row.append(el('span', 'logistics-label', label), el('span', 'logistics-detail', detail));
    list.append(row);
  }
  parent.append(list);
  for (const warning of warnings) parent.append(el('div', 'budget-note over', warning));
}

function exportMarkdown(message) {
  let markdown = (message.response || '').trim();
  if (message.costs) {
    const zh = message.response_language === 'Traditional Chinese';
    const costs = resolvedCosts(message, sectioned(message.response || '').budget);
    const currency = message.currency || 'USD';
    const names = zh ? {flight: '機票', hotel: '住宿', food: '餐飲', transportation: '當地交通', activities: '活動', other: '雜支'} : costLabels;
    const rows = Object.entries(names).filter(([key]) => costs[key] != null).map(([key, name]) =>
      `| ${name} | ${currency} ${Number(costs[key]).toLocaleString()} |`);
    markdown += `\n\n## ${zh ? '完整費用分類' : 'Complete cost categories'}\n\n| ${zh ? '類別' : 'Category'} | ${zh ? '預估費用' : 'Estimated cost'} |\n| --- | ---: |\n` +
      rows.join('\n');
    if (message.total_cost != null) markdown += `\n| **${zh ? '總計' : 'Total'}** | **${currency} ${Number(message.total_cost).toLocaleString()}** |`;
  }
  return markdown.trim() + '\n';
}

function renderAnswer(message) {
  const card = el('article', 'message assistant-message');
  const zh = message.response_language === 'Traditional Chinese';
  card.append(el('div', 'assistant-eyebrow', zh ? '你的旅行計畫' : 'YOUR TRAVEL PLAN'));
  const sections = sectioned(message.response || '');
  textBlock(card, sections.intro, 'answer-text');
  if (sections.summary.some((line) => line.trim())) {
    card.append(el('h3', '', zh ? '行程摘要' : 'At a glance'));
    dayBlocks(card, sections.summary, 'summary-card');
  }
  if (sections.details.some((line) => line.trim())) {
    card.append(el('h3', '', zh ? '每日細節' : 'Day by day'));
    dayBlocks(card, sections.details, 'day-card');
  }
  renderLogistics(card, message.logistics, zh);
  if (message.costs) {
    const reconciled = renderCosts(card, message, sections.budget, zh);
    if (!reconciled && sections.budget.some((line) => line.trim())) {
      const original = el('details', 'cost-details');
      original.append(el('summary', '', zh ? '原始預算說明' : 'Original budget notes'));
      renderBudgetContent(original, sections.budget);
      card.append(original);
    }
  } else if (sections.budget.some((line) => line.trim())) {
    card.append(el('h3', '', zh ? '行程費用明細' : 'Cost details from the plan'));
    renderBudgetContent(card, sections.budget);
  }
  if (message.evaluation || message.costs || /\bDay\s+\d+\b|第[一二三四五六七八九十\d]+天/i.test(message.response || '')) {
    const edit = el('button', 'edit-export-button', zh ? '編輯與匯出 ↗' : 'Edit & export ↗');
    edit.type = 'button';
    edit.addEventListener('click', () => {
      const key = 'traveler_editor_draft';
      let existing;
      try { existing = JSON.parse(sessionStorage.getItem(key)); } catch (_) { existing = null; }
      if (existing?.sourceResponse !== message.response) {
        sessionStorage.setItem(key, JSON.stringify({
          title: currentDestination ? `${currentDestination} trip plan` : 'Trip plan',
          markdown: exportMarkdown(message),
          sourceResponse: message.response,
        }));
      }
      window.location.href = '/editor';
    });
    card.append(edit);
  }
  return card;
}

function userMessage(message) {
  const row = el('div', 'message user-message');
  const bubble = el('div', 'bubble', message.content || 'Please help me understand these images.');
  if (message.images?.length) {
    const imageList = el('div', 'message-images');
    message.images.forEach((name) => imageList.append(el('span', 'message-image', `▣ ${name}`)));
    bubble.append(imageList);
  }
  row.append(bubble);
  return row;
}

function renderMessages(messages) {
  messagesEl.replaceChildren();
  if (!messages?.length) {
    const welcome = el('div', 'welcome');
    const welcomeIcon = el('div', 'welcome-icon');
    const welcomeLogo = document.createElement('img');
    welcomeLogo.src = 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA0OCA0OCIgcm9sZT0iaW1nIiBhcmlhLWxhYmVsbGVkYnk9InRpdGxlIj4KICA8dGl0bGUgaWQ9InRpdGxlIj5UcmF2ZWxtYXRlIHJvdXRlIG1hcms8L3RpdGxlPgogIDxyZWN0IHdpZHRoPSI0OCIgaGVpZ2h0PSI0OCIgcng9IjEyIiBmaWxsPSIjMTk3NjVmIi8+CiAgPHBhdGggZD0iTTEyIDM0QzE4IDM0IDE2IDE5IDI2IDE5aDgiIGZpbGw9Im5vbmUiIHN0cm9rZT0iI2ZmZiIgc3Ryb2tlLXdpZHRoPSIzLjUiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIvPgogIDxjaXJjbGUgY3g9IjEyIiBjeT0iMzQiIHI9IjMuNSIgZmlsbD0iI2ZmZiIvPgogIDxwYXRoIGQ9Im0yOSAxMyA3IDYtNyA2IiBmaWxsPSJub25lIiBzdHJva2U9IiNmZmYiIHN0cm9rZS13aWR0aD0iMy41IiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiLz4KPC9zdmc+Cg==';
    welcomeLogo.alt = '';
    welcomeIcon.append(welcomeLogo);
    welcome.append(welcomeIcon, el('h3', '', 'Every great trip starts somewhere.'),
      el('p', '', "Tell me where you're going, your dates, your budget, or the kind of experience you want."));
    const chips = el('div', 'prompt-chips');
    [['A relaxed Seattle escape ↗', 'Plan a relaxed 3-day trip to Seattle with coffee and food stops.'],
     ['Plan around my budget ↗', 'Help me plan a weekend trip within a $1,000 budget.']].forEach(([label, prompt]) => {
      const button = el('button', '', label); button.dataset.prompt = prompt; chips.append(button);
    });
    welcome.append(chips); messagesEl.append(welcome); return;
  }
  for (const message of messages) {
    if (message.role === 'user') {
      messagesEl.append(userMessage(message));
    } else messagesEl.append(renderAnswer(message));
  }
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function renderActivity(messages, progress = null) {
  activityEl.replaceChildren();
  const groups = (messages || []).filter((message) => message.role === 'assistant' && message.activity?.length);
  if (progress?.active) {
    const group = el('div', 'activity-group');
    group.append(el('div', 'activity-group-title', 'CURRENT REQUEST'));
    for (const item of progress.activity || []) {
      const row = el('div', 'activity-item');
      const icon = item.status === 'warning' ? '!' : item.status === 'progress' ? '↻' : '✓';
      row.append(el('span', `activity-icon ${item.status}`, icon), el('span', '', item.label));
      group.append(row);
    }
    const row = el('div', 'activity-item');
    row.append(el('span', 'activity-icon progress', '…'), el('span', '', progress.label));
    group.append(row);
    activityEl.append(group);
  }
  if (!groups.length && !progress?.active) { activityEl.append(el('div', 'activity-empty', 'Searches and planning updates will show here.')); return; }
  groups.reverse().forEach((message, index) => {
    const group = el('div', 'activity-group');
    group.append(el('div', 'activity-group-title', index === 0 ? 'LATEST RESPONSE' : 'EARLIER RESPONSE'));
    message.activity.forEach((item) => {
      const row = el('div', 'activity-item');
      const icon = item.status === 'warning' ? '!' : item.status === 'progress' ? '↻' : '✓';
      row.append(el('span', `activity-icon ${item.status}`, icon), el('span', '', item.label)); group.append(row);
    });
    for (const search of message.flight_searches || []) {
      const details = el('details', 'flight-search-details');
      details.append(el('summary', '', `Flight search · ${search.query?.origin || '?'} → ${search.query?.destination || '?'} · ${search.query?.departure_date || 'date unknown'}`));
      const filters = search.query || {};
      details.append(el('p', '', `Return: ${filters.return_date || 'one-way'} · Travelers priced: ${filters.adults || 1} adult${filters.adults === 1 ? '' : 's'} · Currency: ${filters.currency || 'default'} · Nonstop: ${filters.nonstop ? 'yes' : 'no'} · Sort: ${filters.sorted_by || 'provider default'} · Price cap: ${filters.max_price ?? 'none'}`));
      const formatOption = (option) => {
        const identity = [option.airline, option.flight_number].filter(Boolean).join(' ');
        return `${option.route} · ${option.departure || '?'} → ${option.arrival || '?'} · ${identity || 'airline unknown'} · ${option.price == null ? 'price unavailable' : `${filters.currency || ''} ${Number(option.price).toLocaleString()}`}${option.stops == null ? '' : ` · ${option.stops} stop${option.stops === 1 ? '' : 's'}`}`;
      };
      if (search.error) details.append(el('p', 'budget-note over', search.error));
      if (search.outbound_options?.length) {
        details.append(el('h4', '', 'Outbound results (initial displayed fares)'));
        for (const option of search.outbound_options) details.append(el('p', '', formatOption(option)));
      }
      for (const pair of search.paired_options || []) {
        details.append(el('h4', '', `Paired returns for ${formatOption(pair.outbound)}`));
        for (const option of pair.returns) details.append(el('p', '', formatOption(option)));
      }
      if (search.return_search_status) details.append(el('p', 'budget-note over', search.return_search_status));
      if (search.independent_returns?.length) {
        details.append(el('h4', '', 'Independent one-way return options'));
        for (const option of search.independent_returns) details.append(el('p', '', formatOption(option)));
      }
      group.append(details);
    }
    activityEl.append(group);
  });
}

async function request(path, options = {}) {
  const response = await fetch(path, {headers: {'Content-Type': 'application/json'}, ...options});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Request failed');
  return data;
}

function render(data) {
  currentDestination = data.memory?.trip_state?.destination || '';
  currentMessages = data.messages || [];
  renderState(data.memory);
  renderMessages(data.messages);
  renderActivity(data.messages);
}

function resizePrompt() {
  promptEl.style.height = 'auto';
  const maxHeight = Math.min(180, window.innerHeight * 0.35);
  promptEl.style.height = `${Math.min(promptEl.scrollHeight, maxHeight)}px`;
  promptEl.style.overflowY = promptEl.scrollHeight > maxHeight ? 'auto' : 'hidden';
}

promptEl.addEventListener('input', resizePrompt);
window.addEventListener('resize', resizePrompt);
resizePrompt();

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const prompt = promptEl.value.trim(); if (!prompt && !selectedImages.length) return;
  const queuedImages = selectedImages;
  const welcome = messagesEl.querySelector('.welcome');
  if (welcome) welcome.remove();
  const optimistic = userMessage({content: prompt, images: queuedImages.map((file) => file.name)});
  messagesEl.append(optimistic);
  promptEl.value = ''; resizePrompt(); selectedImages = []; renderAttachments();
  sendEl.disabled = true; promptEl.disabled = true;
  const pending = el('div', 'loading', 'Planning your trip…');
  messagesEl.append(pending); messagesEl.scrollTop = messagesEl.scrollHeight;
  let progressTimer;
  let finished = false;
  try {
    const images = await Promise.all(queuedImages.map(async (file) => ({name: file.name, data_url: await dataUrl(file)})));
    const response = request('/api/chat', {method: 'POST', body: JSON.stringify({prompt, images})});
    const updateProgress = async () => {
      try {
        const progress = await request('/api/progress');
        if (!finished && progress.active) {
          pending.textContent = `${progress.label}…`;
          renderActivity(currentMessages, progress);
        }
      } catch (_) { /* Keep the last visible stage until the chat response arrives. */ }
    };
    progressTimer = setInterval(updateProgress, 700);
    const data = await response;
    render(data);
  } catch (error) {
    optimistic.remove(); pending.replaceWith(el('div', 'error', error.message));
    promptEl.value = prompt; resizePrompt(); selectedImages = queuedImages; renderAttachments();
    renderActivity(currentMessages);
  }
  finally {
    finished = true;
    clearInterval(progressTimer);
    sendEl.disabled = false; promptEl.disabled = false; promptEl.focus();
  }
});

promptEl.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); form.requestSubmit(); }
});
messagesEl.addEventListener('click', (event) => {
  const preset = event.target.closest('[data-prompt]');
  if (preset) { promptEl.value = preset.dataset.prompt; resizePrompt(); promptEl.focus(); }
});
$('#reset').addEventListener('click', async () => {
  try { render(await request('/api/reset', {method: 'POST', body: '{}'})); }
  catch (error) { alert(error.message); }
});
$('#activity-toggle').addEventListener('click', () => {
  const expanded = $('#activity-toggle').getAttribute('aria-expanded') === 'true';
  $('#activity-toggle').setAttribute('aria-expanded', String(!expanded));
  $('#activity-toggle').textContent = expanded ? '+' : '−';
  activityEl.hidden = expanded;
});
request('/api/state').then(render).catch((error) => { messagesEl.append(el('div', 'error', error.message)); });
