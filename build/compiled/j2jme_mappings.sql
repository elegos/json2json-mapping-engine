CREATE OR REPLACE PACKAGE MAPPING_OWNER.J2JME_MAPPINGS AS
    PROCEDURE map_aggregate_by (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_aggregate_by_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );

    PROCEDURE map_builtins_dates (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_builtins_dates_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );

    PROCEDURE map_builtins_more (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_builtins_more_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );

    PROCEDURE map_builtins_text (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_builtins_text_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );

    PROCEDURE map_document_loop (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_document_loop_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );

    PROCEDURE map_empty_text (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_empty_text_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );

    PROCEDURE map_groups (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_groups_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );

    PROCEDURE map_keyword_fields (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_keyword_fields_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );

    PROCEDURE map_null_forms (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_null_forms_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );

    PROCEDURE map_orders (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_orders_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );

    FUNCTION map_orders_fn (p_src IN CLOB) RETURN CLOB PARALLEL_ENABLE;

    PROCEDURE map_pick (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_pick_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );

    PROCEDURE map_positions (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_positions_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );

    PROCEDURE map_selection (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_selection_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );

    PROCEDURE map_truthiness (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_truthiness_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    );

    PROCEDURE map_validation (
        p_src IN  CLOB,
        p_out OUT CLOB
    );

    PROCEDURE map_validation_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB,
        p_report OUT CLOB
    );
END J2JME_MAPPINGS;
/

CREATE OR REPLACE PACKAGE BODY MAPPING_OWNER.J2JME_MAPPINGS AS
    PROCEDURE map_aggregate_by (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_AGGREGATE_BY.map_aggregate_by(p_src, p_out);
    END map_aggregate_by;

    PROCEDURE map_aggregate_by_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_AGGREGATE_BY.map_aggregate_by_safe(p_src, p_out, p_err);
    END map_aggregate_by_safe;

    PROCEDURE map_builtins_dates (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_BUILTINS_DATES.map_builtins_dates(p_src, p_out);
    END map_builtins_dates;

    PROCEDURE map_builtins_dates_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_BUILTINS_DATES.map_builtins_dates_safe(p_src, p_out, p_err);
    END map_builtins_dates_safe;

    PROCEDURE map_builtins_more (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_BUILTINS_MORE.map_builtins_more(p_src, p_out);
    END map_builtins_more;

    PROCEDURE map_builtins_more_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_BUILTINS_MORE.map_builtins_more_safe(p_src, p_out, p_err);
    END map_builtins_more_safe;

    PROCEDURE map_builtins_text (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_BUILTINS_TEXT.map_builtins_text(p_src, p_out);
    END map_builtins_text;

    PROCEDURE map_builtins_text_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_BUILTINS_TEXT.map_builtins_text_safe(p_src, p_out, p_err);
    END map_builtins_text_safe;

    PROCEDURE map_document_loop (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_DOCUMENT_LOOP.map_document_loop(p_src, p_out);
    END map_document_loop;

    PROCEDURE map_document_loop_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_DOCUMENT_LOOP.map_document_loop_safe(p_src, p_out, p_err);
    END map_document_loop_safe;

    PROCEDURE map_empty_text (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_EMPTY_TEXT.map_empty_text(p_src, p_out);
    END map_empty_text;

    PROCEDURE map_empty_text_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_EMPTY_TEXT.map_empty_text_safe(p_src, p_out, p_err);
    END map_empty_text_safe;

    PROCEDURE map_groups (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_GROUPS.map_groups(p_src, p_out);
    END map_groups;

    PROCEDURE map_groups_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_GROUPS.map_groups_safe(p_src, p_out, p_err);
    END map_groups_safe;

    PROCEDURE map_keyword_fields (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_KEYWORD_FIELDS.map_keyword_fields(p_src, p_out);
    END map_keyword_fields;

    PROCEDURE map_keyword_fields_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_KEYWORD_FIELDS.map_keyword_fields_safe(p_src, p_out, p_err);
    END map_keyword_fields_safe;

    PROCEDURE map_null_forms (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_NULL_FORMS.map_null_forms(p_src, p_out);
    END map_null_forms;

    PROCEDURE map_null_forms_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_NULL_FORMS.map_null_forms_safe(p_src, p_out, p_err);
    END map_null_forms_safe;

    PROCEDURE map_orders (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_ORDERS.map_orders(p_src, p_out);
    END map_orders;

    PROCEDURE map_orders_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_ORDERS.map_orders_safe(p_src, p_out, p_err);
    END map_orders_safe;

    FUNCTION map_orders_fn (p_src IN CLOB) RETURN CLOB PARALLEL_ENABLE AS
    BEGIN
        RETURN MAPPING_OWNER.J2JME_MAP_ORDERS.map_orders_fn(p_src);
    END map_orders_fn;

    PROCEDURE map_pick (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_PICK.map_pick(p_src, p_out);
    END map_pick;

    PROCEDURE map_pick_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_PICK.map_pick_safe(p_src, p_out, p_err);
    END map_pick_safe;

    PROCEDURE map_positions (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_POSITIONS.map_positions(p_src, p_out);
    END map_positions;

    PROCEDURE map_positions_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_POSITIONS.map_positions_safe(p_src, p_out, p_err);
    END map_positions_safe;

    PROCEDURE map_selection (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_SELECTION.map_selection(p_src, p_out);
    END map_selection;

    PROCEDURE map_selection_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_SELECTION.map_selection_safe(p_src, p_out, p_err);
    END map_selection_safe;

    PROCEDURE map_truthiness (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_TRUTHINESS.map_truthiness(p_src, p_out);
    END map_truthiness;

    PROCEDURE map_truthiness_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_TRUTHINESS.map_truthiness_safe(p_src, p_out, p_err);
    END map_truthiness_safe;

    PROCEDURE map_validation (
        p_src IN  CLOB,
        p_out OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_VALIDATION.map_validation(p_src, p_out);
    END map_validation;

    PROCEDURE map_validation_safe (
        p_src IN  CLOB,
        p_out OUT CLOB,
        p_err OUT CLOB,
        p_report OUT CLOB
    ) AS
    BEGIN
        MAPPING_OWNER.J2JME_MAP_VALIDATION.map_validation_safe(p_src, p_out, p_err, p_report);
    END map_validation_safe;
END J2JME_MAPPINGS;
/
