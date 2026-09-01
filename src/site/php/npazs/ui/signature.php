<?php
/**
 * NPA-ZS | ui/signature.php — подписной блок документа.
 *
 * Функции: renderSignature.
 * Источник: строки 2706-2738 монолита snippet.php.
 */

function renderSignature(PDO $pdo, $npa_id, $dateSigned, $npaNumber, $dateFormat, $includeRequisites = true) {
    $stmt = $pdo->prepare("SELECT s.*, p.fio, pp.name as position_name
                           FROM npa_signatory s
                           JOIN person p ON s.person_id = p.id
                           JOIN person_post pp ON s.person_post_id = pp.id
                           WHERE s.npa_id = ? LIMIT 1");
    $stmt->execute([$npa_id]);
    $signer = $stmt->fetch();
    if (!$signer) return '';
    $signerPost = $signer['position_name'];
    $signerName = $signer['fio'];
    $phrases = ['Законодательного Собрания', 'города Севастополя'];
    foreach ($phrases as $phrase) {
        if (mb_stripos($signerPost, $phrase) !== false) {
            if (!preg_match('/<br\s*\/?>\s*' . preg_quote($phrase, '/') . '/ui', $signerPost)) {
                $signerPost = preg_replace('/(\s*)(' . preg_quote($phrase, '/') . ')/ui', '<br>$1$2', $signerPost, 1);
            }
        }
    }
    $signerPost = htmlspecialchars($signerPost);
    $signerPost = str_replace(['&lt;br&gt;', '&lt;br /&gt;', '&lt;br/&gt;'], '<br>', $signerPost);
    $signerName = htmlspecialchars($signerName);
    $html = '<p class="justifyleft npa-signer">' . $signerPost;
    if ($signerName) $html .= str_repeat('&nbsp;', 5) . $signerName;
    $html .= '</p>';
    if ($includeRequisites) {
        $place = 'Севастополь';
        $formattedDate = formatRusDate($dateSigned, $dateFormat);
        $html .= '<p class="justifyleft npa-requisites">' . $place . '<br>' . $formattedDate . '<br>№&nbsp;' . htmlspecialchars($npaNumber) . '</p>';
    }
    return $html;
}

