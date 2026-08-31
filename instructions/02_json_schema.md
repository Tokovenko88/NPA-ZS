# JSON Schema

## Root Object

- `npa_id`: int
- `npa_type`: `law` | `regulation`
- `npa_number`: string
- `npa_author`: string
- `date_passed`: string (DD.MM.YYYY)
- `date_pub`: string
- `valid_from`: string
- `npa_items_revision`: array of items

## Item Object

- `item_id`: string (stable ID)
- `item_type`: `preamble` | `chapter` | `section` | `article` | `part` | `point` | `subpoint` | `appendix` | `structured_table`
- `item_number`: string | null
- `item_level`: int
- `revisions`: array of revision objects
- `head_revisions`: array of head revision objects
- `item_children`: array of child items

## Revision Object

- `valid_from`: string | null
- `valid_to`: string | null
- `mod_type`: string | null
- `modified_by_id`: string | null
- `body`: array of block objects
- `highlights`: object | null

## Block Object

- `type`: `paragraph` | `table` | `child_ref` | `table_header` | `table_fragment`
- `html_text`: string
- `item_id`: string (for child_ref)
- `order`: int
