<?php
/**
 * NPA-ZS | ui/notes.php — примечания к элементам и заголовкам.
 *
 * Функции: isOriginalRevision, splitChangerIds, isIntroductionInheritedFromAncestor,
 *          hasAncestorNewRedactionByNpaId, hasStrictAncestorNewRedactionByNpaId,
 *          isNewRedactionNoteSuppressedByAncestor,
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
            case 'new_redaction':
                // Дочерний элемент в новой редакции того же НПА, что переписал
                // предка: «Заголовок в редакции — …» избыточен, только если это
                // последняя ревизия элемента И строгий предок имеет new_redaction
                // этого же НПА (см. isNewRedactionNoteSuppressedByAncestor —
                // та же проверка гасит и блок кнопок целиком). Другой НПА /
                // не последняя ревизия / нет предка с new_redaction —
                // показываем, как раньше.
                $isLastRevNr = ((int)$rev['id'] === $currentRevId);
                if ($isLastRevNr && isNewRedactionNoteSuppressedByAncestor($pdo, $internal_item_id, $rev, $currentRevId, 'id')) {
                    // Подавляем: примечание избыточно (покрыто предком).
                    $newRedactionNote = null;
                } else {
                    $newRedactionNote = getShortNpaDescription($rev['modified_by_id'], $pdo, true, 'nominative');
                }
                break;
            case 'change':
                $npaInfo = getNpaInfoByItemId($rev['modified_by_id'], $pdo);
                // Для заголовков: подавляем «Заголовок изменен: …» на дочернем
                // элементе, если его последняя ревизия закрыта тем же НПА, что
                // переписал предка в новой редакции (new_redaction) — заголовок
                // изменен тем же НПА, что и весь предок, дублировать в
                // примечании дочернего элемента избыточно.
                $isLastRev = ((int)$rev['id'] === $currentRevId);
                if ($npaInfo && !in_array($npaInfo['npa_id'], $seenChangeNpaIds, true)) {
                    if ($isLastRev && hasAncestorNewRedactionByNpaId($pdo, $internal_item_id, $npaInfo['npa_id'])) {
                        // Подавляем: примечание избыточно.
                    } else {
                        $seenChangeNpaIds[] = $npaInfo['npa_id'];
                        $changeNotes[] = $shortDesc;
                    }
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

/**
 * Есть ли у элемента или любого из его предков (цепочка npa_item.parent_id,
 * глубина ≤ 20) ревизия new_redaction от НПА с переданным npa_base.npa_id?
 *
 * Используется для подавления избыточных примечаний «С изменениями» на
 * дочерних элементах: если дочерний элемент был закрыт тем же НПА, что
 * переписал его предка в новой редакции (new_redaction), примечание
 * «С изменениями: …» на дочернем избыточно — из примечания «В редакции: …»
 * на предке уже следует, что весь состав предка (включая дочерний) изложен
 * этой редакцией. Легитимный кейс сохраняется: если дочерний элемент
 * закрыт/изменён ДРУГИМ НПА (не тем, что переписал предка), примечание
 * выводится — это отдельная реальная правка, а не следствие новой редакции
 * родителя.
 *
 * Сравнение идёт по npa_base.npa_id (а не по npa_item.id), т.к. один и тот же
 * НПА может фигурировать в ревизиях под разными npa_item.id (разные элементы
 * НПА в разных контекстаX), и нам важна именно «один НПА-база» semantics.
 *
 * @param PDO   $pdo            Соединение с БД.
 * @param int   $itemInternalId npa_item.id элемента для проверки (и его предков).
 * @param int   $npaId          npa_base.npa_id изменяющего НПА.
 * @return bool true — предок (или сам элемент) имеет new_redaction от этого НПА.
 */
function hasAncestorNewRedactionByNpaId($pdo, $itemInternalId, $npaId): bool {
    static $parentByItemId = [];
    static $revisionsByItemId = [];
    static $itemIdToNpaId = [];

    $itemId = (int)$itemInternalId;
    $depth = 0;
    while ($itemId > 0 && $depth < 20) {
        // Ревизии new_redaction предка (если есть).
        if (!array_key_exists($itemId, $revisionsByItemId)) {
            $stmt = $pdo->prepare(
                "SELECT modified_by_id FROM npa_item_revision
                 WHERE item_internal_id = ? AND mod_type = 'new_redaction'"
            );
            $stmt->execute([$itemId]);
            $revisionsByItemId[$itemId] = $stmt->fetchAll(PDO::FETCH_COLUMN);
        }
        foreach ($revisionsByItemId[$itemId] as $modifierItemId) {
            // npa_item.id → npa_base.npa_id (кэш).
            if (!array_key_exists($modifierItemId, $itemIdToNpaId)) {
                $stmt = $pdo->prepare("SELECT npa_id FROM npa_item WHERE id = ?");
                $stmt->execute([$modifierItemId]);
                $row = $stmt->fetch();
                $itemIdToNpaId[$modifierItemId] = $row ? (int)$row['npa_id'] : 0;
            }
            if ($itemIdToNpaId[$modifierItemId] === (int)$npaId) {
                return true;
            }
        }

        // Переход к родителю.
        if (!array_key_exists($itemId, $parentByItemId)) {
            $stmt = $pdo->prepare("SELECT parent_id FROM npa_item WHERE id = ?");
            $stmt->execute([$itemId]);
            $row = $stmt->fetch();
            $parentByItemId[$itemId] = $row ? (int)$row['parent_id'] : 0;
        }
        $itemId = $parentByItemId[$itemId];
        $depth++;
    }
    return false;
}

/**
 * Есть ли у СТРОГИХ предков элемента (цепочка npa_item.parent_id от родителя,
 * глубина ≤ 20) ревизия new_redaction от НПА с переданным npa_base.npa_id?
 * Сам элемент НЕ проверяется — только предки.
 *
 * Нужна для подавления избыточного «В редакции — …» у дочернего элемента:
 * если вся ветка переписана тем же НПА, примечание предка уже покрывает весь
 * его состав. Использовать здесь hasAncestorNewRedactionByNpaId() нельзя —
 * она проверяет и сам элемент, т.е. для new_redaction всегда даст совпадение
 * и скроет ВСЕ примечания «В редакции». Семантика в остальном та же:
 * сравнение по npa_base.npa_id, легитимные правки других НПА показываются.
 *
 * @param PDO $pdo            Соединение с БД.
 * @param int $itemInternalId npa_item.id проверяемого элемента.
 * @param int $npaId          npa_base.npa_id изменяющего НПА.
 * @return bool true — строгий предок имеет new_redaction от этого НПА.
 */
function hasStrictAncestorNewRedactionByNpaId($pdo, $itemInternalId, $npaId): bool {
    static $parentByItemId = [];
    static $revisionsByItemId = [];
    static $itemIdToNpaId = [];

    $stmt = $pdo->prepare("SELECT parent_id FROM npa_item WHERE id = ?");
    $stmt->execute([(int)$itemInternalId]);
    $row = $stmt->fetch();
    $itemId = $row ? (int)$row['parent_id'] : 0;
    $depth = 0;
    while ($itemId > 0 && $depth < 20) {
        if (!array_key_exists($itemId, $revisionsByItemId)) {
            $stmt = $pdo->prepare(
                "SELECT modified_by_id FROM npa_item_revision
                 WHERE item_internal_id = ? AND mod_type = 'new_redaction'"
            );
            $stmt->execute([$itemId]);
            $revisionsByItemId[$itemId] = $stmt->fetchAll(PDO::FETCH_COLUMN);
        }
        foreach ($revisionsByItemId[$itemId] as $modifierItemId) {
            if (!array_key_exists($modifierItemId, $itemIdToNpaId)) {
                $stmt = $pdo->prepare("SELECT npa_id FROM npa_item WHERE id = ?");
                $stmt->execute([$modifierItemId]);
                $row = $stmt->fetch();
                $itemIdToNpaId[$modifierItemId] = $row ? (int)$row['npa_id'] : 0;
            }
            if ($itemIdToNpaId[$modifierItemId] === (int)$npaId) {
                return true;
            }
        }
        if (!array_key_exists($itemId, $parentByItemId)) {
            $stmt = $pdo->prepare("SELECT parent_id FROM npa_item WHERE id = ?");
            $stmt->execute([$itemId]);
            $row = $stmt->fetch();
            $parentByItemId[$itemId] = $row ? (int)$row['parent_id'] : 0;
        }
        $itemId = $parentByItemId[$itemId];
        $depth++;
    }
    return false;
}

/**
 * Подавляется ли примечание «В редакции — …» элемента как избыточное
 * (последняя ревизия new_redaction того же НПА, что переписал строгого предка)?
 *
 * Единая точка истины для примечаний (ui/notes.php) и кнопок (ui/buttons.php):
 * если здесь true — примечание скрыто, значит и блок кнопок
 * («Предыдущая редакция» / «История изменений» / «Сравнение редакций»)
 * у такого дочернего элемента тоже не выводится целиком.
 *
 * @param PDO   $pdo            Соединение с БД.
 * @param int   $itemInternalId npa_item.id проверяемого элемента.
 * @param array $currentRev     Текущая ревизия (rev_id/rev['id'], mod_type, modified_by_id).
 * @param int   $currentRevId   npa_item_revision.rev_id текущей ревизии.
 * @param string $idKey         Ключ id в $currentRev ('rev_id' для тела, 'id' для заголовков).
 * @return bool true — элемент-потомок в наследованной new_redaction, UI скрыть.
 */
function isNewRedactionNoteSuppressedByAncestor($pdo, $itemInternalId, array $currentRev, $currentRevId, $idKey = 'rev_id'): bool {
    if (($currentRev['mod_type'] ?? null) !== 'new_redaction') return false;
    if ((int)($currentRev[$idKey] ?? 0) !== (int)$currentRevId) return false;
    $npaInfo = getNpaInfoByItemId($currentRev['modified_by_id'] ?? '', $pdo);
    if (!$npaInfo) return false;
    return hasStrictAncestorNewRedactionByNpaId($pdo, $itemInternalId, $npaInfo['npa_id']);
}

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
            case 'new_redaction':
                // Дочерний элемент в новой редакции того же НПА, что переписал
                // предка: «В редакции — …» избыточно (примечание предка уже
                // покрывает весь его состав). Подавляем только если это
                // последняя ревизия элемента И строгий предок имеет new_redaction
                // этого же НПА (см. isNewRedactionNoteSuppressedByAncestor —
                // та же проверка гасит и блок кнопок целиком). Другой НПА /
                // не последняя ревизия / нет предка с new_redaction —
                // показываем, как раньше.
                $isLastRevNr = ((int)$rev['rev_id'] === $currentRevId);
                if ($isLastRevNr && isNewRedactionNoteSuppressedByAncestor($pdo, $internal_item_id, $rev, $currentRevId, 'rev_id')) {
                    $newRedactionNote = null;
                } else {
                    $newRedactionNote = getShortNpaDescription($rev['modified_by_id'], $pdo, true, 'nominative');
                }
                break;
            case 'change':
                $npaInfo = getNpaInfoByItemId($rev['modified_by_id'], $pdo);
                // Последняя ревизия элемента, закрытая тем же НПА, что переписал
                // его предка в новой редакции (new_redaction) — примечание
                // «С изменениями: …» на таком элементе избыточно: из примечания
                // «В редакции — NPA» на предке уже следует, что весь состав
                // предка (включая этот дочерний) изложен этой редакцией.
                // Реальные правки ДРУГИХ НПА (не того, что переписал предка)
                // примечание получают — это отдельная правка, а не следствие
                // новой редакции родителя (кейс 269-ЗС <- 380-ЗС: дочерние
                // элементы статьи 2, закрытые 380-ЗС, не должны дублировать
                // «В редакции — 380-ЗС» на уровне статьи 2).
                $isLastRev = ((int)$rev['rev_id'] === $currentRevId);
                if ($npaInfo && !in_array($npaInfo['npa_id'], $seenChangeNpaIds, true)) {
                    if ($isLastRev && hasAncestorNewRedactionByNpaId($pdo, $internal_item_id, $npaInfo['npa_id'])) {
                        // Подавляем: примечание избыточно.
                    } else {
                        $seenChangeNpaIds[] = $npaInfo['npa_id'];
                        $changeNotes[] = $shortDesc;
                    }
                }
                break;
        }
        foreach (array_filter(array_map('trim', explode(',', (string)($rev['modified_by_id'] ?? '')))) as $mid) {
            if ($mid !== '' && $mid !== 'base') $ownChangerIds[$mid] = true;
        }
    }

    // НПА, создавшие собственные ревизии элемента (в т.ч. new_redaction/add).
    // Их повторный подъём из дочерних элементов в «С изменениями» запрещён:
    // когда элемент изложен новой редакцией или введён этим же НПА, закрытие
    // его старых дочерних элементов — часть ТОГО ЖЕ изменения, а не отдельная
    // правка. Иначе рядом с «В редакции — Закон № 380-ЗС …» появляется
    // вводящее в заблуждение «С изменениями: Закон № 380-ЗС …», как будто
    // была ещё и правка типа change, которой не было
    // (кейс 269-ЗС <- 380-ЗС: статья 2 изложена новой редакцией 380-ЗС,
    // её бывшие части закрыты той же 380-ЗС).
    $ownProvenanceNpaIds = [];
    foreach (array_keys($ownChangerIds) as $ownMid) {
        $ownNpaInfo = getNpaInfoByItemId($ownMid, $pdo);
        if ($ownNpaInfo && !in_array($ownNpaInfo['npa_id'], $ownProvenanceNpaIds, true)) {
            $ownProvenanceNpaIds[] = $ownNpaInfo['npa_id'];
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
            // Подъём не выполняется для НПА, создавшей собственную ревизию
            // элемента (new_redaction/add/change): закрытие её же старых
            // дочерних элементов — часть того же изменения, а не отдельная
            // правка. НПА уже отображается в «В редакции — …»/«Введён — …».
            if ($npaInfo && in_array($npaInfo['npa_id'], $ownProvenanceNpaIds, true)) {
                continue;
            }
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

