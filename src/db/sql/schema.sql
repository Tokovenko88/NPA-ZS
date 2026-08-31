-- =============================================================================
-- NPA-ZS: схема базы данных нормативных правовых актов
-- =============================================================================
-- Полное описание: docs/db_schema.md
-- Машиночитаемое описание (списки таблиц, ENUM, порядок вставки): src/db/schema.py
--
-- Требования: MySQL 5.7+ / MariaDB 10.3+ (нужен тип JSON), InnoDB, utf8mb4.
--
-- Ключевые инварианты:
--   1. npa_item.item_id -- строковый НЕИЗМЕНЯЕМЫЙ идентификатор элемента вида
--      <npa_id>_<type>_<number>[_double_N]. Он не меняется никогда, поэтому
--      ссылки child_ref / modified_by_id / not_valid остаются корректными даже
--      при перенумерации элемента.
--   2. Номер элемента версионируется отдельно (npa_item_number_revision);
--      npa_item.item_number всегда равен последней действующей записи истории.
--   3. У элемента только ОДНА активная редакция (valid_to IS NULL) в каждой
--      таблице ревизий.
--   4. Удаление НПА каскадное, КРОМЕ npa_note_unified.source_item_id
--      (ON DELETE SET NULL): примечание переживает удаление своего источника.
-- =============================================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- =============================================================================
-- 1. СПРАВОЧНИКИ
-- =============================================================================

CREATE TABLE IF NOT EXISTS person (
    id  INT UNSIGNED NOT NULL AUTO_INCREMENT,
    fio VARCHAR(255) NOT NULL COMMENT 'Полное имя, нормализованное (И.О. Фамилия)',
    PRIMARY KEY (id),
    UNIQUE KEY uq_person_fio (fio)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Физические лица: авторы, подписанты, депутаты';

CREATE TABLE IF NOT EXISTS convocation (
    id        TINYINT UNSIGNED NOT NULL AUTO_INCREMENT,
    name      VARCHAR(50) NOT NULL COMMENT 'Например, "I созыв"',
    date_from DATE DEFAULT NULL,
    date_to   DATE DEFAULT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_convocation_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Созывы Законодательного Собрания';

CREATE TABLE IF NOT EXISTS person_post (
    id             INT UNSIGNED NOT NULL AUTO_INCREMENT,
    name           VARCHAR(255) NOT NULL,
    display_mode   TINYINT UNSIGNED NOT NULL DEFAULT 0
                   COMMENT '0 - полная, 1 - сокращённая, 2 - служебная',
    convocation_id TINYINT UNSIGNED DEFAULT NULL,
    cms_deputy_id  INT UNSIGNED DEFAULT NULL COMMENT 'ID депутата в CMS',
    is_active      TINYINT(1) NOT NULL DEFAULT 1,
    PRIMARY KEY (id),
    KEY idx_person_post_convocation (convocation_id),
    CONSTRAINT fk_person_post_convocation
        FOREIGN KEY (convocation_id) REFERENCES convocation (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Должности (депутат, губернатор, прокурор и т.д.)';

CREATE TABLE IF NOT EXISTS committees (
    id   INT UNSIGNED NOT NULL AUTO_INCREMENT,
    name VARCHAR(255) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_committees_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Комитеты Законодательного Собрания';

-- =============================================================================
-- 2. ЯДРО: ПАСПОРТ НПА
-- =============================================================================

CREATE TABLE IF NOT EXISTS npa_base (
    npa_id           INT UNSIGNED NOT NULL COMMENT 'Уникальный числовой идентификатор НПА',
    npa_type         ENUM('law','regulation') NOT NULL,
    npa_number       VARCHAR(30) NOT NULL COMMENT 'Официальный регистрационный номер',
    pub_info         VARCHAR(500) DEFAULT NULL COMMENT 'Источник опубликования (законы с номером < 176)',
    pub_filepath     VARCHAR(500) DEFAULT NULL COMMENT 'Путь к образу документа на sevzakon.ru',
    npa_url          VARCHAR(1000) DEFAULT NULL,
    date_reg         DATE DEFAULT NULL COMMENT 'Дата регистрации проекта',
    date_cons        DATE DEFAULT NULL COMMENT 'Дата подготовки',
    date_passed      DATE DEFAULT NULL COMMENT 'Дата принятия',
    date_pub         DATE DEFAULT NULL COMMENT 'Дата официальной публикации',
    valid_from       DATE DEFAULT NULL COMMENT 'Вступление в силу: точка отсчёта версий',
    not_valid        DATE DEFAULT NULL COMMENT 'Дата утраты силы',
    date_format      TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Код формата отображения дат',
    not_valid_note   VARCHAR(150) DEFAULT NULL
                     COMMENT 'Строковый item_id элемента-причины утраты силы',
    not_valid_npa_id INT UNSIGNED DEFAULT NULL
                     COMMENT 'ID НПА, вызвавшего утрату силы',
    no_name          VARCHAR(255) DEFAULT NULL
                     COMMENT 'item_id через запятую: разделы без служебного слова "Раздел"',
    PRIMARY KEY (npa_id),
    KEY idx_npa_base_type_number (npa_type, npa_number),
    KEY idx_npa_base_valid_from (valid_from),
    KEY idx_npa_base_not_valid_npa (not_valid_npa_id),
    CONSTRAINT fk_npa_not_valid_npa
        FOREIGN KEY (not_valid_npa_id) REFERENCES npa_base (npa_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Паспорт НПА: общие метаданные законов и постановлений';

CREATE TABLE IF NOT EXISTS npa_law (
    npa_id           INT UNSIGNED NOT NULL,
    date_1st_reading DATE DEFAULT NULL,
    date_2nd_reading DATE DEFAULT NULL,
    date_signed      DATE DEFAULT NULL,
    PRIMARY KEY (npa_id),
    CONSTRAINT fk_npa_law_base
        FOREIGN KEY (npa_id) REFERENCES npa_base (npa_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Дополнительные атрибуты законов';

CREATE TABLE IF NOT EXISTS npa_regulation (
    npa_id         INT UNSIGNED NOT NULL,
    term_number    VARCHAR(10) DEFAULT NULL COMMENT 'Номер созыва римскими цифрами',
    session_number VARCHAR(10) DEFAULT NULL COMMENT 'Номер сессии римскими цифрами',
    PRIMARY KEY (npa_id),
    CONSTRAINT fk_npa_regulation_base
        FOREIGN KEY (npa_id) REFERENCES npa_base (npa_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Дополнительные атрибуты постановлений';

CREATE TABLE IF NOT EXISTS npa_head_revision (
    id              INT UNSIGNED NOT NULL AUTO_INCREMENT,
    npa_id          INT UNSIGNED NOT NULL,
    npa_title       TEXT NOT NULL,
    valid_from      DATE DEFAULT NULL,
    valid_to        DATE DEFAULT NULL COMMENT 'NULL = активная редакция',
    highlights      JSON DEFAULT NULL COMMENT 'Подсветка изменений относительно предыдущей редакции',
    modified_by_id  VARCHAR(255) DEFAULT NULL COMMENT 'Список id инициирующих элементов через запятую',
    not_valid       VARCHAR(255) DEFAULT NULL COMMENT 'item_id документа, отменившего редакцию',
    PRIMARY KEY (id),
    KEY idx_npa_head_rev_npa (npa_id),
    KEY idx_npa_head_rev_validity (npa_id, valid_from, valid_to),
    CONSTRAINT fk_npa_head_rev_base
        FOREIGN KEY (npa_id) REFERENCES npa_base (npa_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='История редакций заголовка НПА';

-- =============================================================================
-- 3. СВЯЗИ ПАСПОРТА
-- =============================================================================

CREATE TABLE IF NOT EXISTS npa_author_link (
    id             INT UNSIGNED NOT NULL AUTO_INCREMENT,
    npa_id         INT UNSIGNED NOT NULL,
    person_id      INT UNSIGNED DEFAULT NULL,
    person_post_id INT UNSIGNED DEFAULT NULL,
    sort_order     SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    KEY idx_npa_author_npa (npa_id),
    KEY idx_npa_author_person (person_id),
    KEY idx_npa_author_post (person_post_id),
    CONSTRAINT fk_npa_author_base
        FOREIGN KEY (npa_id) REFERENCES npa_base (npa_id) ON DELETE CASCADE,
    CONSTRAINT fk_npa_author_person
        FOREIGN KEY (person_id) REFERENCES person (id) ON DELETE SET NULL,
    CONSTRAINT fk_npa_author_post
        FOREIGN KEY (person_post_id) REFERENCES person_post (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Авторы НПА';

CREATE TABLE IF NOT EXISTS npa_signatory (
    id             INT UNSIGNED NOT NULL AUTO_INCREMENT,
    npa_id         INT UNSIGNED NOT NULL,
    person_id      INT UNSIGNED DEFAULT NULL,
    person_post_id INT UNSIGNED DEFAULT NULL,
    sort_order     SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    KEY idx_npa_signatory_npa (npa_id),
    KEY idx_npa_signatory_person (person_id),
    KEY idx_npa_signatory_post (person_post_id),
    CONSTRAINT fk_npa_signatory_base
        FOREIGN KEY (npa_id) REFERENCES npa_base (npa_id) ON DELETE CASCADE,
    CONSTRAINT fk_npa_signatory_person
        FOREIGN KEY (person_id) REFERENCES person (id) ON DELETE SET NULL,
    CONSTRAINT fk_npa_signatory_post
        FOREIGN KEY (person_post_id) REFERENCES person_post (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Подписанты НПА';

CREATE TABLE IF NOT EXISTS npa_committee_link (
    id           INT UNSIGNED NOT NULL AUTO_INCREMENT,
    npa_id       INT UNSIGNED NOT NULL,
    committee_id INT UNSIGNED NOT NULL,
    sort_order   SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    KEY idx_npa_committee_npa (npa_id),
    KEY idx_npa_committee_ref (committee_id),
    CONSTRAINT fk_npa_committee_base
        FOREIGN KEY (npa_id) REFERENCES npa_base (npa_id) ON DELETE CASCADE,
    CONSTRAINT fk_npa_committee_ref
        FOREIGN KEY (committee_id) REFERENCES committees (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Ответственные комитеты';

CREATE TABLE IF NOT EXISTS npa_revision_info (
    id                  INT UNSIGNED NOT NULL AUTO_INCREMENT,
    base_npa_id         INT UNSIGNED NOT NULL COMMENT 'ID основного (изменяемого) НПА',
    revision_id         INT UNSIGNED DEFAULT NULL COMMENT 'npa_id изменяющего документа',
    revision_number     VARCHAR(30) DEFAULT NULL,
    revision_date_reg   DATE DEFAULT NULL,
    revision_date_valid DATE DEFAULT NULL COMMENT 'Дата вступления изменений в силу',
    revision_url        VARCHAR(1000) DEFAULT NULL,
    PRIMARY KEY (id),
    KEY idx_npa_rev_info_base (base_npa_id),
    KEY idx_npa_rev_info_rev (revision_id),
    CONSTRAINT fk_npa_rev_info_base
        FOREIGN KEY (base_npa_id) REFERENCES npa_base (npa_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Документы, вносившие изменения в данный НПА';
-- =============================================================================
-- 4. ИЕРАРХИЯ И КОНТЕНТ СТРУКТУРНЫХ ЭЛЕМЕНТОВ
-- =============================================================================

CREATE TABLE IF NOT EXISTS npa_item (
    id          INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Внутренний числовой PK',
    item_id     VARCHAR(150) NOT NULL
                COMMENT 'Строковый НЕИЗМЕНЯЕМЫЙ id: <npa_id>_<type>_<number>[_double_N]',
    npa_id      INT UNSIGNED NOT NULL,
    parent_id   INT UNSIGNED DEFAULT NULL COMMENT 'Ссылка на npa_item.id родителя',
    item_type   ENUM('preamble','chapter','section','article','part','point',
                     'subpoint','appendix','nested_appendix','structured_table') NOT NULL,
    item_number VARCHAR(30) DEFAULT NULL
                COMMENT 'Текущий номер; синхронизирован с последней записью npa_item_number_revision',
    item_level  TINYINT UNSIGNED NOT NULL DEFAULT 1 COMMENT 'Уровень вложенности, 1 - верхний',
    sort_order  SMALLINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Порядок среди детей одного родителя',
    PRIMARY KEY (id),
    UNIQUE KEY uq_npa_item_item_id (item_id),
    KEY idx_npa_item_npa (npa_id),
    KEY idx_npa_item_parent (parent_id),
    KEY idx_npa_item_lookup (npa_id, item_type, item_number),
    KEY idx_npa_item_order (parent_id, sort_order),
    CONSTRAINT fk_npa_item_base
        FOREIGN KEY (npa_id) REFERENCES npa_base (npa_id) ON DELETE CASCADE,
    CONSTRAINT fk_npa_item_parent
        FOREIGN KEY (parent_id) REFERENCES npa_item (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Узлы дерева документа: главы, разделы, статьи, пункты, приложения, таблицы';

CREATE TABLE IF NOT EXISTS npa_item_revision (
    rev_id           INT UNSIGNED NOT NULL AUTO_INCREMENT,
    item_internal_id INT UNSIGNED NOT NULL COMMENT 'Ссылка на npa_item.id',
    npa_id           INT UNSIGNED NOT NULL,
    valid_from       DATE DEFAULT NULL,
    valid_to         DATE DEFAULT NULL COMMENT 'NULL = активная редакция',
    mod_type         ENUM('add','change','delete','new_redaction') DEFAULT NULL,
    modified_by_id   VARCHAR(255) DEFAULT NULL COMMENT 'id инициирующих элементов через запятую',
    highlights       JSON DEFAULT NULL COMMENT 'Подсветка различий с предыдущей редакцией',
    not_valid        VARCHAR(255) DEFAULT NULL COMMENT 'item_id документа, отменившего редакцию',
    PRIMARY KEY (rev_id),
    KEY idx_item_rev_item (item_internal_id),
    KEY idx_item_rev_npa (npa_id),
    KEY idx_item_rev_validity (item_internal_id, valid_from, valid_to),
    CONSTRAINT fk_item_rev_item
        FOREIGN KEY (item_internal_id) REFERENCES npa_item (id) ON DELETE CASCADE,
    CONSTRAINT fk_item_rev_base
        FOREIGN KEY (npa_id) REFERENCES npa_base (npa_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Редакции содержания элементов';

CREATE TABLE IF NOT EXISTS npa_item_head_revision (
    id               INT UNSIGNED NOT NULL AUTO_INCREMENT,
    item_internal_id INT UNSIGNED NOT NULL,
    npa_id           INT UNSIGNED NOT NULL,
    head_text        TEXT DEFAULT NULL COMMENT 'Заголовок элемента (без номера)',
    valid_from       DATE DEFAULT NULL,
    valid_to         DATE DEFAULT NULL,
    mod_type         ENUM('add','change','delete','new_redaction') DEFAULT NULL,
    modified_by_id   VARCHAR(255) DEFAULT NULL,
    highlights       JSON DEFAULT NULL,
    not_valid        VARCHAR(255) DEFAULT NULL,
    PRIMARY KEY (id),
    KEY idx_item_head_rev_item (item_internal_id),
    KEY idx_item_head_rev_npa (npa_id),
    KEY idx_item_head_rev_validity (item_internal_id, valid_from, valid_to),
    CONSTRAINT fk_item_head_rev_item
        FOREIGN KEY (item_internal_id) REFERENCES npa_item (id) ON DELETE CASCADE,
    CONSTRAINT fk_item_head_rev_base
        FOREIGN KEY (npa_id) REFERENCES npa_base (npa_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Редакции заголовков элементов';

CREATE TABLE IF NOT EXISTS npa_item_prefix_revision (
    id               INT UNSIGNED NOT NULL AUTO_INCREMENT,
    item_internal_id INT UNSIGNED NOT NULL,
    npa_id           INT UNSIGNED NOT NULL,
    prefix_text      TEXT DEFAULT NULL COMMENT 'Служебная информация приложения, напр. "тыс. руб."',
    valid_from       DATE DEFAULT NULL,
    valid_to         DATE DEFAULT NULL,
    mod_type         ENUM('add','change','delete','new_redaction') DEFAULT NULL,
    modified_by_id   VARCHAR(255) DEFAULT NULL,
    highlights       JSON DEFAULT NULL,
    not_valid        VARCHAR(255) DEFAULT NULL,
    PRIMARY KEY (id),
    KEY idx_item_prefix_rev_item (item_internal_id),
    KEY idx_item_prefix_rev_npa (npa_id),
    KEY idx_item_prefix_rev_validity (item_internal_id, valid_from, valid_to),
    CONSTRAINT fk_item_prefix_rev_item
        FOREIGN KEY (item_internal_id) REFERENCES npa_item (id) ON DELETE CASCADE,
    CONSTRAINT fk_item_prefix_rev_base
        FOREIGN KEY (npa_id) REFERENCES npa_base (npa_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Редакции служебной информации (префиксов) приложений';

CREATE TABLE IF NOT EXISTS npa_item_number_revision (
    id               INT UNSIGNED NOT NULL AUTO_INCREMENT,
    item_internal_id INT UNSIGNED NOT NULL,
    npa_id           INT UNSIGNED NOT NULL,
    number_text      VARCHAR(30) DEFAULT NULL COMMENT 'Номер элемента в данной версии',
    valid_from       DATE DEFAULT NULL,
    valid_to         DATE DEFAULT NULL,
    mod_type         ENUM('correction','renumber','editorial') DEFAULT NULL,
    modified_by_id   VARCHAR(255) DEFAULT NULL,
    not_valid        VARCHAR(255) DEFAULT NULL,
    PRIMARY KEY (id),
    KEY idx_item_num_rev_item (item_internal_id),
    KEY idx_item_num_rev_npa (npa_id),
    KEY idx_item_num_rev_validity (item_internal_id, valid_from, valid_to),
    CONSTRAINT fk_item_num_rev_item
        FOREIGN KEY (item_internal_id) REFERENCES npa_item (id) ON DELETE CASCADE,
    CONSTRAINT fk_item_num_rev_base
        FOREIGN KEY (npa_id) REFERENCES npa_base (npa_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='История изменений номеров элементов (item_id при этом неизменен)';

CREATE TABLE IF NOT EXISTS npa_paragraph (
    para_id              INT UNSIGNED NOT NULL AUTO_INCREMENT,
    rev_id               INT UNSIGNED NOT NULL COMMENT 'Ссылка на npa_item_revision.rev_id',
    item_internal_id     INT UNSIGNED NOT NULL COMMENT 'Дубль ссылки на элемент для быстрых выборок',
    block_type           ENUM('paragraph','table','child_ref','table_header','table_fragment')
                         NOT NULL DEFAULT 'paragraph',
    sort_order           SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    html_text            MEDIUMTEXT DEFAULT NULL,
    plain_text           MEDIUMTEXT DEFAULT NULL COMMENT 'Текст без разметки, для поиска',
    ref_item_internal_id INT UNSIGNED DEFAULT NULL
                         COMMENT 'Для block_type=child_ref: ссылка на дочерний элемент',
    PRIMARY KEY (para_id),
    KEY idx_paragraph_rev (rev_id, sort_order),
    KEY idx_paragraph_item (item_internal_id),
    KEY idx_paragraph_ref (ref_item_internal_id),
    CONSTRAINT fk_paragraph_rev
        FOREIGN KEY (rev_id) REFERENCES npa_item_revision (rev_id) ON DELETE CASCADE,
    CONSTRAINT fk_paragraph_item
        FOREIGN KEY (item_internal_id) REFERENCES npa_item (id) ON DELETE CASCADE,
    CONSTRAINT fk_paragraph_ref_item
        FOREIGN KEY (ref_item_internal_id) REFERENCES npa_item (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Блоки контента редакции: абзацы, таблицы, ссылки на детей';
-- =============================================================================
-- 5. ПРИМЕЧАНИЯ (единая таблица)
-- =============================================================================
--
-- Семантика source_item_id (подробно: docs/db_schema.md, раздел 6.1):
--
--   source_item_id IS NOT NULL
--     1. Указывает на npa_item.id элемента НПА, который вызвал появление
--        примечания.
--     2. Примечание относится к редакции, вызванной этим НПА, и ко всем
--        последующим (более новым) редакциям.
--     3. valid_from НЕ используется для определения принадлежности примечания
--        к редакции. Это позволяет корректно обрабатывать ретроактивное
--        действие, когда дата действия раньше даты принятия изменяющего НПА.
--     4. valid_to, если задана, -- безусловная верхняя граница отображения.
--     5. Если выбранная редакция старше редакции источника, примечание не
--        отображается.
--
--   source_item_id IS NULL
--     Применяется только датовая логика:
--       valid_from <= дата просмотра AND (valid_to IS NULL OR valid_to >= дата просмотра)
--
-- ON DELETE SET NULL: удаление НПА-источника НЕ удаляет примечание, а лишь
-- переводит его на датовую модель отображения.

CREATE TABLE IF NOT EXISTS npa_note_unified (
    id             INT UNSIGNED NOT NULL AUTO_INCREMENT,
    npa_id         INT UNSIGNED NOT NULL COMMENT 'НПА, к которому относится примечание',
    source_item_id INT UNSIGNED DEFAULT NULL
                   COMMENT 'npa_item.id элемента НПА-источника; NULL = источник не в БД',
    target_type    ENUM('npa','toc','item') NOT NULL DEFAULT 'item',
    target_id      VARCHAR(150) DEFAULT NULL
                   COMMENT 'Для target_type=item: строковый item_id; для npa -- NULL',
    note_text      TEXT NOT NULL,
    valid_from     DATE DEFAULT NULL,
    valid_to       DATE DEFAULT NULL,
    PRIMARY KEY (id),
    KEY idx_note_npa (npa_id),
    KEY idx_note_target (target_type, target_id),
    KEY idx_note_source (source_item_id),
    KEY idx_note_validity (valid_from, valid_to),
    CONSTRAINT fk_note_base
        FOREIGN KEY (npa_id) REFERENCES npa_base (npa_id) ON DELETE CASCADE,
    CONSTRAINT fk_note_source_item
        FOREIGN KEY (source_item_id) REFERENCES npa_item (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Примечания к НПА и его элементам (npa_notes + item_notes из JSON)';

-- =============================================================================
-- 6. КЭШ РЕНДЕРИНГА
-- =============================================================================

CREATE TABLE IF NOT EXISTS npa_rendered_cache (
    npa_id       INT UNSIGNED NOT NULL,
    as_of_date   DATE NOT NULL COMMENT 'Дата, на которую сгенерирован HTML',
    html_full    LONGTEXT DEFAULT NULL,
    generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (npa_id, as_of_date),
    CONSTRAINT fk_rendered_cache_base
        FOREIGN KEY (npa_id) REFERENCES npa_base (npa_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Кэш HTML-представления НПА на дату (используется снипетом сайта)';

-- =============================================================================
-- 7. ПРЕДСТАВЛЕНИЯ
-- =============================================================================

CREATE OR REPLACE VIEW v_npa_full_authors AS
SELECT
    l.npa_id,
    l.sort_order,
    p.id   AS person_id,
    p.fio  AS person_fio,
    pp.id  AS post_id,
    pp.name AS post_name,
    pp.display_mode,
    pp.is_active AS post_is_active,
    c.id   AS convocation_id,
    c.name AS convocation_name
FROM npa_author_link l
LEFT JOIN person      p  ON p.id  = l.person_id
LEFT JOIN person_post pp ON pp.id = l.person_post_id
LEFT JOIN convocation c  ON c.id  = pp.convocation_id;

CREATE OR REPLACE VIEW v_npa_active_items AS
SELECT
    i.npa_id,
    i.id       AS item_internal_id,
    i.item_id,
    i.item_type,
    i.item_number,
    i.item_level,
    i.sort_order,
    r.rev_id,
    r.valid_from,
    r.mod_type,
    r.modified_by_id
FROM npa_item i
JOIN npa_item_revision r
     ON r.item_internal_id = i.id
    AND r.valid_to IS NULL;

SET FOREIGN_KEY_CHECKS = 1;

-- =============================================================================
-- Конец схемы
-- =============================================================================