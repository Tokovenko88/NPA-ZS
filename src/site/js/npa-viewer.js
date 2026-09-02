let NPA_STATIC_DATA = null;
let NPA_NO_NAME_IDS = null;
function loadStaticData() {
    const dataEl = document.getElementById('npa-static-data');
    if (!dataEl) {
        console.warn('npa-static-data not found');
        return false;
    }
    try {
        NPA_STATIC_DATA = JSON.parse(dataEl.textContent);
        if (NPA_STATIC_DATA && NPA_STATIC_DATA.no_name_ids) {
            NPA_NO_NAME_IDS = NPA_STATIC_DATA.no_name_ids;
        }
        return true;
    } catch (e) {
        console.error('Parse error', e);
        return false;
    }
}
function extractHighlightItem(item) {
    if (!item) return { phrase: '', identifier: null };
    if (typeof item === 'string') return { phrase: item, identifier: null };
    if (Array.isArray(item)) return { phrase: item[0] || '', identifier: item.length > 1 ? item[1] : null };
    if (typeof item === 'object') {
        return {
            phrase: item.text || item.phrase || '',
            identifier: item.positions || item.position || item.identifier || null
        };
    }
    return { phrase: '', identifier: null };
}
function getPrecomputedRevision(revId, itemId, context) {
    context = context || 'item';
    if (!NPA_STATIC_DATA || !NPA_STATIC_DATA.revisionContents) return null;
    let key = (context === 'head') ? (itemId === 'head' || !itemId ? `head_${revId}` : `head_item_${itemId}_${revId}`) : `item_${itemId}_${revId}`;
    return NPA_STATIC_DATA.revisionContents[key] || null;
}
function getPrecomputedHistory(itemId, context) {
    context = context || 'item';
    if (!NPA_STATIC_DATA || !NPA_STATIC_DATA.precomputed || !NPA_STATIC_DATA.precomputed.histories) return null;
    let key = (context === 'head') ? (itemId === 'head' ? 'head' : `head:${itemId}`) : itemId;
    return NPA_STATIC_DATA.precomputed.histories[key] || null;
}
function getPrecomputedCompare(itemId, context) {
    context = context || 'item';
    if (!NPA_STATIC_DATA || !NPA_STATIC_DATA.precomputed || !NPA_STATIC_DATA.precomputed.compares) return null;
    let key = (context === 'head') ? (itemId === 'head' ? 'head' : `head:${itemId}`) : itemId;
    return NPA_STATIC_DATA.precomputed.compares[key] || null;
}
function npaGetViewDateSql() {
    if (NPA_STATIC_DATA && NPA_STATIC_DATA.view_date) return String(NPA_STATIC_DATA.view_date).slice(0, 10);
    const d = new Date();
    const p2 = n => String(n).padStart(2, '0');
    return d.getFullYear() + '-' + p2(d.getMonth() + 1) + '-' + p2(d.getDate());
}
function npaNormalizeDateToSql(v) {
    const s = String(v || '').trim();
    if (!s) return '';
    let m = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
    if (m) return m[1] + '-' + String(m[2]).padStart(2, '0') + '-' + String(m[3]).padStart(2, '0');
    m = s.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})/);
    if (m) return m[3] + '-' + String(m[2]).padStart(2, '0') + '-' + String(m[1]).padStart(2, '0');
    return s.slice(0, 10);
}
function npaIsRevExpiredForView(validTo) {
    const v = npaNormalizeDateToSql(validTo);
    if (!v) return false;
    return v < npaGetViewDateSql();
}
function isItemExpired(itemId, context) {
    context = context || 'item';
    const histData = getPrecomputedHistory(itemId, context);
    if (histData && histData.success && histData.revisions && histData.revisions.length > 0) {
        const lastRev = histData.revisions[histData.revisions.length - 1];
        if (lastRev.is_current !== undefined && lastRev.is_current !== null) {
            return !lastRev.is_current;
        }
        return false;
    }
    const block = document.querySelector(`.npa-item-block[data-npa-item-id="${itemId}"]`);
    if (block) {
        return block.classList.contains('npa-expired-block');
    }
    return false;
}
function normalizeHighlightText(text) {
    if (!text) return '';
    if (typeof text !== 'string') {
        if (Array.isArray(text) && text.length > 0 && typeof text[0] === 'string') {
            text = text[0];
        } else {
            return '';
        }
    }
    return text.replace(/[–—‑‐]/g, '-').replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim();
}
function parseHighlightIdentifier(identifier) {
    if (typeof identifier !== 'string') return null;
    if (identifier.match(/^\d+-all$/i)) {
        const m = identifier.match(/^(\d+)-all$/i);
        if (m) return { paragraph: parseInt(m[1], 10), occurrence: 'all' };
    }
    const m = identifier.match(/^(\d+)-(\d+)$/);
    if (m) return { paragraph: parseInt(m[1], 10), occurrence: [parseInt(m[2], 10)] };
    return null;
}
function parseMultiIdentifier(identifier) {
    if (!identifier) return [null];
    if (typeof identifier === 'object') return [identifier];
    const parts = identifier.split(',');
    const map = new Map();
    for (const part of parts) {
        const match = part.trim().match(/^(\d+)-(\d+)$/);
        if (match) {
            const p = parseInt(match[1]);
            const o = parseInt(match[2]);
            if (!map.has(p)) map.set(p, []);
            map.get(p).push(o);
        } else {
            return [parseHighlightIdentifier(identifier)];
        }
    }
    const result = [];
    for (const [p, o] of map) {
        result.push({ paragraph: p, occurrence: o });
    }
    return result.length ? result : [null];
}
function parseTablePositions(positionsStr) {
    if (!positionsStr || typeof positionsStr !== 'string') return [];
    return positionsStr.split(',')
        .map(p => parseInt(p.trim(), 10))
        .filter(n => !isNaN(n) && n > 0);
}
function buildFlexibleRegex(phrase) {
    let escaped = phrase.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    let flexible = escaped.replace(/\s+/g, '(?:\\s|&nbsp;)+').replace(/[‐‑–—-]/g, '[\\u2010-\\u2015-]');
    return new RegExp(flexible, 'gi');
}
function cleanHighlightTags(container) {
    const removables = container.querySelectorAll('ins.npa-highlight, del.npa-highlight, span.npa-highlight, span[data-pair-id]');
    removables.forEach(el => {
        const parent = el.parentNode;
        while (el.firstChild) parent.insertBefore(el.firstChild, el);
        parent.removeChild(el);
        parent.normalize();
    });
}
function getAllTextNodes(container) {
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, {
        acceptNode: (node) => {
            if (node.parentElement && (node.parentElement.tagName === 'SCRIPT' || node.parentElement.tagName === 'STYLE')) return NodeFilter.FILTER_REJECT;
            return NodeFilter.FILTER_ACCEPT;
        }
    });
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    return nodes;
}
function findNthOccurrence(text, phrase, n) {
    if (n === 'all') {
        const ranges = [];
        const regex = buildFlexibleRegex(phrase);
        let match;
        while ((match = regex.exec(text)) !== null) {
            ranges.push({ start: match.index, end: match.index + match[0].length });
        }
        return ranges;
    }
    let count = 0;
    const regex = buildFlexibleRegex(phrase);
    let match;
    while ((match = regex.exec(text)) !== null) {
        count++;
        if (count === n) {
            return [{ start: match.index, end: match.index + match[0].length }];
        }
    }
    return [];
}
function collectRangesFromTextNodeSimple(text, highlightList, paragraphIndex) {
    const ranges = [];
    for (const rule of highlightList) {
        let targetOccurrences = null;
        let targetParagraph = null;
        if (rule.identifier && typeof rule.identifier === 'object') {
            targetParagraph = rule.identifier.paragraph;
            targetOccurrences = rule.identifier.occurrence;
        }
        if (targetParagraph !== null && targetParagraph !== undefined && targetParagraph !== paragraphIndex) {
            continue;
        }
        let occurrenceNumbers = [];
        if (targetOccurrences === 'all' || (Array.isArray(targetOccurrences) && targetOccurrences.length === 1 && targetOccurrences[0] === 'all')) {
            occurrenceNumbers = ['all'];
        } else if (Array.isArray(targetOccurrences) && targetOccurrences.length) {
            occurrenceNumbers = targetOccurrences;
        } else if (typeof targetOccurrences === 'number') {
            occurrenceNumbers = [targetOccurrences];
        } else {
            occurrenceNumbers = null;
        }
        if (occurrenceNumbers) {
            for (const occ of occurrenceNumbers) {
                const occRanges = findNthOccurrence(text, rule.phrase, occ);
                for (const r of occRanges) {
                    ranges.push({ start: r.start, end: r.end, rule: rule });
                }
            }
        } else {
            const regex = buildFlexibleRegex(rule.phrase);
            let match;
            while ((match = regex.exec(text)) !== null) {
                ranges.push({ start: match.index, end: match.index + match[0].length, rule: rule });
            }
        }
    }
    if (ranges.length === 0) return [];
    ranges.sort((a, b) => a.start - b.start);
    const merged = [];
    for (const range of ranges) {
        if (merged.length === 0) {
            merged.push(range);
            continue;
        }
        const last = merged[merged.length - 1];
        if (range.start <= last.end) {
            last.end = Math.max(last.end, range.end);
            if (!last.rule.pairId && range.rule.pairId) last.rule.pairId = range.rule.pairId;
            const typePriority = { 'insert': 3, 'delete': 2, 'difference': 1 };
            const lastP = typePriority[last.rule.type] || 0;
            const rangeP = typePriority[range.rule.type] || 0;
            if (rangeP > lastP) {
                last.rule.type = range.rule.type;
            }
        } else {
            merged.push(range);
        }
    }
    return merged;
}
function applyRangesToTextNode(node, ranges) {
    if (ranges.length === 0) return;
    const text = node.nodeValue;
    const fragments = [];
    let lastIndex = 0;
    for (const range of ranges) {
        if (range.start > lastIndex) {
            fragments.push(document.createTextNode(text.substring(lastIndex, range.start)));
        }
        const span = document.createElement('span');
        span.className = 'npa-highlight';
        if (range.rule.type === 'insert') span.classList.add('npa-diff-insert');
        else if (range.rule.type === 'delete') span.classList.add('npa-diff-delete');
        else if (range.rule.type === 'difference') span.classList.add('npa-diff-difference');
        if (range.rule.pairId) span.setAttribute('data-pair-id', range.rule.pairId);
        span.textContent = text.substring(range.start, range.end);
        fragments.push(span);
        lastIndex = range.end;
    }
    if (lastIndex < text.length) {
        fragments.push(document.createTextNode(text.substring(lastIndex)));
    }
    const parent = node.parentNode;
    for (const frag of fragments) {
        parent.insertBefore(frag, node);
    }
    parent.removeChild(node);
    parent.normalize();
}
function applyAllHighlightsToParagraphs(paragraphs, highlightList) {
    const allRuleMap = new Map();
    for (const rule of highlightList) {
        if (rule.identifier && typeof rule.identifier === 'object' && rule.identifier.occurrence === 'all') {
            const paraIdx = rule.identifier.paragraph;
            if (paraIdx !== null && paraIdx !== undefined) {
                allRuleMap.set(paraIdx, rule);
            }
        }
    }
    if (allRuleMap.size === 0) return highlightList;
    for (let i = 0; i < paragraphs.length; i++) {
        const para = paragraphs[i];
        const paraIndex = i + 1;
        const rule = allRuleMap.get(paraIndex);
        if (!rule) continue;
        const wrapper = document.createElement('span');
        wrapper.className = 'npa-highlight-block';
        if (rule.type === 'delete') {
            wrapper.classList.add('npa-diff-delete');
        } else if (rule.type === 'difference') {
            wrapper.classList.add('npa-diff-difference');
            if (rule.pairId) {
                wrapper.setAttribute('data-pair-id', rule.pairId);
            }
        } else if (rule.type === 'insert') {
            wrapper.classList.add('npa-diff-insert');
        }
        while (para.firstChild) {
            wrapper.appendChild(para.firstChild);
        }
        para.appendChild(wrapper);
    }
    return highlightList.filter(rule => {
        if (rule.identifier && typeof rule.identifier === 'object' && rule.identifier.occurrence === 'all') {
            return false;
        }
        return true;
    });
}
function applyTableHighlights(container, rules) {
    if (!rules.length) return;
    const rows = Array.from(container.querySelectorAll('tr'));
    if (!rows.length) return;
    for (const rule of rules) {
        const { type, positions, pairId } = rule;
        if (!positions.length) continue;
        for (const rowIndex of positions) {
            const idx = rowIndex - 1;
            if (idx < 0 || idx >= rows.length) continue;
            const tr = rows[idx];
            tr.classList.remove('npa-diff-insert', 'npa-diff-delete', 'npa-diff-difference');
            if (pairId) tr.removeAttribute('data-pair-id');
            if (type === 'insert') {
                tr.classList.add('npa-diff-insert');
            } else if (type === 'delete') {
                tr.classList.add('npa-diff-delete');
            } else if (type === 'difference' && pairId) {
                tr.classList.add('npa-diff-difference');
                tr.setAttribute('data-pair-id', pairId);
            }
        }
    }
}
function getDirectParagraphs(container, context) {
    const allParagraphs = Array.from(container.querySelectorAll('p, div:not(.npa-highlight)'));
    return allParagraphs.filter(el => {
        if (el.classList.contains('npa-item-block') || el.classList.contains('npa-para-sep')) return false;
        if (context === 'item') {
            const isHeading = el.classList.contains('npa-article') || 
                              el.classList.contains('npa-chapter') || 
                              el.classList.contains('npa-section') || 
                              el.classList.contains('npa-appendix');
            if (isHeading) return false;
            const text = el.textContent.trim();
            if (/^(Статья|Глава|Раздел|Приложение)\s+[\dIVXLCDMа-яА-ЯёЁ¹²³⁴⁵⁶⁷⁸⁹⁰]+/iu.test(text)) {
                return false;
            }
        }
        const closestBlock = el.closest('.npa-item-block');
        if (container.classList.contains('npa-item-block')) {
            return closestBlock === container;
        } else {
            return !closestBlock;
        }
    });
}
function buildHighlightList(highlights, side, itemIdPrefix) {
    const list = [];
    if (side === 'old') {
        const prevDels = (highlights.previous_edition && (highlights.previous_edition.deletion || highlights.previous_edition.Delete)) || [];
        prevDels.forEach(item => {
            const { phrase: rawPhrase, identifier } = extractHighlightItem(item);
            const phrase = normalizeHighlightText(rawPhrase);
            if (phrase === 'table') {
                const positions = parseTablePositions(identifier);
                if (positions.length) list.push({ phrase: 'table', identifier: positions, type: 'delete', pairId: null });
            } else if (phrase) {
                const parsedIds = parseMultiIdentifier(identifier);
                parsedIds.forEach(pid => list.push({ phrase, identifier: pid, type: 'delete', pairId: null }));
            }
        });
        const pDiffs = (highlights.previous_edition && highlights.previous_edition.difference) || [];
        const cDiffs = (highlights.current_edition && highlights.current_edition.difference) || [];
        const maxDiff = Math.max(pDiffs.length, cDiffs.length);
        for (let i = 0; i < maxDiff; i++) {
            const pairId = `${itemIdPrefix || 'diff-pair'}-${i}`;
            if (pDiffs[i]) {
                const { phrase: rawPhrase, identifier } = extractHighlightItem(pDiffs[i]);
                const phrase = normalizeHighlightText(rawPhrase);
                if (phrase === 'table') {
                    const positions = parseTablePositions(identifier);
                    if (positions.length) list.push({ phrase: 'table', identifier: positions, type: 'difference', pairId });
                } else if (phrase) {
                    const parsedIds = parseMultiIdentifier(identifier);
                    parsedIds.forEach(pid => list.push({ phrase, identifier: pid, type: 'difference', pairId }));
                }
            }
        }
    } else if (side === 'new') {
        const cAdds = (highlights.current_edition && (highlights.current_edition.addition || highlights.current_edition.additional)) || [];
        cAdds.forEach(item => {
            const { phrase: rawPhrase, identifier } = extractHighlightItem(item);
            const phrase = normalizeHighlightText(rawPhrase);
            if (phrase === 'table') {
                const positions = parseTablePositions(identifier);
                if (positions.length) list.push({ phrase: 'table', identifier: positions, type: 'insert', pairId: null });
            } else if (phrase) {
                const parsedIds = parseMultiIdentifier(identifier);
                parsedIds.forEach(pid => list.push({ phrase, identifier: pid, type: 'insert', pairId: null }));
            }
        });
        const pDiffs = (highlights.previous_edition && highlights.previous_edition.difference) || [];
        const cDiffs = (highlights.current_edition && highlights.current_edition.difference) || [];
        const maxDiff = Math.max(pDiffs.length, cDiffs.length);
        for (let i = 0; i < maxDiff; i++) {
            const pairId = `${itemIdPrefix || 'diff-pair'}-${i}`;
            if (cDiffs[i]) {
                const { phrase: rawPhrase, identifier } = extractHighlightItem(cDiffs[i]);
                const phrase = normalizeHighlightText(rawPhrase);
                if (phrase === 'table') {
                    const positions = parseTablePositions(identifier);
                    if (positions.length) list.push({ phrase: 'table', identifier: positions, type: 'difference', pairId });
                } else if (phrase) {
                    const parsedIds = parseMultiIdentifier(identifier);
                    parsedIds.forEach(pid => list.push({ phrase, identifier: pid, type: 'difference', pairId }));
                }
            }
        }
    }
    return list;
}
function applyHighlightsToDom(container, highlightList, context) {
    if (!highlightList || !highlightList.length) return;
    const textRules = [];
    const tableRules = [];
    for (const rule of highlightList) {
        if (rule.phrase === 'table') {
            tableRules.push({
                type: rule.type,
                positions: rule.identifier && Array.isArray(rule.identifier) ? rule.identifier : [],
                pairId: rule.pairId || null
            });
        } else {
            textRules.push(rule);
        }
    }
    if (textRules.length) {
        const paragraphs = getDirectParagraphs(container, context);
        const remainingRules = applyAllHighlightsToParagraphs(paragraphs, textRules);
        if (remainingRules.length) {
            let paraIndex = 1;
            for (const para of paragraphs) {
                const textNodes = getAllTextNodes(para);
                for (const node of textNodes) {
                    const ranges = collectRangesFromTextNodeSimple(node.nodeValue, remainingRules, paraIndex);
                    if (ranges.length) applyRangesToTextNode(node, ranges);
                }
                paraIndex++;
            }
        }
    }
    if (tableRules.length) {
        applyTableHighlights(container, tableRules);
    }
}
function normalizeBlockDirectText(block) {
    if (!block) return '';
    const clone = block.cloneNode(true);
    clone.querySelectorAll('.npa-item-block, .npa-highlight-block, .npa-highlight, .npa-expired-block, .npa-expired-label, [class*="npa-diff-"], [data-pair-id]').forEach(function(el) {
        if (el.parentNode) el.parentNode.removeChild(el);
    });
    return (clone.textContent || '').replace(/\s+/g, ' ').trim();
}
function applyChildBlockHighlights(container, side, rootItemId, otherContainer, parentCompareData) {
    if (!parentCompareData || !parentCompareData.success) return;
    // Если весь корневой элемент добавлен / удалён / переиздан целиком,
    // дочерние элементы уже покрыты блоковым выделением родителя.
    const rootModType = parentCompareData.mod_type;
    if (rootModType === 'add' || rootModType === 'delete' || rootModType === 'new_redaction') return;
    const blocks = Array.from(container.querySelectorAll('.npa-item-block[data-npa-item-id]'));
    blocks.reverse();
    for (const block of blocks) {
        const itemId = block.getAttribute('data-npa-item-id');
        if (itemId === rootItemId) continue;
        const compareData = getPrecomputedCompare(itemId, 'item');
        let childHighlights = null;
        let childModType = null;
        let isRelevantChange = false;
        const existsInOther = otherContainer ? !!otherContainer.querySelector(`.npa-item-block[data-npa-item-id="${itemId}"]`) : true;
        if (!existsInOther) {
            if (side === 'old') childModType = 'delete';
            else childModType = 'add';
            isRelevantChange = true;
        } else if (compareData && compareData.success) {
            // Подсветку дочернего элемента применяем только если его собственный
            // контент (без вложенных блоков) реально отличается между колонками.
            // Это позволяет рекурсивно показывать изменения любых вложенных элементов
            // (в т.ч. когда родитель не менялся, а менялись только дети) и не
            // дублировать выделения, уже покрытые блоковым diff более глубоких элементов.
            const otherBlock = otherContainer ? otherContainer.querySelector(`.npa-item-block[data-npa-item-id="${itemId}"]`) : null;
            if (!otherBlock || normalizeBlockDirectText(block) !== normalizeBlockDirectText(otherBlock)) {
                isRelevantChange = true;
                childHighlights = compareData.highlights;
                childModType = (compareData.mod_type === 'new_redaction') ? 'new_redaction' : 'change';
            }
        }
        if (!isRelevantChange) {
            continue;
        }
        if (childModType === 'delete' && side === 'old') {
            const wrapper = document.createElement('del');
            wrapper.className = 'npa-diff-delete npa-diff-block';
            while (block.firstChild) wrapper.appendChild(block.firstChild);
            block.appendChild(wrapper);
        } else if (childModType === 'add' && side === 'new') {
            const wrapper = document.createElement('ins');
            wrapper.className = 'npa-diff-insert npa-diff-block';
            while (block.firstChild) wrapper.appendChild(block.firstChild);
            block.appendChild(wrapper);
        } else if (childModType === 'new_redaction') {
            const wrapper = document.createElement(side === 'old' ? 'del' : 'ins');
            wrapper.className = side === 'old' ? 'npa-diff-delete npa-diff-block' : 'npa-diff-insert npa-diff-block';
            while (block.firstChild) wrapper.appendChild(block.firstChild);
            block.appendChild(wrapper);
        } else {
            if (childHighlights && typeof childHighlights === 'object') {
                const list = buildHighlightList(childHighlights, side, `diff-pair-child-${itemId}`);
                if (list.length > 0) {
                    applyHighlightsToDom(block, list, 'item');
                }
            }
        }
    }
}
function applyPreciseHighlights(oldHtml, newHtml, highlights, modType, rootItemId, context, parentCompareData) {
    const prevContainer = document.createElement('div');
    prevContainer.innerHTML = oldHtml;
    cleanHighlightTags(prevContainer);
    const currContainer = document.createElement('div');
    currContainer.innerHTML = newHtml;
    cleanHighlightTags(currContainer);
    const prevRootBlock = rootItemId ? prevContainer.querySelector(`.npa-item-block[data-npa-item-id="${rootItemId}"]`) : null;
    const currRootBlock = rootItemId ? currContainer.querySelector(`.npa-item-block[data-npa-item-id="${rootItemId}"]`) : null;
    let prevHighlights = [];
    let currHighlights = [];
    if (highlights && typeof highlights === 'object') {
        prevHighlights = buildHighlightList(highlights, 'old', 'diff-pair');
        currHighlights = buildHighlightList(highlights, 'new', 'diff-pair');
    }
    if (prevHighlights.length > 0 || currHighlights.length > 0) {
        applyHighlightsToDom(prevRootBlock || prevContainer, prevHighlights, context);
        applyHighlightsToDom(currRootBlock || currContainer, currHighlights, context);
    } else if (modType === 'new_redaction') {
        const prevWrapper = document.createElement('del');
        prevWrapper.className = 'npa-diff-delete npa-diff-block';
        const prevTarget = prevRootBlock || prevContainer;
        while (prevTarget.firstChild) prevWrapper.appendChild(prevTarget.firstChild);
        prevTarget.appendChild(prevWrapper);
        const currWrapper = document.createElement('ins');
        currWrapper.className = 'npa-diff-insert npa-diff-block';
        const currTarget = currRootBlock || currContainer;
        while (currTarget.firstChild) currWrapper.appendChild(currTarget.firstChild);
        currTarget.appendChild(currWrapper);
    } else if (modType === 'add') {
        const currWrapper = document.createElement('ins');
        currWrapper.className = 'npa-diff-insert npa-diff-block';
        const currTarget = currRootBlock || currContainer;
        while (currTarget.firstChild) currWrapper.appendChild(currTarget.firstChild);
        currTarget.appendChild(currWrapper);
    } else if (modType === 'delete') {
        const prevWrapper = document.createElement('del');
        prevWrapper.className = 'npa-diff-delete npa-diff-block';
        const prevTarget = prevRootBlock || prevContainer;
        while (prevTarget.firstChild) prevWrapper.appendChild(prevTarget.firstChild);
        prevTarget.appendChild(prevWrapper);
    }
    applyChildBlockHighlights(prevContainer, 'old', rootItemId, currContainer, parentCompareData);
    applyChildBlockHighlights(currContainer, 'new', rootItemId, prevContainer, parentCompareData);
    return { old: prevContainer.innerHTML, new: currContainer.innerHTML };
}
function formatArticleHeadings(html) {
    if (!html) return html;
    const div = document.createElement('div');
    div.innerHTML = html;
    const isInsideNoName = (itemBlock) => {
        if (!NPA_NO_NAME_IDS || !NPA_NO_NAME_IDS.length) return false;
        let current = itemBlock;
        while (current) {
            const id = current.getAttribute('data-npa-item-id');
            if (id && NPA_NO_NAME_IDS.includes(id)) return true;
            const type = current.getAttribute('data-item-type');
            if (type === 'appendix' || type === 'nested_appendix') break;
            current = current.parentElement?.closest('.npa-item-block');
        }
        return false;
    };
    div.querySelectorAll('p').forEach(p => {
        if (p.classList.contains('npa-article') || p.classList.contains('npa-chapter') ||
            p.classList.contains('npa-section') || p.classList.contains('npa-appendix') ||
            p.classList.contains('npa-num-processed')) return;
        const text = p.textContent.trim();
        const chapterMatch = text.match(/^((?:Глава)\s+[\dIVXLCDMа-яА-ЯёЁ¹²³⁴⁵⁶⁷⁸⁹⁰]+)([\.\)]?)\s*(.*)$/iu);
        if (chapterMatch) {
            p.classList.add('npa-chapter', 'npa-num-processed');
            p.innerHTML = `<span class="npa-chapter-num">${chapterMatch[1]}${chapterMatch[2]}</span><span class="npa-chapter-title">${chapterMatch[3] || ''}</span>`;
            return;
        }
        const sectionMatch = text.match(/^((?:Раздел)\s+[\dIVXLCDMа-яА-ЯёЁ¹²³⁴⁵⁶⁷⁸⁹⁰]+)([\.\)]?)\s*(.*)$/iu);
        if (sectionMatch) {
            p.classList.add('npa-section', 'npa-num-processed');
            const itemBlock = p.closest('.npa-item-block');
            const skipPrefix = itemBlock ? isInsideNoName(itemBlock) : false;
            let numPart = sectionMatch[1];
            const punctuation = sectionMatch[2];
            const titlePart = sectionMatch[3] || '';
            if (skipPrefix) {
                numPart = numPart.replace(/^Раздел\s+/i, '');
                p.innerHTML = `<span class="npa-section-num no-name-prefix">${numPart}${punctuation}</span><span class="npa-section-title">${titlePart}</span>`;
            } else {
                p.innerHTML = `<span class="npa-section-num">${sectionMatch[1]}${punctuation}</span><span class="npa-section-title">${titlePart}</span>`;
            }
            return;
        }
        const articleMatch = text.match(/^((?:Статья|Приложение)\s+[\dIVXLCDMа-яА-ЯёЁ¹²³⁴⁵⁶⁷⁸⁹⁰]+(?:[.\)]\d+)*)([\.\)]?)\s*(.*)$/iu);
        if (articleMatch) {
            p.classList.add('npa-article', 'npa-num-processed');
            p.innerHTML = `<span class="npa-article-num">${articleMatch[1]}${articleMatch[2]}</span><span class="npa-article-title">${articleMatch[3] || ''}</span>`;
            return;
        }
        const appendixMatch = text.match(/^((?:Приложение)\s*[\dIVXLCDMа-яА-ЯёЁ¹²³⁴⁵⁶⁷⁸⁹⁰]*)([\.\)]?)\s*$/iu);
        if (appendixMatch) {
            p.classList.add('npa-appendix', 'npa-num-processed');
            p.innerHTML = `<span class="npa-appendix-num">${appendixMatch[1]}${appendixMatch[2]}</span>`;
            return;
        }
    });
    return div.innerHTML;
}
function getExpiredRevisionTitle(baseText, dateFrom, toStr) {
    let head;
    if (baseText === 'Наименование') {
        head = 'Последнее действующее наименование';
    } else if (baseText === 'Заголовок') {
        head = 'Последний действующий заголовок';
    } else {
        head = 'Последняя действующая редакция';
    }
    return head + (dateFrom ? ', с ' + dateFrom : '') + (toStr || '');
}
function getRevisionTitle(dateFrom, dateTo, isCurrent, context, itemId, isLastExpired) {
    context = context || 'item';
    let baseText = (context === 'head' && itemId === 'head') ? 'Наименование' : (context === 'head') ? 'Заголовок' : 'Редакция';
    let toStr = dateTo ? ' по ' + dateTo : '';
    if (context === 'head' && itemId !== 'head') {
        if (isCurrent && !dateTo) return baseText + ', действующий с ' + dateFrom;
        if (isLastExpired) return getExpiredRevisionTitle(baseText, dateFrom, toStr);
        return baseText + ', действовавший с ' + dateFrom + toStr;
    } else {
        if (isCurrent && !dateTo) return baseText + ', действующая с ' + dateFrom;
        if (isLastExpired) return getExpiredRevisionTitle(baseText, dateFrom, toStr);
        return baseText + ', действовавшая с ' + dateFrom + toStr;
    }
}
function npaFetchRevision(revId, itemId, npaId, titlePrefix, sourceText, context) {
    context = context || 'item';
    const data = getPrecomputedRevision(revId, itemId, context);
    if (!data || !data.success) {
        alert('Редакция не найдена');
        return;
    }
    const histData = getPrecomputedHistory(itemId, context);
    const isLast = histData && histData.revisions && String(histData.revisions[histData.revisions.length - 1].rev_id) === String(revId);
    const isBlockExpired = isItemExpired(itemId, context);
    const isExpired = isLast && (npaIsRevExpiredForView(data.valid_to) || isBlockExpired || data.is_current === false);
    const isCurrent = !isExpired && data.is_current !== false;
    let dateTo = data.valid_to;
    if (!dateTo && isExpired && isBlockExpired) {
        const block = document.querySelector(`.npa-item-block[data-npa-item-id="${itemId}"]`);
        if (block) {
            const dateEl = block.querySelector(':scope > .npa-view-expired') || block.querySelector(':scope > .element-valid-from');
            if (dateEl) {
                const m = (dateEl.dataset.notValidDate || dateEl.textContent || '').match(/(\d{2}\.\d{2}\.\d{4}|\d{4}-\d{2}-\d{2})/);
                if (m) dateTo = m[1];
            }
        }
    }
    const title = getRevisionTitle(data.valid_from, dateTo, isCurrent, context, itemId, isExpired && isLast);
    let info = '';
    if (data.doc_note) {
        let noteText = data.doc_note;
        if (data.npa_url && data.display_title) {
            const npaLink = '<a href="' + escapeHtml(data.npa_url) + '" target="_blank" class="npa-revision-link">' + escapeHtml(data.display_title) + '</a>';
            const regex = new RegExp(escapeRegex(data.display_title), 'i');
            noteText = regex.test(noteText) ? noteText.replace(regex, npaLink) : noteText + ' ' + npaLink;
        }
        info = '<div class="revision-meta">' + noteText + '</div>';
    }
    npaShowModal(title, info + (data.html || data.content || '<p>Содержимое отсутствует</p>'), false);
}
function escapeRegex(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
function npaShowHistory(itemId, npaId, context) {
    context = context || 'item';
    const data = getPrecomputedHistory(itemId, context);
    if (!data || !data.success || !data.revisions.length) {
        alert('История не найдена');
        return;
    }
    const firstRev = data.revisions[0];
    let modalTitle;
    if (context === 'head') {
        if (itemId === 'head') {
            modalTitle = 'История изменений наименования документа';
        } else {
            const elementPath = (firstRev.element_path || '').replace(/\s*\(заголовок\)\s*$/, '').trim();
            modalTitle = 'История изменений заголовка ' + elementPath;
        }
    } else {
        modalTitle = 'История изменений ' + (firstRev.element_path || 'элемента');
    }
    let listHtml = '<div class="history-timeline">';
    const lastIndex = data.revisions.length - 1;
    const isBlockExpired = isItemExpired(itemId, context);
    for (let idx = 0; idx < data.revisions.length; idx++) {
        const rev = data.revisions[idx];
        const isLast = idx === lastIndex;
        const isExpired = isLast && (npaIsRevExpiredForView(rev.valid_to) || isBlockExpired || rev.is_current === false);
        const isCurrent = !isExpired && rev.is_current !== false;
        let toStr = rev.valid_to ? ' по ' + rev.valid_to : '';
        if (!toStr && isExpired && isBlockExpired) {
            const block = document.querySelector(`.npa-item-block[data-npa-item-id="${itemId}"]`);
            if (block) {
                const dateEl = block.querySelector(':scope > .npa-view-expired') || block.querySelector(':scope > .element-valid-from');
                if (dateEl) {
                    const m = (dateEl.dataset.notValidDate || dateEl.textContent || '').match(/(\d{2}\.\d{2}\.\d{4}|\d{4}-\d{2}-\d{2})/);
                    if (m) toStr = ' по ' + m[1];
                }
            }
        }
        let contextPrefix;
        if (context === 'head' && itemId === 'head') {
            contextPrefix = 'Наименование';
        } else if (context === 'head') {
            contextPrefix = 'Заголовок';
        } else {
            contextPrefix = 'Редакция';
        }
        let titleHtml = (isExpired && isLast)
            ? getExpiredRevisionTitle(contextPrefix, rev.valid_from, toStr)
            : contextPrefix + (isCurrent ? ', действующая с ' : ', действовавшая с ') + rev.valid_from + (isCurrent ? '' : toStr);
        let badgeHtml = '';
        if (isCurrent) {
            badgeHtml = '<span class="current-badge">действующая</span>';
        } else if (isExpired && isLast) {
            badgeHtml = '<span class="original-badge" style="background:#666;color:#fff;">последняя действующая</span>';
        } else if (isExpired) {
            badgeHtml = '<span class="original-badge" style="background:#666;color:#fff;">утратила силу</span>';
        } else if (rev.is_original) {
            badgeHtml = '<span class="original-badge">исходная</span>';
        }
        let itemClass = (rev.is_original && !isLast) ? 'history-item original' : isCurrent ? 'history-item current' : 'history-item change';
        let sourceHtml = '';
        if (isExpired && rev.expiry_source) {
            sourceHtml = rev.expiry_url
                ? '<a href="' + escapeHtml(rev.expiry_url) + '" target="_blank" class="npa-revision-link">' + escapeHtml(rev.expiry_source) + '</a>'
                : escapeHtml(rev.expiry_source);
        } else if (rev.npa_url && rev.display_title && rev.display_title !== 'Исходный заголовок элемента' && rev.display_title !== 'Исходное наименование') {
            const npaLink = '<a href="' + escapeHtml(rev.npa_url) + '" target="_blank" class="npa-revision-link">' + escapeHtml(rev.display_title) + '</a>';
            sourceHtml = (rev.source_decode && rev.source_decode !== 'исходная редакция') ? escapeHtml(rev.source_decode) + ' (' + npaLink + ')' : npaLink;
        } else if (rev.source_decode && rev.source_decode !== 'исходная редакция') {
            sourceHtml = escapeHtml(rev.source_decode);
        } else if (rev.is_original && !isExpired) {
            sourceHtml = 'исходная редакция';
        }
        listHtml += '<div class="' + itemClass + '"><div class="history-title"><strong>' + titleHtml + ' ' + badgeHtml + '</strong></div><div class="history-source">' + sourceHtml + '</div><button class="history-view-btn" data-rev-id="' + rev.rev_id + '" data-item-id="' + itemId + '" data-source="' + escapeHtml(rev.source_decode || '') + '" data-context="' + context + '">Просмотреть</button></div>';
    }
    listHtml += '</div><div class="history-note">Нажмите "Просмотреть", чтобы открыть редакцию в модальном окне.</div>';
    npaShowModal(modalTitle, listHtml, false);
    setTimeout(() => {
        document.querySelectorAll('.history-view-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                const btnContext = this.getAttribute('data-context') || context;
                npaCloseModal();
                npaFetchRevision(this.getAttribute('data-rev-id'), this.getAttribute('data-item-id'), npaId, '', this.getAttribute('data-source'), btnContext);
            });
        });
    }, 50);
}
function setupCompareScrollSync(container) {
    const leftScroll = container.querySelector('.compare-col:first-child .compare-content');
    const rightScroll = container.querySelector('.compare-col:last-child .compare-content');
    if (!leftScroll || !rightScroll) return;
    let isScrolling = false;
    const sync = (source, target) => {
        if (!isScrolling) {
            isScrolling = true;
            target.scrollTop = source.scrollTop;
            requestAnimationFrame(() => { isScrolling = false; });
        }
    };
    leftScroll.addEventListener('scroll', () => sync(leftScroll, rightScroll));
    rightScroll.addEventListener('scroll', () => sync(rightScroll, leftScroll));
}
function npaShowCompare(itemId, npaId, context) {
    context = context || 'item';
    const data = getPrecomputedCompare(itemId, context);
    if (!data || !data.success) {
        alert('Данные для сравнения не найдены');
        return;
    }
    let prevHtml = data.prev_html_raw || '';
    let currHtml = data.current_html_raw || '';
    let highlights = data.highlights;
    let modType = data.mod_type;
    let colored = { old: prevHtml, new: currHtml };
    if (data.pre_highlighted) {
        colored = { old: prevHtml, new: currHtml };
    } else {
        let hasHighlights = false;
        if (highlights) {
            const pEd = highlights.previous_edition;
            const cEd = highlights.current_edition;
            if ((pEd && ((pEd.deletion && pEd.deletion.length > 0) || (pEd.difference && pEd.difference.length > 0))) ||
                (cEd && ((cEd.addition && cEd.addition.length > 0) || (cEd.difference && cEd.difference.length > 0)))) {
                hasHighlights = true;
            }
        }
        if (hasHighlights || modType === 'new_redaction' || modType === 'change' || modType === 'delete' || !modType) {
            colored = applyPreciseHighlights(prevHtml, currHtml, highlights, modType, itemId, context, data);
        }
    }
    let content = '';
    if (data.changing_elements && data.changing_elements.length) {
        content += '<h4>Изменения внесены:</h4>';
        for (let i = 0; i < data.changing_elements.length; i++) {
            const el = data.changing_elements[i];
            content += '<div class="element-revision-notes"><div class="revision-note"><strong>' + el.note + '</strong></div><div class="element-valid-from">дата изменения: ' + el.date + '</div></div><div class="changer-content">' + el.html + '</div>';
        }
    }
    content += '<div class="compare-row">' +
        '<div class="compare-col prev-col">' +
        '<h5>Предыдущая редакция (с ' + data.prev_valid_from + ')</h5>' +
        '<div class="compare-content sync-scroll">' + colored.old + '</div>' +
        '</div>' +
        '<div class="compare-col next-col">' +
        '<h5>Текущая редакция (с ' + data.current_valid_from + ')</h5>' +
        '<div class="compare-content sync-scroll">' + colored.new + '</div>' +
        '</div>' +
        '</div>';
    let modalTitle;
    if (context === 'head') {
        if (itemId === 'head') {
            modalTitle = 'Сравнение редакций наименования документа';
        } else {
            modalTitle = 'Сравнение редакций заголовка ' + (data.element_human_path || 'элемента').replace(/^заголовка\s+/i, '');
        }
    } else {
        modalTitle = 'Сравнение редакций ' + (data.element_human_path || 'элемента');
    }
    npaShowModal(modalTitle, content, true);
    setTimeout(() => {
        const modalBody = document.querySelector('#npa-modal-container .npa-modal-body');
        if (modalBody) {
            setupCompareScrollSync(modalBody);
            initDiffPairs();
            initStructNumbers(modalBody);
            initNPAHeadings(modalBody);
        }
    }, 150);
}
function npaChangeRevision(value) {
    var url = new URL(window.location.href);
    if (!value) {
        url.searchParams.delete('view_date');
    } else {
        url.searchParams.set('view_date', value);
    }
    window.location.href = url.toString();
}
function formatDateRus(dateStr) {
    if (!dateStr) return '';
    const parts = dateStr.split('-');
    return parts.length === 3 ? parts[2] + '.' + parts[1] + '.' + parts[0] : dateStr;
}
function npaDownloadRtf() {
    const controlsEl = document.querySelector('.npa-doc-controls');
    const btn = document.querySelector('.npa-download-btn');
    let originalHtml = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Формируется…';
    }
    setTimeout(function() {
        let clone;
        try {
            const filename = controlsEl?.dataset.downloadFilename || 'document.rtf';
            let meta = {
                fullType: controlsEl?.dataset.npaFullType || '',
                number: controlsEl?.dataset.npaNumber || '',
                date: controlsEl?.dataset.npaDate || '',
                title: controlsEl?.dataset.npaTitle || '',
                url: controlsEl?.dataset.npaUrl || '',
                revisionText: ''
            };
            const revisionSelectEl = document.getElementById('npa-revision-select');
            if (revisionSelectEl && revisionSelectEl.options[revisionSelectEl.selectedIndex]) {
                const revDate = revisionSelectEl.options[revisionSelectEl.selectedIndex].getAttribute('data-date-display') || '';
                if (revDate) {
                    meta.revisionText = 'в редакции от ' + revDate;
                }
            }
            if (meta.date) meta.date = formatDateRus(meta.date);
            const docContent = document.querySelector('.npa-doc-content');
            if (!docContent) {
                alert('Содержимое документа не найдено.');
                return;
            }
            clone = docContent.cloneNode(true);
            clone.querySelectorAll('.doc-toc-anchor, script, style, .npa-item-buttons, .npa-doc-controls, .npa-doc-status-banner').forEach(el => el.remove());
            clone.style.position = 'absolute';
            clone.style.left = '-9999px';
            clone.style.top = '0';
            clone.style.visibility = 'hidden';
            document.body.appendChild(clone);
            initNPAHeadings(clone);
            initStructNumbers(clone);
            clone.querySelectorAll('.npa-view-expired, .expired-body-placeholder').forEach(el => {
                el.textContent = 'Утратил(а/о) силу';
            });
            const mergeHeadings = (container) => {
                let blocks = Array.from(container.querySelectorAll('p, h1, h2, h3, h4'));
                for (let i = 0; i < blocks.length; i++) {
                    let block = blocks[i];
                    if (block.classList && block.classList.contains('npa-appendix-title')) continue;
                    let txt = block.textContent.trim();
                    let isOnlyNum = /^(Статья|Глава|Раздел|Приложение)\s+[\dIVXLCDMа-яА-ЯёЁ¹²³⁴⁵⁶⁷⁸⁹⁰]+(?:[\.\)]\d+)*[\.\)]?\s*$/iu.test(txt);
                    let emptyTitleSpan = null;
                    if (block.classList.contains('npa-article') || block.classList.contains('npa-chapter') || block.classList.contains('npa-section')) {
                        let tEl = block.querySelector('.npa-article-title, .npa-chapter-title, .npa-section-title');
                        if (tEl && tEl.textContent.trim() === '') {
                            emptyTitleSpan = tEl;
                        }
                    }
                    if (isOnlyNum || emptyTitleSpan) {
                        let next = block.nextElementSibling;
                        while (next && next.tagName === 'P' && next.textContent.trim() === '') {
                            let temp = next.nextElementSibling;
                            next.remove();
                            next = temp;
                        }
                        if (next && (next.tagName === 'P' || next.tagName.match(/^H\d$/))) {
                            let nextTxt = next.textContent.trim();
                            if (nextTxt && !/^(Статья|Глава|Раздел|Приложение)\s+[\dIVXLCDMа-яА-ЯёЁ¹²³⁴⁵⁶⁷⁸⁹⁰]+/iu.test(nextTxt)) {
                                if (emptyTitleSpan) {
                                    continue;
                                }
                                const isLong = nextTxt.length > 200;
                                const hasSentenceEnd = /[.!?]$/.test(nextTxt);
                                if (!isLong && !hasSentenceEnd) {
                                    block.appendChild(document.createTextNode(' '));
                                    while (next.firstChild) {
                                        block.appendChild(next.firstChild);
                                    }
                                    next.remove();
                                }
                            }
                        }
                    }
                }
            };
            mergeHeadings(clone);
            const blob = new Blob([_npaGenerateRtf(clone, meta)], { type: 'application/rtf;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            setTimeout(() => URL.revokeObjectURL(url), 2000);
        } catch (err) {
            console.error(err);
            alert('Ошибка формирования файла.');
        } finally {
            if (clone && clone.parentNode) {
                clone.parentNode.removeChild(clone);
            }
            if (btn) {
                btn.disabled = false;
                if (originalHtml) btn.innerHTML = originalHtml;
                else btn.textContent = 'Скачать (в формате .rtf)';
            }
        }
    }, 50);
}
function _npaRtfEsc(str) {
    if (!str) return '';
    let out = '';
    for (let i = 0; i < str.length; i++) {
        let c = str.charCodeAt(i);
        if (c === 92) out += '\\\\';
        else if (c === 123) out += '\\{';
        else if (c === 125) out += '\\}';
        else if (c < 128) out += str[i];
        else out += '\\u' + c + '?';
    }
    return out;
}
function _EP() {
    return '\\pard \\ql \\par\n';
}
function _HR() {
    return '\\pard \\ql \\brdrb\\brdrs\\brdrw10\\brsp60 \\par\n';
}
function getCellBorderRtf(cell) {
    const computed = window.getComputedStyle(cell);
    const borders = ['top', 'right', 'bottom', 'left'];
    let result = '';
    for (const side of borders) {
        const width = computed.getPropertyValue(`border-${side}-width`);
        const style = computed.getPropertyValue(`border-${side}-style`);
        const hasBorder = width !== '0px' && width !== '' && style !== 'none';
        if (hasBorder) {
            result += `\\clbrdr${side[0]}\\brdrs\\brdrw10`;
        } else {
            result += `\\clbrdr${side[0]}\\brdrw0`;
        }
    }
    return result;
}
function _npaTableToRtf(tableEl) {
    var rows = tableEl.querySelectorAll('tr');
    if (!rows.length) return '';
    var grid = [];
    for (var r = 0; r < rows.length; r++) {
        grid[r] = [];
    }
    for (var r = 0; r < rows.length; r++) {
        var row = rows[r];
        var cells = row.querySelectorAll('td, th');
        var cellIndex = 0;
        cells.forEach(cell => {
            while (grid[r][cellIndex] !== undefined) {
                cellIndex++;
            }
            var colspan = parseInt(cell.getAttribute('colspan') || '1', 10);
            var rowspan = parseInt(cell.getAttribute('rowspan') || '1', 10);
            for (var rs = 0; rs < rowspan; rs++) {
                if (!grid[r + rs]) grid[r + rs] = [];
                for (var cs = 0; cs < colspan; cs++) {
                    grid[r + rs][cellIndex + cs] = {
                        cell: cell,
                        isReal: (rs === 0 && cs === 0),
                        colspan: colspan,
                        rowspan: rowspan,
                        rowSpanTop: r,
                        colSpanLeft: cellIndex
                    };
                }
            }
            cellIndex += colspan;
        });
    }
    var maxCols = 0;
    grid.forEach(gRow => {
        if (gRow.length > maxCols) maxCols = gRow.length;
    });
    if (!maxCols) return '';
    var colWeights = new Array(maxCols).fill(0);
    grid.forEach(gRow => {
        for (var c = 0; c < maxCols; c++) {
            var slot = gRow[c];
            if (slot && slot.isReal) {
                var textLen = slot.cell.textContent.trim().length;
                var weight = Math.max(textLen, 2) / slot.colspan;
                for (var cs = 0; cs < slot.colspan; cs++) {
                    if (c + cs < maxCols) {
                        if (weight > colWeights[c + cs]) {
                            colWeights[c + cs] = weight;
                        }
                    }
                }
            }
        }
    });
    var totalWeight = colWeights.reduce((a, b) => a + b, 0);
    var colWidths = [];
    var totalWidthAvailable = 8306;
    if (totalWeight > 0) {
        var minWidth = Math.floor(totalWidthAvailable / (maxCols * 2));
        var remainingWidth = totalWidthAvailable - (minWidth * maxCols);
        if (remainingWidth < 0) {
            var evenW = Math.floor(totalWidthAvailable / maxCols);
            colWidths = new Array(maxCols).fill(evenW);
        } else {
            var currentTotal = 0;
            for (var c = 0; c < maxCols; c++) {
                var w = minWidth + Math.floor((colWeights[c] / totalWeight) * remainingWidth);
                colWidths.push(w);
                currentTotal += w;
            }
            var diff = totalWidthAvailable - currentTotal;
            if (colWidths.length > 0) {
                colWidths[colWidths.length - 1] += diff;
            }
        }
    } else {
        var evenW = Math.floor(totalWidthAvailable / maxCols);
        colWidths = new Array(maxCols).fill(evenW);
    }
    var rtf = '';
    for (var r = 0; r < grid.length; r++) {
        var gRow = grid[r];
        if (!gRow || !gRow.length) continue;
        rtf += '\\trowd\\trgaph108\\trleft0\n';
        var x = 0;
        for (var c = 0; c < maxCols; ) {
            var slot = gRow[c];
            if (!slot) {
                x += colWidths[c];
                rtf += `\\clbrdrt\\brdrw0\\clbrdrl\\brdrw0\\clbrdrb\\brdrw0\\clbrdrr\\brdrw0\\cellx${x}\n`;
                c++;
                continue;
            }
            if (c === slot.colSpanLeft) {
                var cellW = 0;
                for (var cs = 0; cs < slot.colspan; cs++) {
                    if (c + cs < maxCols) {
                        cellW += colWidths[c + cs];
                    }
                }
                x += cellW;
                var borderRtf = getCellBorderRtf(slot.cell);
                if (slot.rowspan > 1) {
                    if (r === slot.rowSpanTop) {
                        borderRtf += '\\clvmgf';
                    } else {
                        borderRtf += '\\clvmrg';
                    }
                }
                rtf += borderRtf + `\\cellx${x}\n`;
                c += slot.colspan;
            } else {
                c++;
            }
        }
        for (var c = 0; c < maxCols; ) {
            var slot = gRow[c];
            if (!slot) {
                rtf += '\\pard\\intbl\\fi0 \\ql \\cell\n';
                c++;
                continue;
            }
            if (c === slot.colSpanLeft) {
                if (r > slot.rowSpanTop) {
                    rtf += '\\pard\\intbl\\fi0 \\cell\n';
                } else {
                    var cell = slot.cell;
                    var isHdr = cell.tagName.toLowerCase() === 'th';
                    var alignCmd = '\\ql';
                    if (isHdr) alignCmd = '\\qc';
                    var textAlign = cell.style.textAlign || cell.getAttribute('align');
                    if (textAlign) {
                        textAlign = textAlign.toLowerCase();
                        if (textAlign === 'center') alignCmd = '\\qc';
                        else if (textAlign === 'right') alignCmd = '\\qr';
                        else if (textAlign === 'justify') alignCmd = '\\qj';
                    }
                    var cellRtf = Array.from(cell.childNodes).map(n => _npaNodeToRtf(n, true)).join('');
                    cellRtf = cellRtf.replace(/\\pard(?![a-zA-Z])/g, '\\pard\\intbl\\fi0 ');
                    cellRtf = cellRtf.replace(/\\par(?![a-zA-Z])/g, '\\par\\intbl\\fi0 ');
                    cellRtf = cellRtf.replace(/\\fi-?\d+/g, '');
                    cellRtf = cellRtf.replace(/\\par\\intbl\\fi0\s*$/, '');
                    cellRtf = cellRtf.replace(/\\par\s*$/, '');
                    rtf += `\\pard\\intbl\\fi0 ${alignCmd} ${isHdr ? '\\b ' : ''}${cellRtf}\\cell\n`;
                }
                c += slot.colspan;
            } else {
                c++;
            }
        }
        rtf += '\\row\n';
    }
    return rtf;
}
function _npaNodeToRtf(node, insideTable) {
    if (node.nodeType === 3) {
        return _npaRtfEsc(node.nodeValue);
    }
    if (node.nodeType !== 1) return '';
    var tag = node.tagName.toLowerCase();
    var cls = (typeof node.className === 'string') ? node.className : '';

    if (cls.indexOf('npa-signer') >= 0 || cls.indexOf('npa-requisites') >= 0) {
        let parts = [];
        node.childNodes.forEach(child => {
            if (child.nodeType === 3) {
                parts.push(_npaRtfEsc(child.nodeValue.trim()));
            } else if (child.nodeType === 1) {
                if (child.tagName.toLowerCase() === 'br') {
                    parts.push('\\line');
                } else {
                    parts.push(_npaNodeToRtf(child, insideTable));
                }
            }
        });
        let content = parts.join(' ').replace(/\s*\\line\s*/g, '\\line\n');
        content = content.replace(/ {2,}/g, ' ').trim();
        return '\\pard \\ql\\sb240\\sa0 ' + content + '\\par\n';
    }
    function inner() {
        return Array.from(node.childNodes).map(n => _npaNodeToRtf(n, insideTable)).join('');
    }
    if (tag === 'style' || tag === 'script' || tag === 'svg' || cls.indexOf('npa-doc-controls') >= 0 || cls.indexOf('npa-item-buttons') >= 0) return '';
    if (cls.indexOf('npa-appendix-prefix') >= 0) {
        return '\\pard \\ql \\li5508 \\sa240 ' + inner() + '\\par\n';
    }
    if (cls.indexOf('npa-appendix-title') >= 0) {
        return '\\pard \\qc {\\b ' + inner() + '}\\par\n';
    }
    if (cls.indexOf('npa-view-expired') >= 0 || cls.indexOf('expired-body-placeholder') >= 0) {
        let itemBlock = node.closest('.npa-item-block');
        let itemType = itemBlock ? itemBlock.getAttribute('data-item-type') : null;
        let suffix = '';
        if (itemType === 'article' || itemType === 'part' || itemType === 'chapter' || itemType === 'section' || itemType === 'preamble') {
            suffix = 'а';
        } else if (itemType === 'appendix' || itemType === 'nested_appendix') {
            suffix = 'о';
        } else {
            suffix = '';
        }
        let expiredText = 'Утратил' + suffix + ' силу';
        return _npaRtfEsc(expiredText);
    }
    
    // Обработка блоков с примечаниями и заметками
    if (cls.indexOf('revision-note') >= 0 || cls.indexOf('element-revision-notes') >= 0 || cls.indexOf('head-revision-notes') >= 0 || cls.indexOf('document-revision-note') >= 0 || cls.indexOf('npa-struct-num') >= 0 || cls.indexOf('npa-item-notes') >= 0 || cls.indexOf('npa-doc-notes') >= 0) {
        if (cls.indexOf('element-revision-notes') >= 0 || cls.indexOf('head-revision-notes') >= 0) {
            return '\\pard \\ql\\sb240\\sa240\\li720\\ri720\\sl276\\slmult1 ' + inner() + '\\par\n';
        }
        if (cls.indexOf('document-revision-note') >= 0) {
            return '\\pard \\qc\\sb240\\sa240 {\\i\\fs20\\cf2 ' + inner() + '}\\par\n';
        }
        if (cls.indexOf('npa-item-notes') >= 0) {
            let textSpan = node.querySelector('.npa-item-notes-text');
            let text = textSpan ? textSpan.textContent.trim() : node.textContent.trim();
            if (!text) return '';
            return '\\pard \\ql\\fi0\\sb0\\sa120 {\\i\\fs20\\cf2 ' + _npaRtfEsc('Примечание: ') + _npaRtfEsc(text) + '}\\par\n';
        }
        if (cls.indexOf('npa-doc-notes') >= 0) {
            let notes = node.querySelectorAll('.npa-doc-note');
            if (!notes.length) return '';
            let rtf = '\\pard \\ql\\sb0\\sa120 {\\b\\fs20\\cf2 ' + _npaRtfEsc('Примечания к документу:') + '}\\par\n';
            notes.forEach(n => {
                rtf += '\\pard \\ql\\fi360\\sb0\\sa60 {\\i\\fs20\\cf2 ' + _npaRtfEsc(n.textContent.trim()) + '}\\par\n';
            });
            return rtf;
        }
        if (cls.indexOf('revision-note') >= 0) {
            return '{\\i\\fs20\\cf2 ' + inner() + '}';
        }
        if (cls.indexOf('npa-struct-num') >= 0) {
            return inner() + '\\~';
        }
        return inner();
    }
    
    if (cls.indexOf('npa-section') >= 0 && tag === 'p') {
        let numSpan = node.querySelector('.npa-section-num');
        let titleSpan = node.querySelector('.npa-section-title');
        let numText = numSpan ? numSpan.textContent.trim() : '';
        let titleText = titleSpan ? titleSpan.textContent.trim() : '';
        if (numText) {
            let rtfNum = _npaRtfEsc(numText);
            let rtfTitle = titleText ? _npaRtfEsc(titleText) : '';
            if (rtfTitle) {
                return '\\pard \\qc \\sa240 {\\b ' + rtfNum + '}\\line {\\b ' + rtfTitle + '}\\par\n';
            } else {
                return '\\pard \\qc \\sa240 {\\b ' + rtfNum + '}\\par\n';
            }
        }
        return '\\pard \\qc {\\b ' + inner() + '}\\par\n';
    }
    if (cls.indexOf('npa-chapter') >= 0 && tag === 'p') {
        let numSpan = node.querySelector('.npa-chapter-num');
        let titleSpan = node.querySelector('.npa-chapter-title');
        let numText = numSpan ? numSpan.textContent.trim() : '';
        let titleText = titleSpan ? titleSpan.textContent.trim() : '';
        if (numText) {
            let rtfNum = _npaRtfEsc(numText);
            let rtfTitle = titleText ? _npaRtfEsc(titleText) : '';
            if (rtfTitle) {
                return '\\pard \\qc \\sa240 {\\b ' + rtfNum + '}\\line {\\b ' + rtfTitle + '}\\par\n';
            } else {
                return '\\pard \\qc \\sa240 {\\b ' + rtfNum + '}\\par\n';
            }
        }
        return '\\pard \\qc {\\b ' + inner() + '}\\par\n';
    }
    if (cls.indexOf('npa-article') >= 0 && tag === 'p') {
        return '\\pard \\ql \\sa240 ' + inner() + '\\par\n';
    }
    if (cls.indexOf('npa-appendix') >= 0 && tag === 'p') {
        return '\\pard \\ql ' + inner() + '\\par\n';
    }
    if (tag === 'p') {
        var pcls = cls.toLowerCase();
        var alignCmd = '\\qj';
        var isCenter = false;
        if (node.getAttribute('align') === 'center' || (node.style && node.style.textAlign === 'center')) {
            alignCmd = '\\qc';
            isCenter = true;
        }
        var firstLineIndent = isCenter ? '\\fi0' : '\\fi720';
        if (pcls.indexOf('npa-date-passed') >= 0) {
            return '\\pard \\ql\\sb0\\sa240 ' + inner() + '\\par\n';
        }
        if (pcls.indexOf('document-revision-note') >= 0) {
            return '\\pard \\qc\\sb200\\sa200 {\\i\\fs20 ' + inner() + '}\\par\n';
        }
        let intblFlag = insideTable ? '\\intbl' : '';
        return '\\pard' + intblFlag + ' ' + alignCmd + firstLineIndent + '\\sb0\\sa120 {\\f0\\fs24 ' + inner() + '}\\par\n';
    }
    if (tag === 'b' || tag === 'strong') {
        return '{\\b ' + inner() + '}';
    }
    if (tag === 'span') {
        if (cls.indexOf('npa-struct-num') >= 0) {
            return inner() + '\\~';
        }
        if (cls.indexOf('npa-article-num') >= 0) {
            return '{\\b ' + inner() + '} ';
        }
        if (cls.indexOf('npa-appendix-num') >= 0) {
            return '{\\b ' + inner() + '} ';
        }
        if (cls.indexOf('npa-chapter-num') >= 0) {
            return '{\\b ' + inner() + '} ';
        }
        if (cls.indexOf('npa-section-num') >= 0) {
            return '{\\b ' + inner() + '} ';
        }
        if (cls.indexOf('npa-article-title') >= 0 || cls.indexOf('npa-chapter-title') >= 0 || cls.indexOf('npa-section-title') >= 0) {
            return '{\\b ' + inner() + '}';
        }
        if (cls.indexOf('npa-appendix-title') >= 0) {
            return '{\\b ' + inner() + '}';
        }
    }
    if (cls.indexOf('npa-empty-signature-space') >= 0) {
        return '\\pard \\ql \\par\n';
    }
    if (cls.indexOf('element-valid-from') >= 0) {
        return '\\pard \\ql\\sb0\\sa60 {\\i\\fs20\\cf2 ' + inner() + '}\\par\n';
    }
    if (cls.indexOf('revision-meta') >= 0) {
        return '\\pard \\ql\\sb0\\sa120 {\\i\\fs20\\cf2 ' + inner() + '}\\par\n';
    }
    switch (tag) {
        case 'i':
        case 'em':
            return '{\\i ' + inner() + '}';
        case 'u':
            return '{\\ul ' + inner() + '}';
        case 'sup':
            return '{\\super ' + inner() + '}';
        case 'sub':
            return '{\\sub ' + inner() + '}';
        case 'br':
            if (node.closest && (node.closest('.element-revision-notes') || node.closest('.head-revision-notes') || node.closest('.document-revision-note'))) {
                return '\\par\n';
            }
            return '\\line ';
        case 'a':
            var href = node.getAttribute('href') || '';
            var linkText = node.textContent.trim();
            if (linkText.startsWith('Посмотреть текст')) {
                return _npaRtfEsc('Утратил(а/о) силу');
            }
            var content = '{\\cf1 ' + inner() + '}';
            return (href && (href.indexOf('http') === 0 || href.indexOf('//') === 0)) ? '{\\field{\\*\\fldinst HYPERLINK "' + _npaRtfEsc(href) + '"}{\\fldrslt {' + content + '}}}' : content;
        case 'h1':
            return '\\pard \\sb0\\sa200 \\qc {\\b\\fs32 ' + inner() + '}\\par\n';
        case 'h2':
            return '\\pard \\sb0\\sa180 \\qc {\\b\\fs28 ' + inner() + '}\\par\n';
        case 'h3':
            return '\\pard \\sb0\\sa160 \\ql {\\b\\fs26 ' + inner() + '}\\par\n';
        case 'table':
            var tableRtf = _npaTableToRtf(node);
            return tableRtf + '\\pard \\par\n';
        case 'tr':
        case 'td':
        case 'th':
            return inner();
        case 'ul':
        case 'ol':
            var listOut = '';
            var idx = 1;
            Array.from(node.children).forEach(function(li) {
                var innerRtf = Array.from(li.childNodes).map(n => _npaNodeToRtf(n, insideTable)).join('');
                innerRtf = innerRtf.replace(/(\\par\s*)+$/, '');
                listOut += '\\pard \\ql\\sb0\\sa0 ' + (tag === 'ul' ? '\\u8226?  ' : (idx++ + '. ')) + innerRtf + '\\par\n';
            });
            return listOut;
        case 'div':
            if (cls.indexOf('element-valid-from') >= 0) {
                return '\\pard \\ql\\sb0\\sa60 {\\i\\fs20\\cf2 ' + inner() + '}\\par\n';
            }
            if (cls.indexOf('npa-para-sep') >= 0) return '';
            if (cls.indexOf('npa-doc-footer') >= 0) return '\\pard \\ql \\par\n' + inner();
            if (cls === 'npa-item-block') return '{\\f0\\fs24 ' + inner() + '}';
            if (cls.indexOf('npa-expired-inline') >= 0) {
                return '\\pard \\ql \\fi720\\sb0\\sa120 {\\f0\\fs24 ' + inner() + '}\\par\n';
            }
            return inner();
        default:
            return inner();
    }
}
function _npaGenerateRtf(containerEl, meta) {
    meta = meta || {};
    var body = Array.from(containerEl.childNodes).map(n => _npaNodeToRtf(n, false)).join('');
    var prefix = '';
    if (meta.fullType) {
        var lowerType = meta.fullType.toLowerCase();
        if (lowerType.indexOf('постановление') >= 0) {
            prefix = 'Постановление Законодательного Собрания города Севастополя ';
        } else if (lowerType.indexOf('закон') >= 0) {
            prefix = 'Закон города Севастополя ';
        }
    }
    var cleanNumber = (meta.number || '').replace(/^\s*[ВвBb]\s*/, '').trim();
    var npaAndRevision = '';
    if (cleanNumber) {
        npaAndRevision += _npaRtfEsc(prefix) + _npaRtfEsc('№') + ' ' + _npaRtfEsc(cleanNumber);
        if (meta.date) npaAndRevision += ' ' + _npaRtfEsc('от') + ' ' + _npaRtfEsc(meta.date);
    }
    var npaLinkLine = '';
    if (npaAndRevision) {
        if (meta.url) {
            npaLinkLine = '{\\field{\\*\\fldinst HYPERLINK "' + _npaRtfEsc(meta.url) + '"}{\\fldrslt {\\cf1 ' + npaAndRevision + '}}}';
        } else {
            npaLinkLine = '{\\cf2 ' + npaAndRevision + '}';
        }
    }
    var siteText = "Документ предоставлен официальным сайтом Законодательного Собрания города Севастополя — ";
    var site = _npaRtfEsc(siteText) + '{\\field{\\*\\fldinst HYPERLINK "https://sevzakon.ru"}{\\fldrslt {\\cf1 sevzakon.ru}}}';
    var headerPara1 = '{\\f1\\fs18\\cf2 ' + site + '}\\par\n';
    var headerPara2Content = '';
    if (npaLinkLine) {
        headerPara2Content += npaLinkLine;
    }
    if (meta.revisionText) {
        var tempDiv = document.createElement('div');
        tempDiv.innerHTML = meta.revisionText;
        var revisionRtf = Array.from(tempDiv.childNodes).map(n => _npaNodeToRtf(n, false)).join('');
        if (headerPara2Content && revisionRtf) {
            headerPara2Content += ' ' + revisionRtf;
        } else {
            headerPara2Content += revisionRtf;
        }
    }
    var headerPara2 = '';
    if (headerPara2Content) {
        headerPara2 = '{\\f1\\fs18\\cf2 ' + headerPara2Content + '}\\par\n';
    }
    var attrBlock = headerPara1 + headerPara2 + '\\pard \\ql \\brdrb\\brdrs\\brdrw10\\brsp60 \\par\n';
    return '{\\rtf1\\ansi\\deff0\\nouicompat\n' +
        '{\\fonttbl{\\f0\\froman\\fprq2\\fcharset204 Times New Roman;}{\\f1\\fswiss\\fprq2\\fcharset204 Arial;}}\n' +
        '{\\colortbl;\\red0\\green0\\blue255;\\red100\\green100\\blue100;}\n' +
        '{\\*\\generator NPA RTF 5.0}\n' +
        '\\paperw12240\\paperh15840\\margl1800\\margr1800\\margt1440\\margb1440\n' +
        '\\widowctrl\\f0\\fs24\\lang1049 \n' +
        '\\pard \\ql ' + attrBlock + '\\cf0 ' + body + '}';
}
function npaShowModal(title, contentHtml, skipFormatting) {
    if (!document.getElementById('npa-modal-container')) {
        const mc = document.createElement('div');
        mc.id = 'npa-modal-container';
        document.body.appendChild(mc);
    }
    const container = document.getElementById('npa-modal-container');
    container.innerHTML = `<div class="npa-modal-overlay"><div class="npa-modal-window"><div class="npa-modal-header"><span class="npa-modal-title">${escapeHtml(title)}</span><button class="npa-modal-close">&times;</button></div><div class="npa-modal-body">${contentHtml}</div></div></div>`;
    container.style.display = 'block';
    document.body.style.overflow = 'hidden';
    const closeModal = () => {
        container.style.display = 'none';
        container.innerHTML = '';
        document.body.style.overflow = '';
    };
    container.querySelector('.npa-modal-close').addEventListener('click', closeModal);
    container.querySelector('.npa-modal-overlay').addEventListener('click', e => {
        if (e.target === e.currentTarget) closeModal();
    });
    setTimeout(initDiffPairs, 100);
    if (!skipFormatting) {
        setTimeout(() => {
            const modalBody = document.querySelector('#npa-modal-container .npa-modal-body');
            if (modalBody) {
                initStructNumbers(modalBody);
                initNPAHeadings(modalBody);
            }
        }, 150);
    }
}
function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[m]);
}
function npaCloseModal() {
    const c = document.getElementById('npa-modal-container');
    if (c) {
        c.style.display = 'none';
        c.innerHTML = '';
        document.body.style.overflow = '';
    }
}
function initDiffPairs() {
    const modal = document.getElementById('npa-modal-container');
    if (!modal) return;
    const hues = [35, 45, 55, 65, 40, 50, 60, 70];
    const pairIds = new Set();
    modal.querySelectorAll('[data-pair-id]').forEach(el => pairIds.add(el.getAttribute('data-pair-id')));
    const pairIdList = Array.from(pairIds);
    modal.querySelectorAll('[data-pair-id]').forEach(el => el.style.setProperty('--pair-hue', hues[pairIdList.indexOf(el.getAttribute('data-pair-id')) % hues.length]));
    if (modal._diffPairsHandlersAttached) return;
    modal._diffPairsHandlersAttached = true;
    modal.addEventListener('mouseover', e => {
        const t = e.target.closest('[data-pair-id]');
        if (!t) return;
        modal.querySelectorAll(`[data-pair-id="${t.getAttribute('data-pair-id')}"]`).forEach(el => el.classList.add('highlight-pair'));
    });
    modal.addEventListener('mouseout', e => {
        const t = e.target.closest('[data-pair-id]');
        if (!t) return;
        const r = e.relatedTarget?.closest('[data-pair-id]');
        if (r && r.getAttribute('data-pair-id') === t.getAttribute('data-pair-id')) return;
        modal.querySelectorAll(`[data-pair-id="${t.getAttribute('data-pair-id')}"]`).forEach(el => el.classList.remove('highlight-pair'));
    });
}
function filterInvalidButtons() {
    if (!NPA_STATIC_DATA || !NPA_STATIC_DATA.precomputed) return;
    const allButtons = document.querySelectorAll('.npa-item-btn');
    allButtons.forEach(btn => {
        let itemId = btn.dataset.itemId || null;
        let context = btn.dataset.context || 'item';
        if (!itemId) {
            const ib = btn.closest('.npa-item-block');
            if (ib) {
                itemId = ib.getAttribute('data-npa-item-id');
            }
        }
        if (!itemId) return;
        const text = (btn.textContent || '').toLowerCase();
        const isExpired = isItemExpired(itemId, context);
        const historyData = getPrecomputedHistory(itemId, context);
        const compareData = getPrecomputedCompare(itemId, context);
        const isAdd = compareData && compareData.success && compareData.mod_type === 'add';
        const isDelete = compareData && compareData.success && compareData.mod_type === 'delete';
        let shouldRemove = false;
        if (isAdd && !isExpired) {
            shouldRemove = true;
        } else if (isExpired || isDelete) {
            if (!text.includes('истор')) {
                shouldRemove = true;
            } else {
                if (!historyData || !historyData.success || !historyData.revisions || historyData.revisions.length === 0) {
                    shouldRemove = true;
                }
            }
        } else {
            if (text.includes('истор')) {
                const hasValidHistory = historyData && historyData.success && historyData.revisions && historyData.revisions.length > 1;
                if (!hasValidHistory) shouldRemove = true;
            } else if (text.includes('сравн') || text.includes('предыдущ') || text.includes('редакци')) {
                const hasValidCompare = compareData && compareData.success && compareData.prev_html_raw;
                if (!hasValidCompare) shouldRemove = true;
            }
        }
        if (shouldRemove) {
            btn.remove();
        }
    });
    document.querySelectorAll('.npa-item-buttons').forEach(container => {
        if (container.querySelectorAll('.npa-item-btn').length === 0) {
            container.remove();
        }
    });
}
function initToggleButtons() {
    const noteSel = '.element-revision-notes, .head-revision-notes, .document-revision-note';
    const makeIcon = () => {
        const iconSpan = document.createElement('span');
        iconSpan.className = 'toggle-buttons-icon closed';
        iconSpan.setAttribute('aria-label', 'Показать/скрыть кнопки');
        return iconSpan;
    };
    const bindIcon = (iconSpan, buttons) => {
        if (iconSpan._npaBound) return;
        iconSpan._npaBound = true;
        buttons.classList.remove('show-buttons');
        iconSpan.addEventListener('click', e => {
            e.stopPropagation();
            buttons.classList.toggle('show-buttons');
            iconSpan.className = buttons.classList.contains('show-buttons') ? 'toggle-buttons-icon opened' : 'toggle-buttons-icon closed';
        });
        buttons._npaToggleIcon = iconSpan;
    };
    const attachToNote = (note, buttons) => {
        const existing = note.querySelector('.toggle-buttons-icon');
        if (existing) {
            bindIcon(existing, buttons);
            return buttons._npaToggleIcon === existing;
        }
        const originalContent = note.innerHTML;
        note.innerHTML = '';
        const textSpan = document.createElement('span');
        textSpan.className = 'revision-note-text';
        textSpan.innerHTML = originalContent;
        const iconSpan = makeIcon();
        const container = document.createElement('div');
        container.className = 'revision-note-container';
        container.appendChild(textSpan);
        container.appendChild(iconSpan);
        note.appendChild(container);
        bindIcon(iconSpan, buttons);
        return true;
    };
    // Проход 1: заметка -> ближайший следующий контейнер кнопок (до следующей заметки)
    document.querySelectorAll(noteSel).forEach(note => {
        let sibling = note.nextElementSibling;
        while (sibling) {
            if (sibling.classList?.contains('npa-item-buttons')) {
                if (!sibling._npaToggleIcon) attachToNote(note, sibling);
                break;
            }
            if (sibling.matches(noteSel)) break;
            sibling = sibling.nextElementSibling;
        }
    });
    // Проход 2: контейнеры-«сироты» (стоят ПЕРЕД своей заметкой и т.п.) ->
    // ближайшая предыдущая заметка в том же родителе без своей иконки
    document.querySelectorAll('.npa-item-buttons').forEach(buttons => {
        if (buttons._npaToggleIcon) return;
        let sibling = buttons.previousElementSibling;
        while (sibling) {
            if (sibling.matches(noteSel)) {
                const ex = sibling.querySelector('.toggle-buttons-icon');
                if (!ex) {
                    attachToNote(sibling, buttons);
                    return;
                }
                if (!ex._npaBound) {
                    bindIcon(ex, buttons);
                    return;
                }
                break;
            }
            if (sibling.classList?.contains('npa-item-buttons')) break;
            sibling = sibling.previousElementSibling;
        }
        // Проход 3: гарантия доступности кнопок — standalone-иконка перед контейнером
        const iconSpan = makeIcon();
        buttons.parentNode.insertBefore(iconSpan, buttons);
        bindIcon(iconSpan, buttons);
    });
}
function initStructNumbers(rootElement) {
    rootElement = rootElement || document;
    const itemBlocks = rootElement.querySelectorAll('.npa-item-block');
    itemBlocks.forEach(block => {
        const itemType = block.getAttribute('data-item-type');
        if (!['point', 'subpoint', 'part', 'article', 'chapter', 'section', 'appendix'].includes(itemType)) {
            return;
        }
        const firstP = block.querySelector(':scope > p:first-of-type');
        if (!firstP || firstP.classList.contains('npa-num-processed')) return;
        const textNode = firstP.firstChild;
        if (!textNode || textNode.nodeType !== 3) return;
        let text = textNode.textContent;
        const structMatch = text.match(/^(\s*)([\dIVX]+(?:\.[\dIVX]+)*[\.\)]?|[а-яА-ЯёЁ][\.\)])(?=\s|$)/i);
        if (structMatch) {
            const [, leadingSpace, numberPart] = structMatch;
            if (text.trim().length > 250 && /«|"/.test(text)) {
                return;
            }
            firstP.classList.add('npa-has-num', 'npa-num-processed');
            const numSpan = document.createElement('span');
            numSpan.className = 'npa-struct-num';
            numSpan.textContent = numberPart;
            textNode.textContent = text.substring(leadingSpace.length + numberPart.length);
            if (leadingSpace) firstP.insertBefore(document.createTextNode(leadingSpace), textNode);
            firstP.insertBefore(numSpan, textNode);
        }
    });
}
function initNPAHeadings(rootElement) {
    rootElement = rootElement || document;
    if (!rootElement) return;
    const docContent = rootElement === document ? document.querySelector('.npa-doc-content') : null;
    if (docContent) {
        const firstP = docContent.querySelector(':scope > p:first-of-type');
        if (firstP) {
            firstP.style.textIndent = '0';
            firstP.style.textAlign = 'center';
        }
        const secondP = docContent.querySelector(':scope > p:nth-of-type(2)');
        if (secondP) {
            secondP.style.textIndent = '0';
            secondP.style.textAlign = 'center';
        }
    }
    const isInsideNoName = (itemBlock) => {
        if (!NPA_NO_NAME_IDS || !NPA_NO_NAME_IDS.length) return false;
        let current = itemBlock;
        while (current) {
            const id = current.getAttribute('data-npa-item-id');
            if (id && NPA_NO_NAME_IDS.includes(id)) return true;
            const type = current.getAttribute('data-item-type');
            if (type === 'appendix' || type === 'nested_appendix') break;
            current = current.parentElement?.closest('.npa-item-block');
        }
        return false;
    };
    rootElement.querySelectorAll('p, h1, h2, h3, h4').forEach(p => {
        if (p.classList.contains('npa-num-processed') ||
            p.classList.contains('npa-article') ||
            p.classList.contains('npa-chapter') ||
            p.classList.contains('npa-section') ||
            p.classList.contains('npa-appendix') ||
            p.querySelector('.npa-highlight') ||
            p.classList.contains('revision-note-text') ||
            p.closest('.element-revision-notes') ||
            p.closest('.npa-item-buttons') ||
            p.closest('.history-item') ||
            p.closest('.revision-meta')) return;
        const originalHtml = p.innerHTML;
        const hasSupSub = /<\/?sup|<\/?sub/i.test(originalHtml);
        const plainText = p.textContent.trim();
        let match = plainText.match(/^Глава\s+[\dIVXLCDMа-яА-ЯёЁ¹²³⁴⁵⁶⁷⁸⁹⁰]+/iu);
        if (match) {
            p.classList.add('npa-chapter', 'npa-num-processed');
            if (hasSupSub) {
                p.innerHTML = `<span class="npa-chapter-num">${originalHtml}</span>`;
            } else {
                const full = plainText.match(/^((?:Глава)\s+[\dIVXLCDMа-яА-ЯёЁ¹²³⁴⁵⁶⁷⁸⁹⁰]+)([\.\)]?)\s*(.*)$/iu);
                if (full) {
                    p.innerHTML = `<span class="npa-chapter-num">${full[1]}${full[2]}</span><span class="npa-chapter-title">${full[3]}</span>`;
                }
            }
            return;
        }
        match = plainText.match(/^Раздел\s+[\dIVXLCDMа-яА-ЯёЁ¹²³⁴⁵⁶⁷⁸⁹⁰]+/iu);
        if (match) {
            p.classList.add('npa-section', 'npa-num-processed');
            const itemBlock = p.closest('.npa-item-block');
            const skipPrefix = itemBlock ? isInsideNoName(itemBlock) : false;
            if (hasSupSub) {
                p.innerHTML = `<span class="npa-section-num">${originalHtml}</span>`;
            } else {
                const full = plainText.match(/^((?:Раздел)\s+[\dIVXLCDMа-яА-ЯёЁ¹²³⁴⁵⁶⁷⁸⁹⁰]+)([\.\)]?)\s*(.*)$/iu);
                if (full) {
                    let numPart = full[1];
                    const punctuation = full[2];
                    const titlePart = full[3];
                    if (skipPrefix) {
                        numPart = numPart.replace(/^Раздел\s+/i, '');
                        p.innerHTML = `<span class="npa-section-num no-name-prefix">${numPart}${punctuation}</span><span class="npa-section-title">${titlePart}</span>`;
                    } else {
                        p.innerHTML = `<span class="npa-section-num">${full[1]}${punctuation}</span><span class="npa-section-title">${titlePart}</span>`;
                    }
                }
            }
            return;
        }
        match = plainText.match(/^Статья\s+[\dIVXLCDMа-яА-ЯёЁ¹²³⁴⁵⁶⁷⁸⁹⁰]+/iu);
        if (match) {
            p.classList.add('npa-article', 'npa-num-processed');
            if (hasSupSub) {
                p.innerHTML = `<span class="npa-article-num">${originalHtml}</span>`;
            } else {
                const full = plainText.match(/^((?:Статья)\s+[\dIVXLCDMа-яА-ЯёЁ¹²³⁴⁵⁶⁷⁸⁹⁰]+(?:[.\)]\d+)*)([\.\)]?)\s*(.*)$/iu);
                if (full) {
                    p.innerHTML = `<span class="npa-article-num">${full[1]}${full[2]}</span><span class="npa-article-title">${full[3]}</span>`;
                }
            }
            return;
        }
        match = plainText.match(/^Приложение\s+[\dIVXLCDMа-яА-ЯёЁ¹²³⁴⁵⁶⁷⁸⁹⁰]*/iu);
        if (match && plainText.length < 50) {
            p.classList.add('npa-article', 'npa-num-processed');
            if (hasSupSub) {
                p.innerHTML = `<span class="npa-article-num">${originalHtml}</span>`;
            } else {
                const full = plainText.match(/^((?:Приложение)\s*[\dIVXLCDMа-яА-ЯёЁ¹²³⁴⁵⁶⁷⁸⁹⁰]*)([\.\)]?)\s*$/iu);
                if (full) {
                    p.innerHTML = `<span class="npa-article-num">${full[1]}${full[2]}</span>`;
                }
            }
            return;
        }
    });
}
function updateRtfCaption() {
    const select = document.getElementById('npa-revision-select');
    const captionSpan = document.getElementById('rtf-caption');
    if (!captionSpan) return;
    if (select) {
        const selectedOpt = select.options[select.selectedIndex];
        if (selectedOpt) {
            const isOriginal = selectedOpt.getAttribute('data-is-original') === '1';
            const isCurrent = selectedOpt.getAttribute('data-is-current') === '1';
            const isLast = selectedOpt.getAttribute('data-is-last') === '1';
            let dateDisplay = selectedOpt.getAttribute('data-date-display') || '';
            if (!dateDisplay) {
                const match = selectedOpt.textContent.match(/\d{2}\.\d{2}\.\d{4}/);
                if (match) dateDisplay = match[0];
            }
            let captionText = '';
            if (isLast) {
                captionText = 'Последняя редакция от ' + dateDisplay;
            } else if (isOriginal) {
                captionText = 'Исходная редакция от ' + dateDisplay;
            } else if (isCurrent) {
                captionText = 'Действующая редакция от ' + dateDisplay;
            } else {
                captionText = 'Редакция от ' + dateDisplay;
            }
            captionSpan.textContent = captionText;
            return;
        }
    }
    const banner = document.querySelector('.npa-doc-status-banner.expired');
    if (banner) {
        const controls = document.querySelector('.npa-doc-controls');
        let date = controls ? controls.getAttribute('data-npa-date') : '';
        if (date) {
            const parts = date.split('-');
            if (parts.length === 3) {
                date = parts[2] + '.' + parts[1] + '.' + parts[0];
            }
            captionSpan.textContent = 'Последняя редакция от ' + date;
        } else {
            captionSpan.textContent = 'Последняя редакция';
        }
    } else {
        captionSpan.textContent = 'Действующая редакция';
    }
}
function syncSelectWithUrl() {
    const select = document.getElementById('npa-revision-select');
    if (!select) return;
    const urlParams = new URLSearchParams(window.location.search);
    const viewDate = urlParams.get('view_date');
    if (viewDate) {
        for (let i = 0; i < select.options.length; i++) {
            if (select.options[i].value === viewDate) {
                if (select.selectedIndex !== i) {
                    select.selectedIndex = i;
                    updateRtfCaption();
                }
                break;
            }
        }
    }
}
function updateTableHeadHeights() {
    document.querySelectorAll('.npa-doc-content table').forEach(table => {
        const thead = table.querySelector('thead');
        if (thead) {
            const height = thead.offsetHeight;
            table.style.setProperty('--th-height', height + 'px');
        }
    });
}
window.addEventListener('resize', function() {
    updateTableHeadHeights();
});
document.addEventListener('DOMContentLoaded', function() {
    loadStaticData();
    filterInvalidButtons();
    if (!document.getElementById('npa-modal-container')) {
        const mc = document.createElement('div');
        mc.id = 'npa-modal-container';
        document.body.appendChild(mc);
    }
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            const c = document.getElementById('npa-modal-container');
            if (c && c.style.display === 'block') {
                c.style.display = 'none';
                c.innerHTML = '';
                document.body.style.overflow = '';
            }
        }
    });
    initToggleButtons();
    initStructNumbers();
    initNPAHeadings();
    syncSelectWithUrl();
    updateRtfCaption();
    const selectEl = document.getElementById('npa-revision-select');
    if (selectEl) {
        selectEl.addEventListener('change', function() {
            updateRtfCaption();
        });
    }
    updateTableHeadHeights();
    document.addEventListener('click', function(e) {
        const btn = e.target.closest('.npa-item-btn');
        if (!btn) return;
        e.stopPropagation();
        e.preventDefault();
        let itemId = btn.dataset.itemId || null;
        let npaId = btn.dataset.npaId || 0;
        let revId = btn.dataset.revId || null;
        let context = btn.dataset.context || 'item';
        if (!itemId) {
            const ib = btn.closest('.npa-item-block');
            if (ib) {
                itemId = ib.id;
                if (!itemId) {
                    const a = ib.querySelector('.doc-toc-anchor');
                    if (a) itemId = a.id;
                }
            }
        }
        const text = btn.textContent.toLowerCase();
        let action = null;
        if (text.includes('истор')) action = 'history';
        else if (text.includes('сравн')) action = 'compare';
        else if (text.includes('предыдущ') || text.includes('редакци')) action = 'revision';
        if (action && itemId) {
            if (action === 'history') npaShowHistory(itemId, npaId, context);
            else if (action === 'compare') npaShowCompare(itemId, npaId, context);
            else if (action === 'revision') npaFetchRevision(revId, itemId, npaId, '', '', context);
        } else if (btn.getAttribute('onclick')) {
            try {
                new Function(btn.getAttribute('onclick'))();
            } catch (err) {
                console.error(err);
            }
        }
    }, true);
    (function() {
        const CONFIG = { lazyLoad: false, mobileBreakpoint: 768, showButtonAfter: 300 };
        const elements = { tocButton: null, tocPanel: null, tocOverlay: null, tocContainer: null, allLinks: null, allAnchors: null, expandAllBtn: null };
        const state = { isPanelOpen: false, panelInitialized: false, tocReady: false, allExpanded: false, tocItemsCount: 0, activeHighlightTimeout: null, scrollHashThrottle: null, lastHashUpdate: '' };
        function init() {
            elements.tocButton = document.getElementById('modx-toc-button');
            elements.tocPanel = document.getElementById('modx-toc-panel');
            if (!elements.tocButton || !elements.tocPanel) {
                console.error('TOC elements not found');
                return;
            }
            checkTOCContent();
            window.addEventListener('resize', handleResize);
        }
        function handleResize() {
            if (state.isPanelOpen && window.innerWidth <= CONFIG.mobileBreakpoint) adjustPanelHeight();
            if (elements.allAnchors) collectAllAnchors();
        }
        function adjustPanelHeight() {
            if (!elements.tocPanel || !state.isPanelOpen) return;
            if (window.innerWidth <= CONFIG.mobileBreakpoint) {
                const viewportHeight = window.innerHeight;
                elements.tocPanel.style.height = viewportHeight + 'px';
                const panelHeader = elements.tocPanel.querySelector('.toc-panel-header');
                const tocContainer = elements.tocPanel.querySelector('.toc-list-container');
                if (panelHeader && tocContainer) {
                    const headerHeight = panelHeader.offsetHeight;
                    tocContainer.style.maxHeight = 'calc(' + viewportHeight + 'px - ' + headerHeight + 'px)';
                }
            }
        }
        function checkTOCContent() {
            const tocContainer = elements.tocPanel.querySelector('.toc-list-container');
            const tocItems = elements.tocPanel.querySelectorAll('.toc-item');
            state.tocItemsCount = tocItems.length;
            if (tocContainer && (state.tocItemsCount > 0 || tocContainer.textContent.trim() !== '')) {
                setTimeout(initTOCSystem, 50);
            } else {
                const checkInterval = setInterval(function() {
                    const tc = elements.tocPanel.querySelector('.toc-list-container');
                    const ti = elements.tocPanel.querySelectorAll('.toc-item');
                    if ((tc && tc.textContent.trim() !== '') || ti.length > 0) {
                        clearInterval(checkInterval);
                        setTimeout(initTOCSystem, 50);
                    }
                }, 100);
                setTimeout(function() {
                    clearInterval(checkInterval);
                    if (!state.tocReady) showTOCButton();
                }, 5000);
            }
        }
        function collectAllAnchors() {
            const anchorSet = new Set();
            const tocLinks = document.querySelectorAll('.toc-link[href*="#"]');
            const targetIds = new Set();
            tocLinks.forEach(link => {
                const href = link.getAttribute('href');
                if (href && href.includes('#')) {
                    let hash = href.split('#').pop();
                    if (hash) targetIds.add(decodeURIComponent(hash));
                }
            });
            targetIds.forEach(id => {
                const elById = document.getElementById(id);
                if (elById && !elById.closest('#modx-toc-panel')) anchorSet.add(elById);
                else {
                    const elByName = document.querySelector(`[name="${id}"]`);
                    if (elByName && !elByName.closest('#modx-toc-panel')) anchorSet.add(elByName);
                }
            });
            elements.allAnchors = Array.from(anchorSet).sort((a, b) => (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING) ? -1 : 1);
            elements.allAnchors.forEach(anchor => {
                anchor._cachedTop = anchor.getBoundingClientRect().top + window.pageYOffset;
            });
        }
        function getCurrentActiveAnchorId() {
            var scrollPosition = window.pageYOffset + (window.innerWidth <= CONFIG.mobileBreakpoint ? 118 : 0);
            if (!elements.allAnchors || elements.allAnchors.length === 0) collectAllAnchors();
            if (!elements.allLinks) elements.allLinks = document.querySelectorAll('.toc-link[href*="#"]');
            var tocAnchorIds = [];
            elements.allLinks.forEach(function(link) {
                var href = link.getAttribute('href');
                if (href && href.includes('#')) {
                    var anchorId = '#' + href.split('#').pop();
                    if (!tocAnchorIds.includes(anchorId)) tocAnchorIds.push(anchorId);
                }
            });
            var currentAnchor = null, closestDistance = Infinity;
            for (var i = 0; i < elements.allAnchors.length; i++) {
                var anchor = elements.allAnchors[i];
                if (anchor.closest('#modx-toc-panel')) continue;
                var anchorId = anchor.id ? '#' + anchor.id : anchor.getAttribute('name') ? '#' + anchor.getAttribute('name') : null;
                if (!anchorId || !tocAnchorIds.includes(anchorId)) continue;
                var anchorTop = anchor._cachedTop !== undefined ? anchor._cachedTop : (anchor.getBoundingClientRect().top + window.pageYOffset);
                var distance = Math.abs(anchorTop - scrollPosition);
                if (anchorTop <= scrollPosition + 50 && distance < closestDistance) {
                    closestDistance = distance;
                    currentAnchor = anchor;
                }
            }
            if (currentAnchor) return currentAnchor.id ? '#' + currentAnchor.id : currentAnchor.getAttribute('name') ? '#' + currentAnchor.getAttribute('name') : null;
            return null;
        }
        function initTOCSystem() {
            createOverlay();
            setupEventListeners();
            initTreeStructure();
            collectAllAnchors();
            state.tocReady = true;
            if (window.location.hash) {
                setTimeout(function() {
                    var anchorId = window.location.hash;
                    var targetElement = getCachedAnchorElement(anchorId);
                    if (targetElement) {
                        highlightActiveTocLink(anchorId);
                        expandParentsOfActiveLink(anchorId);
                        var tocContainer = elements.tocContainer || document.querySelector('.toc-list-container');
                        if (tocContainer) {
                            var activeLink = tocContainer.querySelector('.toc-link.active');
                            if (activeLink) {
                                setTimeout(function() {
                                    var containerTop = tocContainer.getBoundingClientRect().top;
                                    var linkTop = activeLink.getBoundingClientRect().top;
                                    var containerScrollTop = tocContainer.scrollTop;
                                    var relativePosition = linkTop - containerTop;
                                    var containerHeight = tocContainer.clientHeight;
                                    var linkHeight = activeLink.offsetHeight;
                                    var targetScrollTop = containerScrollTop + relativePosition - (containerHeight / 2) + (linkHeight / 2);
                                    tocContainer.scrollTo({ top: Math.max(0, targetScrollTop), behavior: 'smooth' });
                                }, 300);
                            }
                        }
                    }
                    setTimeout(function() {
                        scrollToAnchor(anchorId);
                    }, 500);
                }, 500);
            }
            var isMobile = window.innerWidth <= CONFIG.mobileBreakpoint;
            if (!isMobile) setTimeout(showTOCButton, CONFIG.showButtonAfter);
            else showTOCButton();
        }
        function initTreeStructure() {
            var tocContainer = elements.tocPanel.querySelector('.toc-list-container');
            if (!tocContainer) return;
            elements.tocContainer = tocContainer;
            addExpandAllButton();
            var allLists = tocContainer.querySelectorAll('.toc-list');
            allLists.forEach(list => list.style.display = '');
            var allItems = tocContainer.querySelectorAll('.toc-item');
            allItems.forEach(item => item.classList.remove('expanded'));
            var level0Items = tocContainer.querySelectorAll('.toc-item.level-0');
            level0Items.forEach(item => {
                item.classList.add('expanded');
                var toggleBtn = item.querySelector('.toc-toggle');
                if (toggleBtn) toggleBtn.remove();
            });
            var allNonLevel0Items = tocContainer.querySelectorAll('.toc-item:not(.level-0)');
            allNonLevel0Items.forEach(item => {
                var childLists = item.querySelectorAll('.toc-list');
                var hasChildLists = childLists.length > 0;
                var childItems = item.querySelectorAll('.toc-item');
                var hasChildItems = childItems.length > 0;
                if (hasChildLists || hasChildItems) {
                    item.classList.add('has-children');
                    item.classList.remove('expanded');
                    addToggleButton(item);
                    if (hasChildLists && !item.classList.contains('expanded')) childLists.forEach(list => list.style.display = 'none');
                } else {
                    item.classList.remove('has-children');
                    var toggleBtn = item.querySelector('.toc-toggle');
                    if (toggleBtn) toggleBtn.remove();
                }
            });
        }
        function addExpandAllButton() {
            var panelHeader = elements.tocPanel.querySelector('.toc-panel-header');
            if (!panelHeader || panelHeader.querySelector('.toc-expand-all')) return;
            elements.expandAllBtn = document.createElement('button');
            elements.expandAllBtn.className = 'toc-expand-all';
            elements.expandAllBtn.innerHTML = 'Развернуть все';
            elements.expandAllBtn.title = 'Развернуть/свернуть все пункты оглавления';
            elements.expandAllBtn.setAttribute('aria-label', 'Развернуть или свернуть все разделы оглавления');
            var title = panelHeader.querySelector('.toc-panel-title');
            if (title) title.parentNode.insertBefore(elements.expandAllBtn, title.nextSibling);
            elements.expandAllBtn.addEventListener('click', function(e) {
                e.stopPropagation();
                toggleAllItems();
                setTimeout(function() {
                    this.blur();
                }.bind(this), 10);
            });
        }
        function addToggleButton(item) {
            var link = item.querySelector('.toc-link');
            if (!link || item.querySelector('.toc-toggle')) return;
            var toggleBtn = document.createElement('button');
            toggleBtn.className = 'toc-toggle';
            toggleBtn.innerHTML = '▶';
            toggleBtn.setAttribute('aria-label', 'Развернуть/свернуть раздел');
            toggleBtn.setAttribute('tabindex', '0');
            link.parentNode.insertBefore(toggleBtn, link.nextSibling);
            toggleBtn.addEventListener('click', function(e) {
                e.stopPropagation();
                e.preventDefault();
                toggleItem(item);
                setTimeout(function() {
                    this.blur();
                }.bind(this), 10);
            });
            toggleBtn.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    toggleItem(item);
                }
            });
        }
        function toggleItem(item) {
            var isExpanded = item.classList.contains('expanded');
            if (isExpanded) {
                item.classList.remove('expanded');
                var toggleBtn = item.querySelector(':scope > .toc-toggle');
                if (toggleBtn) {
                    toggleBtn.innerHTML = '▶';
                    toggleBtn.classList.remove('expanded');
                }
                var childLists = item.querySelectorAll(':scope > .toc-list');
                childLists.forEach(list => list.style.display = 'none');
                var nestedItems = item.querySelectorAll('.toc-item.has-children');
                nestedItems.forEach(nestedItem => {
                    nestedItem.classList.remove('expanded');
                    var nestedToggleBtn = nestedItem.querySelector(':scope > .toc-toggle');
                    if (nestedToggleBtn) {
                        nestedToggleBtn.innerHTML = '▶';
                        nestedToggleBtn.classList.remove('expanded');
                    }
                    var nestedChildLists = nestedItem.querySelectorAll(':scope > .toc-list');
                    nestedChildLists.forEach(list => list.style.display = 'none');
                });
            } else {
                item.classList.add('expanded');
                var toggleBtn = item.querySelector(':scope > .toc-toggle');
                if (toggleBtn) {
                    toggleBtn.innerHTML = '▼';
                    toggleBtn.classList.add('expanded');
                }
                var childLists = item.querySelectorAll(':scope > .toc-list');
                childLists.forEach(list => list.style.display = 'block');
            }
            updateExpandAllButtonState();
        }
        function toggleAllItems() {
            state.allExpanded = !state.allExpanded;
            var itemsWithChildren = elements.tocPanel.querySelectorAll('.toc-item.has-children:not(.level-0)');
            itemsWithChildren.forEach(item => {
                if (state.allExpanded) {
                    item.classList.add('expanded');
                    var toggleBtn = item.querySelector(':scope > .toc-toggle');
                    if (toggleBtn) {
                        toggleBtn.innerHTML = '▼';
                        toggleBtn.classList.add('expanded');
                    }
                    var childLists = item.querySelectorAll(':scope > .toc-list');
                    childLists.forEach(list => list.style.display = 'block');
                } else {
                    item.classList.remove('expanded');
                    var toggleBtn = item.querySelector(':scope > .toc-toggle');
                    if (toggleBtn) {
                        toggleBtn.innerHTML = '▶';
                        toggleBtn.classList.remove('expanded');
                    }
                    var childLists = item.querySelectorAll(':scope > .toc-list');
                    childLists.forEach(list => list.style.display = 'none');
                }
            });
            updateExpandAllButtonState();
        }
        function updateExpandAllButtonState() {
            if (!elements.expandAllBtn) return;
            var itemsWithChildren = elements.tocPanel.querySelectorAll('.toc-item.has-children:not(.level-0)');
            var allAreExpanded = true;
            itemsWithChildren.forEach(item => {
                if (!item.classList.contains('expanded')) allAreExpanded = false;
            });
            state.allExpanded = allAreExpanded;
            elements.expandAllBtn.innerHTML = state.allExpanded ? 'Свернуть все' : 'Развернуть все';
        }
        function showTOCButton() {
            elements.tocButton.classList.add('toc-button-ready');
        }
        function createOverlay() {
            if (document.getElementById('modx-toc-overlay')) {
                elements.tocOverlay = document.getElementById('modx-toc-overlay');
                return;
            }
            elements.tocOverlay = document.createElement('div');
            elements.tocOverlay.className = 'toc-overlay';
            elements.tocOverlay.id = 'modx-toc-overlay';
            document.body.appendChild(elements.tocOverlay);
        }
        function setupEventListeners() {
            elements.tocButton.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                if (state.isPanelOpen) closePanel();
                else openPanel();
            });
            if (elements.tocOverlay) elements.tocOverlay.addEventListener('click', function() {
                closePanel();
            });
            var closeBtn = elements.tocPanel.querySelector('.toc-panel-close');
            if (closeBtn) closeBtn.addEventListener('click', function() {
                closePanel();
            });
            elements.tocPanel.addEventListener('click', function(e) {
                var link = e.target.closest('.toc-link');
                if (link) {
                    e.preventDefault();
                    var href = link.getAttribute('href');
                    if (href && href.includes('#')) {
                        var anchorId = '#' + href.split('#').pop();
                        highlightActiveTocLink(anchorId);
                        scrollToAnchor(anchorId);
                        if (window.innerWidth <= CONFIG.mobileBreakpoint) closePanel();
                    }
                }
            });
            var scrollTimeout;
            window.addEventListener('scroll', function() {
                clearTimeout(scrollTimeout);
                scrollTimeout = setTimeout(function() {
                    var activeId = getCurrentActiveAnchorId();
                    if (activeId && window.location.hash !== activeId) {
                        var newUrl = window.location.pathname + window.location.search + activeId;
                        history.replaceState(null, null, newUrl);
                    }
                    highlightActiveTocLink(activeId);
                }, 150);
            });
        }
        function openPanel() {
            state.isPanelOpen = true;
            elements.tocPanel.classList.add('show');
            if (elements.tocOverlay) elements.tocOverlay.classList.add('show');
            elements.tocButton.classList.add('active');
            document.body.style.overflow = 'hidden';
            adjustPanelHeight();
            setTimeout(function() {
                var activeId = getCurrentActiveAnchorId();
                if (activeId) {
                    highlightActiveTocLink(activeId);
                    expandParentsOfActiveLink(activeId);
                    var container = elements.tocContainer || document.querySelector('.toc-list-container');
                    if (container) {
                        var activeLink = container.querySelector('.toc-link.active');
                        if (activeLink) {
                            var containerTop = container.getBoundingClientRect().top;
                            var linkTop = activeLink.getBoundingClientRect().top;
                            var containerScrollTop = container.scrollTop;
                            var relativePosition = linkTop - containerTop;
                            var containerHeight = container.clientHeight;
                            var linkHeight = activeLink.offsetHeight;
                            var targetScrollTop = containerScrollTop + relativePosition - (containerHeight / 2) + (linkHeight / 2);
                            container.scrollTo({ top: Math.max(0, targetScrollTop), behavior: 'smooth' });
                        }
                    }
                }
            }, 150);
        }
        function closePanel() {
            state.isPanelOpen = false;
            elements.tocPanel.classList.remove('show');
            if (elements.tocOverlay) elements.tocOverlay.classList.remove('show');
            elements.tocButton.classList.remove('active');
            document.body.style.overflow = '';
        }
        function highlightActiveTocLink(anchorId) {
            if (!elements.tocPanel) return;
            var allLinks = elements.tocPanel.querySelectorAll('.toc-link');
            allLinks.forEach(link => link.classList.remove('active'));
            if (!anchorId) return;
            var targetLink = elements.tocPanel.querySelector('.toc-link[href$="' + anchorId + '"]');
            if (targetLink) targetLink.classList.add('active');
        }
        function expandParentsOfActiveLink(anchorId) {
            if (!elements.tocPanel || !anchorId) return;
            var targetLink = elements.tocPanel.querySelector('.toc-link[href$="' + anchorId + '"]');
            if (targetLink) {
                var parentItem = targetLink.closest('.toc-item');
                while (parentItem) {
                    var parentList = parentItem.parentElement;
                    if (parentList && parentList.classList.contains('toc-list')) {
                        var grandParentItem = parentList.closest('.toc-item');
                        if (grandParentItem && grandParentItem.classList.contains('has-children') && !grandParentItem.classList.contains('expanded')) {
                            grandParentItem.classList.add('expanded');
                            var toggleBtn = grandParentItem.querySelector(':scope > .toc-toggle');
                            if (toggleBtn) {
                                toggleBtn.innerHTML = '▼';
                                toggleBtn.classList.add('expanded');
                            }
                            parentList.style.display = 'block';
                        }
                        parentItem = grandParentItem;
                    } else break;
                }
            }
        }
        function scrollToAnchor(anchorId) {
            var targetElement = getCachedAnchorElement(anchorId);
            if (!targetElement) return;
            var headerOffset = window.innerWidth <= CONFIG.mobileBreakpoint ? 118 : 10;
            var elementPosition = targetElement.getBoundingClientRect().top + window.pageYOffset;
            var offsetPosition = elementPosition - headerOffset;
            window.scrollTo({ top: offsetPosition, behavior: 'smooth' });
        }
        function getCachedAnchorElement(anchorId) {
            if (!anchorId) return null;
            var cleanId = anchorId.replace('#', '');
            var el = document.getElementById(cleanId);
            if (el) return el;
            var namedEl = document.querySelector('[name="' + cleanId + '"]');
            if (namedEl) return namedEl;
            return null;
        }
        function expandDirectChildren(tocItem) {
            if (!tocItem.classList.contains('has-children')) return;
            if (!tocItem.classList.contains('expanded')) {
                tocItem.classList.add('expanded');
                var toggleBtn = tocItem.querySelector(':scope > .toc-toggle');
                if (toggleBtn) {
                    toggleBtn.innerHTML = '▼';
                    toggleBtn.classList.add('expanded');
                }
                var childLists = tocItem.querySelectorAll(':scope > .toc-list');
                childLists.forEach(list => list.style.display = 'block');
            }
        }
        function modifyTocLinkHandler() {
            var newHandler = function(e) {
                var link = e.target.closest('.toc-link');
                if (link) {
                    e.preventDefault();
                    var href = link.getAttribute('href');
                    if (href && href.includes('#')) {
                        var anchorId = '#' + href.split('#').pop();
                        var tocItem = link.closest('.toc-item');
                        if (tocItem && tocItem.classList.contains('has-children')) expandDirectChildren(tocItem);
                        highlightActiveTocLink(anchorId);
                        scrollToAnchor(anchorId);
                        if (window.innerWidth <= CONFIG.mobileBreakpoint) closePanel();
                    }
                }
            };
            elements.tocPanel.removeEventListener('click', elements.tocPanel._clickHandler);
            elements.tocPanel.addEventListener('click', newHandler);
            elements.tocPanel._clickHandler = newHandler;
        }
        init();
        setTimeout(function() {
            if (elements.tocPanel) modifyTocLinkHandler();
        }, 100);
    })();
    document.addEventListener('click', function(e) {
        const link = e.target.closest('.npa-view-expired');
        if (!link) return;
        e.preventDefault();
        const itemId = link.dataset.itemId;
        const npaId = link.dataset.npaId;
        const expiredBlock = link.closest('.npa-item-block');
        const jsonScript = expiredBlock ? expiredBlock.querySelector('.npa-expired-content') : null;
        let modalTitle = expiredBlock ? expiredBlock.dataset.modalTitle : null;
        if (!modalTitle) {
            modalTitle = 'Текст утратившего силу элемента';
        }
        let contentHtml = '';
        if (jsonScript) {
            try {
                contentHtml = JSON.parse(jsonScript.textContent);
            } catch (er) {
                contentHtml = '<p><i>Содержимое недоступно</i></p>';
            }
        } else {
            contentHtml = '<p><i>Содержимое недоступно</i></p>';
        }
        npaShowModal(modalTitle, contentHtml, false);
    });
    document.addEventListener('click', function(e) {
        const link = e.target.closest('a[href^="#"]');
        if (!link) return;
        const targetId = link.getAttribute('href').substring(1);
        const targetElement = document.getElementById(targetId);
        if (targetElement) {
            e.preventDefault();
            const table = targetElement.closest('table');
            let offset = 0;
            if (table) {
                const thead = table.querySelector('thead');
                if (thead) {
                    offset = thead.offsetHeight;
                }
            }
            const elementPosition = targetElement.getBoundingClientRect().top + window.pageYOffset;
            const offsetPosition = elementPosition - offset;
            window.scrollTo({
                top: offsetPosition,
                behavior: 'smooth'
            });
            history.pushState(null, null, `#${targetId}`);
        }
    });
    document.addEventListener('click', function(e) {
        const icon = e.target.closest('.npa-doc-notes-header .toggle-buttons-icon');
        if (icon) {
            const targetId = icon.getAttribute('data-target');
            if (targetId) {
                const body = document.getElementById(targetId) || document.querySelector('.' + targetId);
                if (body) {
                    const isHidden = body.style.display === 'none' || body.style.display === '';
                    body.style.display = isHidden ? 'block' : 'none';
                    icon.className = 'toggle-buttons-icon ' + (isHidden ? 'opened' : 'closed');
                    icon.setAttribute('aria-label', isHidden ? 'Скрыть примечания' : 'Показать примечания');
                }
            }
        }
    });
});