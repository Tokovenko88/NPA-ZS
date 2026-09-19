<?php
/**
 * NPA-ZS | ui/notes.php — примечания к элементам и заголовкам.
 *
 * Функции: isOriginalRevision, splitChangerIds, isIntroductionInheritedFromAncestor,
 *          getItemHeadRevisionNotes, getElementRevisionNotes, filterNotesByValidTo.
 * Источник: строки 1039-1123, 2786-2875 монолита snippet.php.
 */

function isOriginalRevision(array $rev): bool {
    return empty($rev['mod_type']) && empty($rev['modified_by_id']);
}

function getItemHeadRevisionNotes($internal_item_id, $pdo, $viewDate, $itemType, array $selectedRevisionNpaIds = [], $baseNpaId = null) {
    $currentRev = getItemHeadRevisionForSelectedEdition($pdo, $internal_item_id, $viewDate, $selectedRevisionNpaIds);
    if (!$currentRev || empty($currentRev['id'])) return '';

    $currentRevId = (int)$currentRev['id'];
    $currentRevIsOriginal = isOriginalRevision($currentRev);

    $sql = "SELECT r.* FROM npa_item_head_revision r
            WHERE r.item_internal_id = ?
              AND (r.valid_from IS NULL OR r.valid_from <= ?";
    $params = [$internal_item_id, $currentRev['valid_from']];

    if (!empty($selectedRevisionNpaIds)) {
        $placeholders = buildRevisionNpaIdPlaceholders($selectedRevisionNpaIds);
        $sql .= " OR EXISTS (
            SELECT 1 FROM npa_item changer
            WHERE changer.npa_id IN ($placeholders)
              AND INSTR(BINARY CONCAT(',', REPLACE(COALESCE(r.modified_by_id, ''), ' ', ''), ','), BINARY CONCAT(',', CAST(changer.id AS CHAR), ',')) > 0
        )";
        $params = array_merge($params, array_values($selectedRevisionNpaIds));
    }
    $sql .= ") ORDER BY r.valid_from ASC, r.id ASC";
    
    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    $allRevisions = $stmt->fetchAll();

    $allowedRevisions = [];
    foreach ($allRevisions as $rev) {
        if ((int)$rev['id'] <= $currentRevId) $allowedRevisions[] = $rev;
    }
    if (empty($allowedRevisions)) return '';

    $addNote = $newRedactionNote = null;
    $changeNotes = [];
    $seenChangeNpaIds = [];

    foreach ($allowedRevisions as $rev) {
        $shortDesc = getShortNpaDescription($rev['modified_by_id'], $pdo, true);
        if ($shortDesc === 'исходная редакция') continue;

        switch ($rev['mod_type']) {
            case 'add': if ($addNote === null) $addNote = getShortNpaDescription($rev['modified_by_id'], $pdo, true, 'nominative'); break;
            case 'new_redaction': $newRedactionNote = getShortNpaDescription($rev['modified_by_id'], $pdo, true, 'nominative'); break;
            case 'change':
                $npaInfo = getNpaInfoByItemId($rev['modified_by_id'], $pdo);
                if ($npaInfo && !in_array($npaInfo['npa_id'], $seenChangeNpaIds, true)) {
                    $seenChangeNpaIds[] = $npaInfo['npa_id'];
                    $changeNotes[] = $shortDesc;
                }
                break;
        }
    }

    $parts = [];
    if ($addNote) $parts[] = '<span class="revision-note">Заголовок введен — ' . $addNote . '</span>';
    if ($newRedactionNote) $parts[] = '<span class="revision-note">Заголовок в редакции — ' . $newRedactionNote . '</span>';
    if (!empty($changeNotes)) $parts[] = '<span class="revision-note">Заголовок изменен: ' . implode(', ', $changeNotes) . '</span>';

    if (empty($parts) && !empty($baseNpaId) && !empty($selectedRevisionNpaIds)) {
        $allNull = true;
        foreach ($allowedRevisions as $rev) {
            if (!empty($rev['mod_type']) || !empty($rev['modified_by_id'])) $allNull = false;
        }
        if ($allNull && !empty($currentRev['valid_from'])) {
            $law = getIntroducingLawForDate($pdo, $baseNpaId, $currentRev['valid_from']);
            if ($law) {
                $lawShort = getShortNpaDescription($law['revision_id'], $pdo, true, 'nominative');
                if ($lawShort !== 'исходная редакция') $addNote = $lawShort;
            }
        }
        if ($addNote) $parts[] = '<span class="revision-note">Заголовок введен — ' . $addNote . '</span>';
    }

    if (empty($parts)) return '';

    $dateBlock = '';
    if (!$currentRevIsOriginal) {
        $dt = parseDate($currentRev['valid_from'] ?? null);
        $validFromDate = $dt ? $dt->format('d.m.Y') : '';
        $isDeferred = isDeferredSelectedEditionRevision($currentRev, $viewDate, $selectedRevisionNpaIds);
        $dateBlock = buildRevisionEffectiveDateBlock($validFromDate, $isDeferred);
    }

    return '<div class="element-revision-notes" style="margin: 0.5em 0;">'
         . $dateBlock . implode('<br>', $parts) . '</div>';
}

/**
 * Разбирает modified_by_id («143532,143624») в список идентификаторов
 * элементов изменяющего НПА. Служебное значение «base» (исходная редакция)
 * отбрасывается.
 *
 * @param mixed $modifiedById Значение npa_item_revision.modified_by_id.
 * @return array Список идентификаторов (возможно пустой).
 */
function splitChangerIds($modifiedById) {
    $ids = [];
    foreach (explode(',', (string)($modifiedById ?? '')) as $part) {
        $part = trim($part);
        if ($part !== '' && $part !== 'base') $ids[] = $part;
    }
    return $ids;
}

/**
 * Введён ли элемент «вместе с предком» тем же изменяющим НПА?
 *
 * Когда структурный элемент вводится (mod_type='add') или излагается в новой
 * редакции (mod_type='new_redaction'), все его потомки из нового содержимого
 * получают собственную ревизию 'add' с тем же изменяющим НПА и той же датой
 * вступления в силу. Примечание «Введён — …» под каждым таким потомком
 * избыточно: из примечания «Введён …»/«В редакции …» на самом элементе уже
 * следует, что весь его состав введён тем же НПА.
 *
 * Примечание скрывается только при точном совпадении: у одного из предков
 * (цепочка npa_item.parent_id, глубина ≤ 20) есть ревизия 'add' или
 * 'new_redaction' с тем же изменяющим НПА (пересечение modified_by_id) и той же
 * датой valid_from. Если позже ДРУГОЙ НПА добавит дочерний элемент в уже
 * введённый элемент, его собственная 'add'-ревизия с ревизией предка не
 * совпадёт — примечание «Введён …» для него выводится (как и требуется).
 *
 * @param PDO   $pdo            Соединение с БД.
 * @param int   $internalItemId npa_item.id проверяемого элемента.
 * @param array $addRevision    Ревизия с mod_type='add' (valid_from, modified_by_id).
 * @return bool true — примечание «Введён …» избыточно и выводиться не должно.
 */
function isIntroductionInheritedFromAncestor($pdo, $internalItemId, $addRevision) {
    static $parentByItemId = [];
    static $revisionsByItemId = [];

    $addDate = parseDate($addRevision['valid_from'] ?? null);
    $addChangers = splitChangerIds($addRevision['modified_by_id'] ?? '');
    if (!$addDate || empty($addChangers)) return false;
    $addDateKey = $addDate->format('Y-m-d');

    $itemId = (int)$internalItemId;
    $depth = 0;
    while ($itemId > 0 && $depth < 20) {
        if (!array_key_exists($itemId, $parentByItemId)) {
            $stmt = $pdo->prepare("SELECT parent_id FROM npa_item WHERE id = ?");
            $stmt->execute([$itemId]);
            $row = $stmt->fetch(PDO::FETCH_ASSOC);
            $parentByItemId[$itemId] = $row ? (int)$row['parent_id'] : 0;
        }
        $ancestorId = $parentByItemId[$itemId];
        if ($ancestorId <= 0) break;

        if (!array_key_exists($ancestorId, $revisionsByItemId)) {
            $stmt = $pdo->prepare("SELECT valid_from, mod_type, modified_by_id
                                   FROM npa_item_revision WHERE item_internal_id = ?");
            $stmt->execute([$ancestorId]);
            $revisionsByItemId[$ancestorId] = $stmt->fetchAll(PDO::FETCH_ASSOC);
        }
        foreach ($revisionsByItemId[$ancestorId] as $ancestorRev) {
            if ($ancestorRev['mod_type'] !== 'add' && $ancestorRev['mod_type'] !== 'new_redaction') continue;
            $ancestorDate = parseDate($ancestorRev['valid_from'] ?? null);
            if (!$ancestorDate || $ancestorDate->format('Y-m-d') !== $addDateKey) continue;
            if (array_intersect($addChangers, splitChangerIds($ancestorRev['modified_by_id'] ?? ''))) {
                return true;
            }
        }
        $itemId = $ancestorId;
        $depth++;
    }
    return false;
}

function getElementRevisionNotes($internal_item_id, $pdo, $baseNpaId, $npaType, $viewDate, $itemType, array $selectedRevisionNpaIds = []) {
    $currentRev = getRevisionForSelectedEdition($pdo, $internal_item_id, $viewDate, $selectedRevisionNpaIds);
    if (!$currentRev || empty($currentRev['rev_id'])) return '';

    $currentRevId = (int)$currentRev['rev_id'];
    $currentRevIsOriginal = isOriginalRevision($currentRev);

    $sql = "SELECT r.* FROM npa_item_revision r
            WHERE r.item_internal_id = ?
              AND (r.valid_from IS NULL OR r.valid_from <= ?";
    $params = [$internal_item_id, $currentRev['valid_from']];

    if (!empty($selectedRevisionNpaIds)) {
        $placeholders = buildRevisionNpaIdPlaceholders($selectedRevisionNpaIds);
        $sql .= " OR EXISTS (
            SELECT 1 FROM npa_item changer
            WHERE changer.npa_id IN ($placeholders)
              AND INSTR(BINARY CONCAT(',', REPLACE(COALESCE(r.modified_by_id, ''), ' ', ''), ','), BINARY CONCAT(',', CAST(changer.id AS CHAR), ',')) > 0
        )";
        $params = array_merge($params, array_values($selectedRevisionNpaIds));
    }
    $sql .= ") ORDER BY r.valid_from ASC, r.rev_id ASC";

    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    $allRevisions = $stmt->fetchAll();

    $allowedRevisions = [];
    foreach ($allRevisions as $rev) {
        if ((int)$rev['rev_id'] <= $currentRevId) $allowedRevisions[] = $rev;
    }
    if (empty($allowedRevisions)) return '';

    $addNote = null;
    $newRedactionNote = null;
    $changeNotes = [];
    $seenChangeNpaIds = [];
    $ownChangerIds = [];

    foreach ($allowedRevisions as $rev) {
        $shortDesc = getShortNpaDescription($rev['modified_by_id'], $pdo, true);
        if ($shortDesc === 'исходная редакция') continue;

        switch ($rev['mod_type']) {
            case 'add':
                // Потомки введённого (или изложенного в новой редакции) элемента
                // не повторяют «Введён — …»: их введение уже следует из
                // примечания предка (см. isIntroductionInheritedFromAncestor).
                // Если элемент введён позже другим НПА, совпадения с предком нет
                // и примечание выводится.
                if ($addNote === null && !isIntroductionInheritedFromAncestor($pdo, $internal_item_id, $rev)) {
                    $addNote = getShortNpaDescription($rev['modified_by_id'], $pdo, true, 'nominative');
                }
                break;
            case 'new_redaction': $newRedactionNote = getShortNpaDescription($rev['modified_by_id'], $pdo, true, 'nominative'); break;
            case 'change':
                $npaInfo = getNpaInfoByItemId($rev['modified_by_id'], $pdo);
                if ($npaInfo && !in_array($npaInfo['npa_id'], $seenChangeNpaIds, true)) {
                    $seenChangeNpaIds[] = $npaInfo['npa_id'];
                    $changeNotes[] = $shortDesc;
                }
                break;
        }
        foreach (array_filter(array_map('trim', explode(',', (string)($rev['modified_by_id'] ?? '')))) as $mid) {
            if ($mid !== '' && $mid !== 'base') $ownChangerIds[$mid] = true;
        }
    }

    // Если собственная ревизия структурного элемента не была создана этой
    // НПА, но НПА всё равно удалила его дочерние элементы (их
    // npa_item_revision.not_valid ссылается на эту НПА) — добавим такую
    // НПА в список «С изменениями», чтобы пользователь видел причину.
    // Ищем удаления в body предыдущей редакции, чтобы не пропустить
    // дочерние элементы, чьи child_ref уже удалены из текущей редакции.
    //
    // Пузырьковый подъём дочерних changers на родителя пропускаем, если
    // собственная ревизия элемента — исходная (mod_type/modified_by_id пусты).
    // Иначе для элемента, чьи дочерние правки и так уже отмечены примечаниями
    // на самих дочерних элементах, всплывало бы ложное «С изменениями: …» на
    // уровне родителя (см. жалобу по ст. 6 закона 127‑ЗС). На сравнение
    // редакций это не влияет: там используется collectExpiredChildChanges()
    // в content/compare.php, эта ветка только для публичных примечаний.
    if (!$currentRevIsOriginal) {
        $ownChangerIdsList = array_keys($ownChangerIds);
        $prevRevForNotes = getPreviousItemRevision($pdo, $internal_item_id, $currentRevId);
        $childChangerNotes = collectExpiredChildChangerNotes(
            $pdo,
            $internal_item_id,
            $viewDate,
            $ownChangerIdsList,
            $selectedRevisionNpaIds,
            $currentRevId,
            $prevRevForNotes ? $prevRevForNotes['rev_id'] : null
        );
        foreach ($childChangerNotes as $modifiedById) {
            $npaInfo = getNpaInfoByItemId($modifiedById, $pdo);
            if ($npaInfo && !in_array($npaInfo['npa_id'], $seenChangeNpaIds, true)) {
                $seenChangeNpaIds[] = $npaInfo['npa_id'];
                $changeNotes[] = getShortNpaDescription($modifiedById, $pdo, true);
            } elseif (!$npaInfo) {
                $desc = getShortNpaDescription($modifiedById, $pdo, true);
                if ($desc && $desc !== 'исходная редакция' && !in_array($desc, $changeNotes, true)) {
                    $changeNotes[] = $desc;
                }
            }
        }
    }

    $genderSuffix = '';
    if ($itemType === 'article' || $itemType === 'part') $genderSuffix = 'а';
    elseif ($itemType === 'appendix') $genderSuffix = 'о';

    $parts = [];
    if ($addNote) $parts[] = '<span class="revision-note">Введен' . $genderSuffix . ' — ' . $addNote . '</span>';
    if ($newRedactionNote) $parts[] = '<span class="revision-note">В редакции — ' . $newRedactionNote . '</span>';
    if (!empty($changeNotes)) $parts[] = '<span class="revision-note">С изменениями: ' . implode(', ', $changeNotes) . '</span>';

    if (empty($parts) && !empty($baseNpaId) && !empty($selectedRevisionNpaIds)) {
        $allNull = true;
        foreach ($allowedRevisions as $rev) {
            if (!empty($rev['mod_type']) || !empty($rev['modified_by_id'])) $allNull = false;
        }
        if ($allNull && !empty($currentRev['valid_from'])) {
            $law = getIntroducingLawForDate($pdo, $baseNpaId, $currentRev['valid_from']);
            if ($law) {
                $lawShort = getShortNpaDescription($law['revision_id'], $pdo, true, 'nominative');
                if ($lawShort !== 'исходная редакция') $addNote = $lawShort;
            }
        }
        if ($addNote) $parts[] = '<span class="revision-note">Введен' . $genderSuffix . ' — ' . $addNote . '</span>';
    }

    if (empty($parts)) return '';

    $dateBlock = '';
    if (!$currentRevIsOriginal) {
        $dt = parseDate($currentRev['valid_from'] ?? null);
        $validFromDate = $dt ? $dt->format('d.m.Y') : '';
        $isDeferred = isDeferredSelectedEditionRevision($currentRev, $viewDate, $selectedRevisionNpaIds);
        $dateBlock = buildRevisionEffectiveDateBlock($validFromDate, $isDeferred);
    }

    return '<div class="element-revision-notes" style="margin: 0.5em 0;">'
         . $dateBlock . implode('<br>', $parts) . '</div>';
}

/**
 * Фильтрует примечания (npa_note_unified) по правилу отображения
 * (docs/db_schema.md §6.1.4, §6.2, docs/site_output.md §8.4):
 *
 *   Примечание выводится только если его valid_to не задан (бессрочно)
 *   ИЛИ valid_to >= даты вступления в силу выбранной редакции ($editionDate).
 *   Примечание, у которого valid_to меньше даты вступления в силу выбранной
 *   редакции, считается истёкшим и не выводится.
 *
 * $editionDate — дата вступления в силу выбранной редакции (view_date);
 * поддерживаются форматы 'Y-m-d' и 'd.m.Y' (через parseDate()).
 *
 * @param array $notes       Список примечаний (строки npa_note_unified).
 * @param mixed $editionDate Дата вступления в силу выбранной редакции.
 * @return array Отфильтрованный список примечаний.
 */
function filterNotesByValidTo(array $notes, $editionDate) {
    $edition = parseDate($editionDate);
    if (!$edition) {
        // Дата просмотра неизвестна — не принимаем решений, показываем как есть.
        return array_values($notes);
    }
    $editionStr = $edition->format('Y-m-d');
    $filtered = [];
    foreach ($notes as $note) {
        $validTo = parseDate($note['valid_to'] ?? null);
        // Бессрочные примечания (valid_to NULL/'') показываются всегда;
        // истёкшие (valid_to < даты вступления в силу редакции) — скрываются.
        if ($validTo === null || $validTo->format('Y-m-d') >= $editionStr) {
            $filtered[] = $note;
        }
    }
    return $filtered;
}

