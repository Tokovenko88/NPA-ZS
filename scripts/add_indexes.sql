-- Индексы для ускорения импорта и запросов
-- Применять после создания таблиц NPA-ZS

-- Таблица предрендеренного HTML-кеша (заполняется импортёром:
-- npazs.db.html_renderer.NpaHtmlRenderer). Сайт читает её
-- через getRenderedCacheHtml() в cache/static.php.
CREATE TABLE IF NOT EXISTS npa_rendered_cache (
    npa_id INT UNSIGNED NOT NULL,
    as_of_date DATE NOT NULL,
    html_full LONGTEXT,
    generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (npa_id, as_of_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Для bulk_insert и fetch_revision_ids
CREATE INDEX IF NOT EXISTS idx_npa_item_revision_npa_id 
ON npa_item_revision(npa_id, item_internal_id, valid_from);

-- Для getItemTree
CREATE INDEX IF NOT EXISTS idx_npa_item_npa_id 
ON npa_item(npa_id, item_id, sort_order);

-- Для загрузки параграфов по rev_id
CREATE INDEX IF NOT EXISTS idx_npa_paragraph_rev 
ON npa_paragraph(rev_id, sort_order);

-- Для head_revision запросов
CREATE INDEX IF NOT EXISTS idx_npa_item_head_revision_lookup 
ON npa_item_head_revision(item_internal_id, valid_from, valid_to);

-- Для prefix_revision запросов
CREATE INDEX IF NOT EXISTS idx_npa_item_prefix_revision_lookup 
ON npa_item_prefix_revision(item_internal_id, valid_from, valid_to);

-- Для number_revision запросов
CREATE INDEX IF NOT EXISTS idx_npa_item_number_revision_lookup 
ON npa_item_number_revision(item_internal_id, valid_from, valid_to);
